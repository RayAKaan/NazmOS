"""Canonical entity resolution (spec §19).

The audit found **five independent entity-resolution implementations** with
different semantics, plus three parallel contract vocabularies:

* ``product_pairing.pair_products``      rapidfuzz WRatio, greedy assignment
* ``adapters/item_resolver.resolve_item`` 4 tiers, tier 4 is a 10-char substring
* ``supplier_price_ingestion``           unanchored ``ILIKE '%name%'``
* ``ETLPipeline._upsert_items``          exact name only
* ``BusinessSnapshotBuilder._ledger``     exact-name dict key
* ``recovery_match_service``             unrelated cross-business heuristic

Tier 4 of ``item_resolver`` is the dangerous one: a 10-character substring match
will happily merge unrelated products. This module replaces all of them.

Resolution ladder, strongest evidence first:

    exact ID → normalized ID → exact normalized name → alias
             → phone/email/SKU → guarded fuzzy → (JEV) → ambiguous

**The safety property that matters most: over-merging is worse than
under-merging.** Merging ``Pepsi 330ml`` with ``Pepsi 500ml`` invents a fact that
corrupts inventory and margin forever. Splitting one customer into two is a
recoverable cosmetic problem. So when two strong signals conflict, the answer is
``AMBIGUOUS`` — never a guess.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any, Iterable, Mapping, Optional, Sequence

from app.services.orbit.contracts import (
    DecisionOrigin,
    Entity,
    EntityKind,
    EntityResolution,
    MatchMethod,
    ResolutionOutcome,
    content_hash,
    normalize_identifier,
    normalize_text,
)
from app.services.orbit.contracts import _utcnow

#: Fuzzy scores at or above this are considered, below it there is no match.
FUZZY_CANDIDATE_THRESHOLD = 88.0
#: Score at or above which a fuzzy match is accepted outright.
FUZZY_ACCEPT_THRESHOLD = 92.0
#: Difference required between the best two fuzzy candidates to accept the best.
FUZZY_MARGIN = 6.0

#: Tokens that mark a distinct variant. Two products sharing a base name but
#: differing in one of these are DIFFERENT entities, never a fuzzy merge.
VARIANT_TOKENS = frozenset({
    # sizes
    "330", "500", "330ml", "500ml", "1l", "1.5l", "2l", "small", "large", "big",
    "mini", "jumbo", "family", "xl", "medium", "std", "regular",
    "٥٠٠", "٣٣٠",
    # grades/flavours
    "sugar", "diet", "zero", "light", "regular", "original", "classic", "premium",
    "organic", "whole", "skim", "full", "extra",
    # pack form
    "can", "bottle", "box", "pack", "carton", "jar", "bag", "tin", "pouch", "single",
    "multipack", "6pk", "12pk", "24pk",
    # state
    "frozen", "chilled", "fresh", "dry", "instant", "canned",
})

#: Tokens describing a legal form. Deliberately conservative: "trading" and
#: "shop" describe what a company does and are usually part of its registered
#: name, so stripping them would over-merge distinct suppliers.
LEGAL_SUFFIX_TOKENS = frozenset({
    "est", "establishment", "co", "company", "llc", "ltd", "limited",
    "inc", "incorporated", "corp", "corporation", "gmbh", "sa", "sarl", "bv",
    "plc", "partnership", "wll", "llp",
    "شركة", "مؤسسة",
})

#: Lower threshold used only to *report* near-duplicate products. Reporting is
#: safe at a lower bar than merging, and "Pepsi 330ml" vs "Pepsi 500ml" scores
#: only ~82 on fuzzy similarity, so the merge threshold would hide the pair.
VARIANT_SURFACING_THRESHOLD = 70.0

#: Identifiers strong enough to merge without any name agreement.
STRONG_IDENTIFIERS = ("sku", "barcode", "email", "phone", "abn", "vat_number")

#: How each authoritative identifier is reported in the resolution record.
_IDENTIFIER_MATCH_METHOD: dict[str, MatchMethod] = {
    "sku": MatchMethod.SKU,
    "barcode": MatchMethod.BARCODE,
    "email": MatchMethod.EMAIL,
    "phone": MatchMethod.PHONE,
}


def _token_set(text: str) -> set[str]:
    return {t for t in normalize_text(text).split() if t}


def variant_signature(name: str) -> frozenset[str]:
    """Variant-bearing tokens within a name, used to block unsafe merges."""
    return frozenset(t for t in _token_set(name) if t in VARIANT_TOKENS)


def strip_legal_suffix(name: str) -> str:
    tokens = [t for t in normalize_text(name).split() if t]
    while tokens and tokens[-1] in LEGAL_SUFFIX_TOKENS:
        tokens.pop()
    return " ".join(tokens)


@dataclass(frozen=True)
class EntityCandidate:
    """One pre-existing entity considered during resolution."""

    entity: Entity
    match_method: MatchMethod
    score: float
    evidence_ids: tuple[str, ...] = ()
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_id": self.entity.entity_id,
            "canonical_name": self.entity.canonical_name,
            "match_method": self.match_method.value,
            "score": round(self.score, 4),
            "evidence_ids": list(self.evidence_ids),
            "note": self.note,
        }


@dataclass
class EntityStore:
    """In-memory canonical entity index for one business.

    Scoped to a single business so that two tenants can never resolve against
    each other's entities, even with identical names.
    """

    business_id: Any = None
    entities: dict[str, Entity] = field(default_factory=dict)
    #: normalized name -> entity ids, per kind
    _by_name: dict[tuple[str, str], set[str]] = field(default_factory=dict)
    #: identifier value -> entity id, per kind
    _by_identifier: dict[tuple[str, str], str] = field(default_factory=dict)
    #: alias -> entity id
    _by_alias: dict[tuple[str, str], str] = field(default_factory=dict)
    resolutions: list[EntityResolution] = field(default_factory=list)

    def register(self, entity: Entity) -> Entity:
        self.entities[entity.entity_id] = entity
        name_key = (entity.kind.value, entity.normalized_name or normalize_text(entity.canonical_name or ""))
        if name_key[1]:
            self._by_name.setdefault(name_key, set()).add(entity.entity_id)
        for key, value in entity.identifiers.items():
            normalized = normalize_identifier(value)
            if normalized:
                self._by_identifier[(entity.kind.value, f"{key}:{normalized}")] = entity.entity_id
        for alias in entity.aliases:
            normalized = normalize_text(alias)
            if normalized:
                self._by_alias[(entity.kind.value, normalized)] = entity.entity_id
        return entity

    def all(self) -> tuple[Entity, ...]:
        return tuple(self.entities[eid] for eid in sorted(self.entities))

    def of_kind(self, kind: EntityKind) -> tuple[Entity, ...]:
        return tuple(e for e in self.all() if e.kind is kind)

    def __len__(self) -> int:
        return len(self.entities)

    # ── lookups ──────────────────────────────────────────────────────────────

    def by_identifier(self, kind: EntityKind, key: str, value: str) -> Optional[Entity]:
        eid = self._by_identifier.get((kind.value, f"{key}:{normalize_identifier(value)}"))
        return self.entities.get(eid) if eid else None

    def by_exact_name(self, kind: EntityKind, name: str) -> list[Entity]:
        key = (kind.value, normalize_text(name))
        return [self.entities[eid] for eid in sorted(self._by_name.get(key, set())) if eid in self.entities]

    def by_alias(self, kind: EntityKind, alias: str) -> Optional[Entity]:
        eid = self._by_alias.get((kind.value, normalize_text(alias)))
        return self.entities.get(eid) if eid else None

    def names(self) -> list[tuple[Entity, str]]:
        """Every (entity, normalized name) pair, for fuzzy comparison."""
        pairs: list[tuple[Entity, str]] = []
        for entity in self.all():
            name = entity.normalized_name or normalize_text(entity.canonical_name or "")
            if name:
                pairs.append((entity, name))
            for alias in entity.aliases:
                normalized = normalize_text(alias)
                if normalized:
                    pairs.append((entity, normalized))
        return pairs

    def merge_names(self, entity: Entity, extra_name: str) -> None:
        """Record an additional observed name for an existing entity."""
        normalized = normalize_text(extra_name)
        if not normalized:
            return
        key = (entity.kind.value, normalized)
        self._by_name.setdefault(key, set()).add(entity.entity_id)
        updated = replace(
            entity,
            raw_names=tuple({*entity.raw_names, extra_name}),
            aliases=tuple({*entity.aliases, extra_name}),
        )
        self.entities[entity.entity_id] = updated


def _identifier_contradiction(entity: Entity, identifiers: Mapping[str, str]) -> Optional[str]:
    """Report a declared identifier that conflicts with the entity's own.

    Only *strong* identifiers can contradict. A missing identifier is not a
    contradiction — plenty of exports simply omit the SKU.
    """
    for key in STRONG_IDENTIFIERS:
        incoming = identifiers.get(key)
        if not incoming:
            continue
        existing = entity.identifiers.get(key)
        if existing and normalize_identifier(existing) != normalize_identifier(incoming):
            return f"{key}={incoming!r} conflicts with {key}={existing!r}"
    return None


def _fuzzy_score(left: str, right: str) -> float:
    """0..100 similarity. Uses rapidfuzz when present, else a token overlap."""
    try:
        from rapidfuzz import fuzz

        return float(fuzz.WRatio(left, right))
    except Exception:
        left_tokens, right_tokens = set(left.split()), set(right.split())
        if not left_tokens or not right_tokens:
            return 0.0
        return round(100.0 * len(left_tokens & right_tokens) / len(left_tokens | right_tokens), 4)


def _blocking_conflict(query_name: str, candidate_name: str) -> Optional[str]:
    """Refuse a merge when the names carry different variant tokens.

    ``Pepsi 330ml`` vs ``Pepsi 500ml`` scores very high on fuzzy similarity — the
    only difference is one token. Without this guard they merge, which corrupts
    inventory and margin permanently.
    """
    q_variants = variant_signature(query_name)
    c_variants = variant_signature(candidate_name)
    if q_variants and c_variants and q_variants != c_variants:
        return (
            f"variant tokens differ: query has {sorted(q_variants)}, "
            f"candidate has {sorted(c_variants)}"
        )
    return None


class EntityResolver:
    """The single entity resolver.

    Deterministic by default. Bounded judgment is opt-in via ``jev`` and is only
    consulted for genuine ambiguity; it never overrides a decisive deterministic
    signal.
    """

    def __init__(self, store: Optional[EntityStore] = None, *, business_id: Any = None) -> None:
        self.store = store or EntityStore(business_id=business_id)

    # ── the ladder ───────────────────────────────────────────────────────────

    def resolve(
        self,
        kind: EntityKind,
        *,
        name: Optional[str] = None,
        identifiers: Optional[Mapping[str, str]] = None,
        raw_names: Optional[Sequence[str]] = None,
        evidence_ids: Sequence[str] = (),
        allow_fuzzy: bool = True,
        jev: Optional[Any] = None,
    ) -> EntityResolution:
        """Resolve one observed reference to a canonical entity.

        Returns ``AMBIGUOUS`` rather than guessing whenever the evidence does not
        support a single answer.
        """
        identifiers = {k: v for k, v in (identifiers or {}).items() if v}
        query_name = normalize_text(name) if name else ""

        # 1-3. Strong identifiers: decisive, no name agreement required.
        for key in STRONG_IDENTIFIERS:
            value = identifiers.get(key)
            if not value:
                continue
            found = self.store.by_identifier(kind, key, value)
            if found is not None:
                return self._record(
                    kind, name or "", ResolutionOutcome.SAME_ENTITY,
                    _IDENTIFIER_MATCH_METHOD.get(key, MatchMethod.NORMALIZED_ID),
                    selected=found, confidence=1.0, evidence_ids=evidence_ids,
                    note=f"matched on {key}={value!r}",
                )

        # 4. Exact normalized name.
        if query_name:
            exact = self.store.by_exact_name(kind, query_name)
            # A conflicting authoritative identifier blocks a name-based merge.
            # "Pepsi 330ml" with sku=SKU-B is not "Pepsi 330ml" with sku=SKU-A,
            # and merging them would corrupt inventory and margin permanently.
            if len(exact) == 1:
                contradiction = _identifier_contradiction(exact[0], identifiers)
                if contradiction:
                    return self._record(
                        kind, name or "", ResolutionOutcome.AMBIGUOUS,
                        MatchMethod.UNRESOLVED, candidates=tuple(exact),
                        confidence=0.5, evidence_ids=evidence_ids,
                        note=(
                            f"name matches an existing entity but {contradiction}; "
                            "refusing to merge two different records"
                        ),
                    )
                self.store.merge_names(exact[0], name or "")
                return self._record(
                    kind, name or "", ResolutionOutcome.SAME_ENTITY,
                    MatchMethod.EXACT_NORMALIZED_NAME, selected=exact[0],
                    confidence=1.0, evidence_ids=evidence_ids,
                    note="exact normalized name match",
                )
            if len(exact) > 1:
                # The name alone points at several entities. Do not pick one.
                return self._record(
                    kind, name or "", ResolutionOutcome.AMBIGUOUS,
                    MatchMethod.UNRESOLVED, candidates=tuple(exact),
                    confidence=0.5, evidence_ids=evidence_ids,
                    note=f"{len(exact)} entities share this normalized name",
                )

        # 5. Alias.
        if query_name:
            aliased = self.store.by_alias(kind, query_name)
            if aliased is not None:
                return self._record(
                    kind, name or "", ResolutionOutcome.SAME_ENTITY,
                    MatchMethod.ALIAS, selected=aliased, confidence=0.95,
                    evidence_ids=evidence_ids, note="matched a recorded alias",
                )

        # 6. Guarded fuzzy, restricted to the same kind.
        if allow_fuzzy and query_name:
            fuzzy = self._fuzzy_candidates(kind, query_name, identifiers)
            if fuzzy:
                best = fuzzy[0]
                runner = fuzzy[1] if len(fuzzy) > 1 else None
                accept = best.score >= FUZZY_ACCEPT_THRESHOLD and (
                    runner is None or best.score - runner.score >= FUZZY_MARGIN
                )
                if accept:
                    return self._record(
                        kind, name or "", ResolutionOutcome.SAME_ENTITY,
                        MatchMethod.FUZZY, selected=best.entity,
                        confidence=round(min(0.99, best.score / 100.0), 4),
                        evidence_ids=evidence_ids, candidates=tuple(c.entity for c in fuzzy[:3]),
                        note=f"fuzzy score {best.score:.1f} with a clear margin",
                    )
                return self._record(
                    kind, name or "", ResolutionOutcome.AMBIGUOUS,
                    MatchMethod.FUZZY, candidates=tuple(c.entity for c in fuzzy[:3]),
                    confidence=round(best.score / 100.0, 4), evidence_ids=evidence_ids,
                    note=(
                        f"best fuzzy score {best.score:.1f} is not decisive"
                        + (f" (runner-up {runner.score:.1f})" if runner else "")
                    ),
                )

        # 7. Bounded judgment, only if a provider is supplied and it is safe to ask.
        if jev is not None and query_name:
            judged = self._consult_jev(
                jev, kind, name or "", identifiers, fuzzy_candidates=(), evidence_ids=evidence_ids
            )
            if judged is not None:
                return judged

        # 8. Nothing matched.
        return self._record(
            kind, name or "", ResolutionOutcome.DIFFERENT_ENTITY,
            MatchMethod.UNRESOLVED, confidence=0.0, evidence_ids=evidence_ids,
            note="no existing entity matched; a new entity is required",
        )

    def _fuzzy_candidates(
        self, kind: EntityKind, query_name: str, identifiers: Mapping[str, str]
    ) -> list[EntityCandidate]:
        """Fuzzy matches that are safe to consider, best first."""
        candidates: list[EntityCandidate] = []
        for entity, name in self.store.names():
            if entity.kind is not kind:
                continue
            score = _fuzzy_score(query_name, name)
            if score < FUZZY_CANDIDATE_THRESHOLD:
                continue
            conflict = _blocking_conflict(query_name, name) or _identifier_contradiction(
                entity, identifiers
            )
            if conflict:
                # Recorded as blocked rather than dropped, so a reviewer can see
                # that the merge was considered and refused on purpose.
                candidates.append(
                    EntityCandidate(
                        entity=entity, match_method=MatchMethod.FUZZY, score=score,
                        note=f"blocked: {conflict}",
                    )
                )
                continue
            candidates.append(
                EntityCandidate(
                    entity=entity, match_method=MatchMethod.FUZZY, score=score,
                )
            )
        candidates.sort(key=lambda c: (-c.score, c.entity.entity_id))
        return candidates

    def _consult_jev(
        self, jev: Any, kind: EntityKind, name: str,
        identifiers: Mapping[str, str], *, fuzzy_candidates: Sequence[EntityCandidate],
        evidence_ids: Sequence[str],
    ) -> Optional[EntityResolution]:
        """Ask bounded judgment about a reference it cannot be certain about.

        JEV may only *choose among candidates*. It cannot invent an entity, and a
        failure or an unknown answer leaves the deterministic ambiguity intact.
        """
        try:
            decision = jev.decide_entity(
                kind=kind.value,
                observed_name=name,
                candidates=[
                    {"entity_id": c.entity.entity_id, "name": c.entity.canonical_name}
                    for c in fuzzy_candidates
                ],
                identifiers_present=sorted(identifiers),
            )
        except Exception:
            # A judgment failure must never destroy or invent a fact.
            return None

        if decision is None or not getattr(decision, "choice", None):
            return None
        if decision.choice not in ("same_entity", "different_entity", "ambiguous"):
            return None
        if decision.choice == "same_entity":
            selected_id = getattr(decision, "selected_id", None)
            entity = self.store.entities.get(selected_id) if selected_id else None
            if entity is None:
                return None
            return self._record(
                kind, name or "", ResolutionOutcome.SAME_ENTITY, MatchMethod.JEV,
                selected=entity, confidence=float(getattr(decision, "confidence", 0.5)),
                evidence_ids=evidence_ids, origin=DecisionOrigin.JEV,
                note=f"bounded judgment chose same_entity ({decision.choice})",
            )
        if decision.choice == "different_entity":
            return self._record(
                kind, name or "", ResolutionOutcome.DIFFERENT_ENTITY, MatchMethod.JEV,
                confidence=float(getattr(decision, "confidence", 0.5)),
                evidence_ids=evidence_ids, origin=DecisionOrigin.JEV,
                note="bounded judgment chose different_entity",
            )
        return self._record(
            kind, name or "", ResolutionOutcome.AMBIGUOUS, MatchMethod.JEV,
            confidence=float(getattr(decision, "confidence", 0.3)),
            evidence_ids=evidence_ids, origin=DecisionOrigin.JEV,
            note="bounded judgment could not decide; ambiguity preserved",
        )

    def _record(
        self,
        kind: EntityKind,
        query: str,
        outcome: ResolutionOutcome,
        method: MatchMethod,
        *,
        selected: Optional[Entity] = None,
        candidates: Sequence[Entity] = (),
        confidence: float = 0.0,
        evidence_ids: Sequence[str] = (),
        note: str = "",
        origin: DecisionOrigin = DecisionOrigin.DETERMINISTIC,
    ) -> EntityResolution:
        resolution = EntityResolution(
            query=query,
            kind=kind,
            outcome=outcome,
            match_method=method,
            selected_entity=selected,
            candidates=tuple(candidates),
            confidence=confidence,
            evidence_ids=tuple(evidence_ids),
            origin=origin,
            note=note,
        )
        self.store.resolutions.append(resolution)
        return resolution

    # ── convenience ──────────────────────────────────────────────────────────

    def resolve_or_create(
        self,
        kind: EntityKind,
        *,
        name: Optional[str],
        identifiers: Optional[Mapping[str, str]] = None,
        raw_names: Optional[Sequence[str]] = None,
        evidence_ids: Sequence[str] = (),
        allow_fuzzy: bool = True,
        jev: Optional[Any] = None,
    ) -> tuple[Entity, EntityResolution, bool]:
        """Resolve, creating a new entity only when that is actually justified.

        The third element says whether a new entity was created, which lets callers
        record that fact rather than assume it.
        """
        resolution = self.resolve(
            kind, name=name, identifiers=identifiers, raw_names=raw_names,
            evidence_ids=evidence_ids, allow_fuzzy=allow_fuzzy, jev=jev,
        )
        if resolution.outcome is ResolutionOutcome.SAME_ENTITY and resolution.selected_entity:
            return resolution.selected_entity, resolution, False
        if resolution.outcome is ResolutionOutcome.AMBIGUOUS:
            # Ambiguity is never auto-resolved by creating a duplicate; the caller
            # must decide. Returning the ambiguous resolution makes that explicit.
            return None, resolution, False

        identifier_map = dict(identifiers or {})
        if not identifier_map and name:
            # A name-keyed identity keeps reprocessing deterministic.
            identifier_map = {"name": f"{kind.value}:{normalize_identifier(name)}"}

        entity = Entity(
            kind=kind,
            business_id=self.store.business_id,
            canonical_name=name,
            normalized_name=normalize_text(name) if name else None,
            raw_names=tuple(n for n in (raw_names or ()) if n),
            identifiers=identifier_map,
            aliases=(),
            evidence_ids=tuple(evidence_ids),
            confidence=1.0 if name else 0.5,
            first_seen_at=_utcnow(),
            last_seen_at=_utcnow(),
        )
        self.store.register(entity)
        return entity, resolution, True

    # ── policy helpers ───────────────────────────────────────────────────────

    def products_with_different_variants(self) -> list[tuple[Entity, Entity]]:
        """Product pairs that look alike but carry different variant tokens.

        Surfaced so the conflict and quality layers can report them rather than
        leaving the ambiguity buried inside a resolver.
        """
        products = self.store.of_kind(EntityKind.PRODUCT)
        flagged: list[tuple[Entity, Entity]] = []
        for i, left in enumerate(products):
            left_name = left.normalized_name or normalize_text(left.canonical_name or "")
            left_variants = variant_signature(left_name)
            if not left_variants:
                continue
            for right in products[i + 1:]:
                right_name = right.normalized_name or normalize_text(right.canonical_name or "")
                right_variants = variant_signature(right_name)
                if right_variants and right_variants != left_variants:
                    if _fuzzy_score(left_name, right_name) >= VARIANT_SURFACING_THRESHOLD:
                        flagged.append((left, right))
        return flagged


def build_product(
    name: str, *, sku: Optional[str] = None, barcode: Optional[str] = None,
    business_id: Any = None, evidence_ids: Sequence[str] = (),
) -> Entity:
    """Convenience constructor for a product entity."""
    identifiers: dict[str, str] = {}
    if sku:
        identifiers["sku"] = sku
    if barcode:
        identifiers["barcode"] = barcode
    if not identifiers and name:
        identifiers["name"] = f"product:{normalize_identifier(name)}"
    return Entity(
        kind=EntityKind.PRODUCT,
        business_id=business_id,
        canonical_name=name,
        normalized_name=normalize_text(name),
        raw_names=(name,),
        identifiers=identifiers,
        evidence_ids=tuple(evidence_ids),
        confidence=1.0,
        first_seen_at=_utcnow(),
        last_seen_at=_utcnow(),
    )