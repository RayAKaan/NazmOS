"""Canonical column mapper (spec §13).

    raw header
      ↓ text normalization
      ↓ candidate roles
      ↓ value-pattern analysis
      ↓ cross-column analysis
      ↓ source metadata
      ↓ deterministic scoring
      ↓ confidence threshold
      ↓ (JEV only if ambiguity is material)
      ↓ validated role

Two rules govern everything here.

**Rule 1 — never silently resolve an ambiguous header.** A bare ``Amount`` column
on a sales sheet is revenue; on a purchase sheet it is spend; on a bank sheet it is
a movement. The mapper returns *candidates* with scores and marks the column
``AMBIGUOUS`` when the top two are too close to call. The caller decides whether
ambiguity is acceptable; the mapper never lies to resolve it.

**Rule 2 — a poor match is reported as unmapped.** Forcing an unmatched header
into the nearest role is what produced columns called ``cost`` that held a date.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import re
from typing import Any, Mapping, Optional, Sequence

from app.services.orbit.contracts import (
    DecisionOrigin,
    normalize_identifier,
    normalize_text,
)
from app.services.orbit.semantics.vocabulary import (
    ALL_ROLES,
    ALIAS_INDEX,
    PRIMARY_DOMAIN_BY_ARTIFACT_KIND,
    ROLES_BY_ARTIFACT_KIND,
    SemanticRole,
    ValueType,
    designated_role_for,
    domain_of,
    GENERIC_MONEY_HEADERS as _VOCAB_GENERIC_MONEY_HEADERS,
    exact_alias_lookup,
    get_role,
    is_currency_role,
)

#: Below this, a column is not mapped at all. A weak guess is worse than a gap.
MIN_MAPPING_CONFIDENCE = 0.45

#: When the top two candidates are within this margin, the header is ambiguous.
#: 0.12 ≈ "genuinely too close to call" once scores are normalised to 0..1.
AMBIGUITY_MARGIN = 0.12

#: Head whose best score lands in this band is accepted but flagged for review.
REVIEW_BAND = 0.70

# Re-exported from the vocabulary module so callers of either module share one
# definition of these header sets.
#: Only genuinely vague words belong here. 'Cost' and 'Price' are *specific* -- a
#: column called 'Cost' means cost -- and putting them in this set would let a
#: POS export's designated money role capture the cost column and discard it.
GENERIC_MONEY_HEADERS = _VOCAB_GENERIC_MONEY_HEADERS

#: Money roles a generic header could plausibly mean, in reporting order.
GENERIC_MONEY_CANDIDATES = (
    "sale_amount", "purchase_amount", "payment_amount", "expense_amount", "amount",
)

#: Confidence for a role assigned from the artifact kind rather than from the
#: header's own text. High enough to accept, low enough that a reviewer can see it
#: did not come from the header.
DESIGNATED_CONFIDENCE = 0.75


class ColumnMappingStatus(str, Enum):
    MAPPED = "mapped"
    AMBIGUOUS = "ambiguous"
    UNMAPPED = "unmapped"


@dataclass(frozen=True)
class ColumnCandidate:
    """One possible meaning for a column, with the reason it was proposed."""

    role: str
    score: float
    #: Which evidence contributed: 'alias', 'token', 'value_shape', 'cross_column'.
    reasons: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"role": self.role, "score": round(self.score, 4), "reasons": list(self.reasons)}


@dataclass(frozen=True)
class ColumnMapping:
    """The full mapping decision for one column, including what was rejected."""

    raw_header: str
    normalized_header: str
    status: ColumnMappingStatus
    selected_role: Optional[str] = None
    confidence: float = 0.0
    candidates: tuple[ColumnCandidate, ...] = ()
    needs_review: bool = False
    origin: DecisionOrigin = DecisionOrigin.DETERMINISTIC
    #: Populated when bounded judgment was consulted; never silently replaces the
    #: deterministic candidate (spec §53).
    jev_suggested_role: Optional[str] = None
    jev_choice: Optional[str] = None
    notes: tuple[str, ...] = ()

    @property
    def is_mapped(self) -> bool:
        return self.status is ColumnMappingStatus.MAPPED

    @property
    def top_candidates(self) -> tuple[str, ...]:
        return tuple(c.role for c in self.candidates[:3])

    def to_dict(self) -> dict[str, Any]:
        return {
            "raw_header": self.raw_header,
            "normalized_header": self.normalized_header,
            "status": self.status.value,
            "selected_role": self.selected_role,
            "confidence": round(self.confidence, 4),
            "candidates": [c.to_dict() for c in self.candidates],
            "needs_review": self.needs_review,
            "origin": self.origin.value,
            "jev_suggested_role": self.jev_suggested_role,
            "jev_choice": self.jev_choice,
            "notes": list(self.notes),
        }


@dataclass(frozen=True)
class ColumnProfile:
    """Value-shape summary for one column, computed once per artifact."""

    header: str
    total: int = 0
    non_null: int = 0
    numeric: int = 0
    text: int = 0
    date_like: int = 0
    currency_like: int = 0
    negative: int = 0
    distinct: int = 0
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    mean_value: Optional[float] = None
    integer_ratio: float = 0.0
    sample_values: tuple[str, ...] = ()

    @property
    def fill_rate(self) -> float:
        return round(self.non_null / self.total, 4) if self.total else 0.0

    @property
    def numeric_ratio(self) -> float:
        return round(self.numeric / self.non_null, 4) if self.non_null else 0.0

    @property
    def date_ratio(self) -> float:
        return round(self.date_like / self.non_null, 4) if self.non_null else 0.0

    @property
    def currency_ratio(self) -> float:
        return round(self.currency_like / self.non_null, 4) if self.non_null else 0.0

    @property
    def all_integral(self) -> bool:
        return self.integer_ratio >= 0.95 and self.numeric > 0

    @property
    def has_negative(self) -> bool:
        return self.negative > 0


_CURRENCY_HINTS = (
    "sar", "saudi", "usd", "eur", "aed", "kwd", "qar", "bhd", "omr", "egp", "jod",
    "ريال", "دولار", "درهم", "دينار", "ريال سعودي",
)
_CURRENCY_SYMBOLS = ("ر.س", "﷼", "$", "€", "£", "د.إ", "د.ك", "ج.م")

#: Leading/trailing currency text that must be removed before numeric parsing.
_CURRENCY_NOISE_RE = re.compile(
    r"(?i)\b(sar|saudi\s+riyal|usd|aed|sr|eur|gbp|kwd|qar|bhd|omr|egp|jod)\b"
    r"|ر\.?\s*س|ريال|د\.?\s*إ|د\.?\s*ك|دولار|درهم|دينار"
    r"|[﷼$€£]"
)


def looks_like_currency(text: str) -> bool:
    """Does a raw cell value carry a currency marker?"""
    lowered = text.strip().lower()
    if any(sym in text for sym in _CURRENCY_SYMBOLS):
        return True
    return any(h in lowered for h in _CURRENCY_HINTS)


def parse_numeric(text: str) -> Optional[float]:
    """Parse a cell to a number, tolerating currency marks, commas and spaces.

    ``"1,250.00 SAR"``, ``"SAR 1,250.00"`` and ``"1.250,00"`` all occur in real
    exports. Returning ``None`` for a parse failure is essential: this is what
    keeps a malformed value from silently becoming zero.
    """
    stripped = _CURRENCY_NOISE_RE.sub(" ", text).strip()
    stripped = stripped.replace(",", "").replace(" ", " ").replace(" ", "")
    if not stripped:
        return None
    # Parenthesised negatives: (1,250.00)
    negative = stripped.startswith("(") and stripped.endswith(")")
    if negative:
        stripped = stripped[1:-1]
    try:
        value = float(stripped)
    except (TypeError, ValueError):
        return None
    return -value if negative else value


def profile_column(header: str, values: Sequence[Any]) -> ColumnProfile:
    """Compute the value-shape profile used to corroborate or reject a guess."""
    total = len(values)
    non_null = numeric = text = date_like = currency_like = negative = 0
    nums: list[float] = []
    distinct: set[str] = set()
    samples: list[str] = []

    for raw in values:
        if raw is None:
            continue
        s = str(raw).strip()
        if not s or s.lower() in {"nan", "none", "null", "-", "n/a"}:
            continue
        non_null += 1
        distinct.add(normalize_text(s))
        if len(samples) < 5:
            samples.append(s)

        numeric_value = parse_numeric(s)
        if numeric_value is None:
            text += 1
            # Date shapes: ISO, slash-delimited, or a month name.
            compact = s.replace("-", "/").replace(".", "/").replace(",", "/")
            parts = [p for p in compact.split("/") if p]
            if (
                (len(parts) in (2, 3) and all(p.isdigit() for p in parts))
                or (len(parts) == 3 and len(parts[0]) == 4)
            ):
                date_like += 1
            if looks_like_currency(s):
                currency_like += 1
            continue

        numeric += 1
        nums.append(numeric_value)
        if numeric_value < 0:
            negative += 1
        if looks_like_currency(s):
            currency_like += 1

    return ColumnProfile(
        header=header,
        total=total,
        non_null=non_null,
        numeric=numeric,
        text=text,
        date_like=date_like,
        currency_like=currency_like,
        negative=negative,
        distinct=len(distinct),
        min_value=min(nums) if nums else None,
        max_value=max(nums) if nums else None,
        mean_value=round(sum(nums) / len(nums), 4) if nums else None,
        integer_ratio=(
            round(sum(1 for n in nums if float(n).is_integer()) / len(nums), 4) if nums else 0.0
        ),
        sample_values=tuple(samples),
    )


#: Value shapes that flatly contradict a role. A header match cannot rescue a
#: column whose contents are the wrong shape entirely: a "Cost" column holding
#: only dates is a mislabelled date column, and mapping it would place dates in
#: money fields.
HARD_CONTRADICTIONS: dict[ValueType, str] = {
    ValueType.CURRENCY: "value_shape:dates_in_a_money_column",
    ValueType.NUMERIC: "value_shape:dates_in_a_numeric_column",
    ValueType.QUANTITY: "value_shape:dates_in_a_quantity_column",
}


def value_shape_contradicts(profile: Optional[ColumnProfile], role: SemanticRole) -> str | None:
    """Return a reason string when the column's values cannot be this role."""
    if profile is None or profile.non_null == 0:
        return None
    if profile.date_ratio >= 0.8:
        return HARD_CONTRADICTIONS.get(role.value_type)
    if role.value_type is ValueType.TEXT and profile.numeric_ratio >= 0.9:
        return "value_shape:numbers_in_a_text_column"
    if role.value_type is ValueType.DATE and profile.numeric_ratio >= 0.9:
        return "value_shape:numbers_in_a_date_column"
    return None


def _value_evidence(profile: Optional[ColumnProfile], role: SemanticRole) -> tuple[float, str | None]:
    """Corroborate or contradict a role guess using the column's value shape."""
    if profile is None or profile.non_null == 0:
        return 0.0, None

    ratio = profile.numeric_ratio if role.value_type is not ValueType.TEXT else profile.text / max(
        profile.non_null, 1
    )

    if role.value_type is ValueType.DATE:
        if profile.date_ratio >= 0.6:
            return 0.18, "value_shape:date"
        # A date column that is purely numeric is suspicious but common in
        # exports that serialise dates; only reject it if it is not date-shaped.
        if profile.numeric_ratio > 0.8 and profile.date_ratio < 0.2:
            return -0.25, "value_shape:numeric_not_date"
        return 0.0, None

    if value_shape_contradicts(profile, role):
        return -1.0, value_shape_contradicts(profile, role)

    if role.value_type is ValueType.IDENTIFIER:
        if profile.text >= profile.numeric and profile.numeric_ratio < 0.5:
            return 0.15, "value_shape:text_identifier"
        return 0.0, None

    if role.value_type in (ValueType.CURRENCY, ValueType.NUMERIC, ValueType.QUANTITY):
        if profile.numeric_ratio >= 0.7:
            bonus = 0.16
            if is_currency_role(role.canonical_name) and profile.currency_ratio >= 0.3:
                bonus += 0.12
                return bonus, "value_shape:numeric_with_currency"
            return bonus, "value_shape:numeric"
        if profile.date_ratio >= 0.6:
            return -0.4, "value_shape:date_not_number"
        if profile.text > profile.numeric:
            return -0.2, "value_shape:text_not_number"
        return 0.0, None

    return 0.0, None


def _cross_column_bonuses(
    role_name: str,
    all_profiles: Mapping[str, ColumnProfile],
    role_to_profile: Optional[Mapping[str, str]] = None,
) -> tuple[float, str | None]:
    """Adjust scores using relationships that hold across the whole sheet.

    ``quantity x unit_price ~= sale_amount`` is the classic sanity relation on a
    sales line. When it holds, the sheet really is transactional and the
    sales-domain money role deserves support over the generic ``amount``; when a
    candidate is an *expense* role but the sheet carries quantities and prices,
    that candidate is actively contradicted.
    """
    if role_name not in {"sale_amount", "amount", "expense_amount", "purchase_amount"}:
        return 0.0, None

    index = role_to_profile or {}
    qty = next((p for r, p in all_profiles.items() if r == "quantity"), None)
    price = next((p for r, p in all_profiles.items() if r == "unit_price"), None)
    total = next((p for r, p in all_profiles.items() if r == "sale_amount"), None)
    del index

    relational = qty is not None and price is not None and total is not None

    if role_name in {"sale_amount", "amount"}:
        if relational:
            return 0.10, "cross_column:qty_x_price_equals_total"
        if qty is not None and price is not None:
            return 0.05, "cross_column:qty_and_price_present"
        return 0.0, None

    # expense / purchase candidates on a sheet that behaves like a sales ledger
    if relational:
        return -0.20, "cross_column:contradicted_by_qty_x_price_relation"
    return 0.0, None


def _score_column(
    raw_header: str,
    profile: Optional[ColumnProfile],
    all_profiles: Mapping[str, ColumnProfile],
    role_to_profile: Optional[Mapping[str, str]] = None,
) -> list[ColumnCandidate]:
    """Deterministic scoring of every role for one header."""
    normalized = normalize_text(raw_header)
    candidates: dict[str, ColumnCandidate] = {}

    exact = exact_alias_lookup(normalized)
    header_scores: dict[str, tuple[float, tuple[str, ...]]] = {}

    for role in ALL_ROLES:
        score = role.matches(normalized)
        reasons: list[str] = []
        if score >= 1.0:
            reasons.append("alias:exact")
        elif score > 0.0:
            reasons.append("token:match")
        if exact == role.canonical_name:
            score = max(score, 1.0)
            reasons.append("alias:index")
        if score > 0.0:
            header_scores[role.canonical_name] = (score, tuple(reasons))

    if not header_scores:
        return []

    for role_name, (base, reasons) in header_scores.items():
        role = get_role(role_name)
        if role is None:
            continue
        adj, adj_reason = _value_evidence(profile, role)
        cross, cross_reason = _cross_column_bonuses(role_name, all_profiles, role_to_profile)
        final = max(0.0, min(1.0, base + adj + cross))
        all_reasons = list(reasons)
        if adj_reason:
            all_reasons.append(adj_reason)
        if cross_reason:
            all_reasons.append(cross_reason)
        candidates[role_name] = ColumnCandidate(
            role=role_name, score=final, reasons=tuple(all_reasons)
        )

    return sorted(candidates.values(), key=lambda c: (-c.score, c.role))


def map_column(
    raw_header: str,
    *,
    profile: Optional[ColumnProfile] = None,
    all_profiles: Optional[Mapping[str, ColumnProfile]] = None,
    role_to_profile: Optional[Mapping[str, str]] = None,
    expected_roles: Optional[Sequence[str]] = None,
    artifact_hint: Optional[str] = None,
) -> ColumnMapping:
    """Map one header, reporting ambiguity instead of hiding it.

    ``expected_roles`` optionally restricts the candidate set — used when the
    artifact classifier already knows the artifact kind, so a POS sales export
    should not map its ``Amount`` column to ``expense_amount``.
    """
    normalized = normalize_text(raw_header)
    if not normalized:
        return ColumnMapping(
            raw_header=raw_header,
            normalized_header=normalized,
            status=ColumnMappingStatus.UNMAPPED,
            notes=("empty header",),
        )

    # A generic header ("Amount", "Qty") carries no header-level evidence for the
    # specific role it denotes on a known artifact kind. This is resolved *before*
    # candidate filtering, because after filtering those roles are already gone.
    designated = designated_role_for(normalized, artifact_hint)
    if designated is not None:
        return ColumnMapping(
            raw_header=raw_header,
            normalized_header=normalized,
            status=ColumnMappingStatus.MAPPED,
            selected_role=designated,
            confidence=DESIGNATED_CONFIDENCE,
            candidates=(),
            notes=(
                f"{normalized!r} is a generic header; artifact kind {artifact_hint!r} "
                f"designates it as {designated!r}",
            ),
        )

    candidates = _score_column(raw_header, profile, all_profiles or {}, role_to_profile)
    if expected_roles:
        allowed = set(expected_roles)
        in_scope = [c for c in candidates if c.role in allowed]
        out_scope = [c for c in candidates if c.role not in allowed]
        if not in_scope:
            return ColumnMapping(
                raw_header=raw_header,
                normalized_header=normalized,
                status=ColumnMappingStatus.UNMAPPED,
                confidence=candidates[0].score if candidates else 0.0,
                candidates=tuple(candidates[:5]),
                notes=(
                    f"header {normalized!r} matched only roles excluded by the "
                    f"{artifact_hint or 'artifact'} allowlist: "
                    + ", ".join(c.role for c in candidates[:3]),
                ),
            )
        # Out-of-scope candidates stay *visible* (they explain why a role was
        # rejected) but can never be selected.
        candidates = sorted(
            in_scope + out_scope, key=lambda c: (c.role not in allowed, -c.score, c.role)
        )
        selectable = in_scope
    else:
        selectable = candidates

    if not candidates:
        return ColumnMapping(
            raw_header=raw_header,
            normalized_header=normalized,
            status=ColumnMappingStatus.UNMAPPED,
            notes=(f"no role matched header {normalized!r}",),
        )

    top = selectable[0]
    runner_up = selectable[1] if len(selectable) > 1 else None

    if top.score < MIN_MAPPING_CONFIDENCE:
        return ColumnMapping(
            raw_header=raw_header,
            normalized_header=normalized,
            status=ColumnMappingStatus.UNMAPPED,
            confidence=top.score,
            candidates=tuple(candidates[:5]),
            notes=(f"best candidate {top.role!r} scored {top.score:.2f} < {MIN_MAPPING_CONFIDENCE}",),
        )

    # A generic money header is only decidable when the artifact kind declares
    # which kind of money it carries. "Amount" on a POS export is revenue; on a
    # bank statement it is a movement. Without that signal it stays ambiguous.
    if normalized in GENERIC_MONEY_HEADERS:
        primary = PRIMARY_DOMAIN_BY_ARTIFACT_KIND.get(artifact_hint or "")
        if primary is None:
            ranked = sorted(
                [c for c in selectable if c.role in GENERIC_MONEY_CANDIDATES],
                key=lambda c: (-c.score, c.role),
            )
            if len(ranked) > 1:
                return ColumnMapping(
                    raw_header=raw_header,
                    normalized_header=normalized,
                    status=ColumnMappingStatus.AMBIGUOUS,
                    selected_role=None,
                    confidence=ranked[0].score,
                    candidates=tuple(ranked[:5]),
                    needs_review=True,
                    notes=(
                        f"{normalized!r} names money without naming its kind; it could mean "
                        + ", ".join(c.role for c in ranked[:4])
                        + ". Requires an artifact hint or bounded judgment to resolve.",
                    ),
                )
        else:
            in_domain = [c for c in selectable if domain_of(c.role) is primary]
            if in_domain and (top.score - in_domain[0].score) <= AMBIGUITY_MARGIN:
                chosen = in_domain[0]
                return ColumnMapping(
                    raw_header=raw_header,
                    normalized_header=normalized,
                    status=ColumnMappingStatus.MAPPED,
                    selected_role=chosen.role,
                    confidence=chosen.score,
                    candidates=tuple(candidates[:5]),
                    notes=(
                        f"resolved via artifact kind {artifact_hint!r} "
                        f"(primary domain {primary.value}): {chosen.role}",
                    ),
                )

    if runner_up is not None and (top.score - runner_up.score) < AMBIGUITY_MARGIN:
        return ColumnMapping(
            raw_header=raw_header,
            normalized_header=normalized,
            status=ColumnMappingStatus.AMBIGUOUS,
            selected_role=None,
            confidence=top.score,
            candidates=tuple(candidates[:5]),
            needs_review=True,
            notes=(
                f"{top.role!r} ({top.score:.2f}) and {runner_up.role!r} "
                f"({runner_up.score:.2f}) are too close to distinguish",
            ),
        )

    return ColumnMapping(
        raw_header=raw_header,
        normalized_header=normalized,
        status=ColumnMappingStatus.MAPPED,
        selected_role=top.role,
        confidence=top.score,
        candidates=tuple(candidates[:5]),
        needs_review=top.score < REVIEW_BAND,
    )


@dataclass(frozen=True)
class ArtifactColumnMap:
    """The complete column mapping for one artifact."""

    mappings: tuple[ColumnMapping, ...] = ()
    artifact_hint: Optional[str] = None

    @property
    def by_raw_header(self) -> dict[str, ColumnMapping]:
        return {m.raw_header: m for m in self.mappings}

    @property
    def role_to_header(self) -> dict[str, str]:
        """Selected role -> raw header.

        Ambiguous and unmapped columns are excluded. When two columns claim the
        same role the first one wins, and the collision is reported through
        :attr:`role_collisions` rather than silently discarding a column.
        """
        out: dict[str, str] = {}
        for mapping in self.mappings:
            if not mapping.is_mapped or not mapping.selected_role:
                continue
            out.setdefault(mapping.selected_role, mapping.raw_header)
        return out

    @property
    def role_collisions(self) -> dict[str, tuple[str, str]]:
        """Roles claimed by more than one column: role -> (kept, discarded).

        A collision means data was not ingested, so it must be visible rather than
        resolved by iteration order.
        """
        seen: dict[str, list[str]] = {}
        for mapping in self.mappings:
            if mapping.is_mapped and mapping.selected_role:
                seen.setdefault(mapping.selected_role, []).append(mapping.raw_header)
        return {
            role: (headers[0], ", ".join(headers[1:]))
            for role, headers in seen.items()
            if len(headers) > 1
        }

    @property
    def ambiguous_headers(self) -> tuple[str, ...]:
        return tuple(m.raw_header for m in self.mappings if m.status is ColumnMappingStatus.AMBIGUOUS)

    @property
    def unmapped_headers(self) -> tuple[str, ...]:
        return tuple(m.raw_header for m in self.mappings if m.status is ColumnMappingStatus.UNMAPPED)

    @property
    def needs_review(self) -> tuple[str, ...]:
        return tuple(m.raw_header for m in self.mappings if m.needs_review)

    @property
    def roles(self) -> tuple[str, ...]:
        return tuple(m.selected_role for m in self.mappings if m.selected_role)

    def confidence_for(self, role: str) -> float:
        for m in self.mappings:
            if m.selected_role == role:
                return m.confidence
        return 0.0

    @property
    def mean_confidence(self) -> Optional[float]:
        mapped = [m.confidence for m in self.mappings if m.is_mapped]
        if not mapped:
            return None
        return round(sum(mapped) / len(mapped), 4)

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_hint": self.artifact_hint,
            "mappings": [m.to_dict() for m in self.mappings],
            "role_to_header": dict(self.role_to_header),
            "ambiguous_headers": list(self.ambiguous_headers),
            "unmapped_headers": list(self.unmapped_headers),
            "needs_review": list(self.needs_review),
            "role_collisions": {
                role: {"kept": kept, "discarded": dropped}
                for role, (kept, dropped) in self.role_collisions.items()
            },
            "mean_confidence": self.mean_confidence,
        }


def map_columns(
    headers: Sequence[str],
    *,
    rows: Optional[Sequence[Sequence[Any]]] = None,
    artifact_hint: Optional[str] = None,
    expected_roles: Optional[Sequence[str]] = None,
    expected_roles_for: Optional[Mapping[str, Sequence[str]]] = None,
) -> ArtifactColumnMap:
    """Map every header of an artifact.

    ``artifact_hint`` (e.g. ``"bank_statement"``) selects the role allowlist from
    :data:`ROLES_BY_ARTIFACT_KIND`, which is what lets a generic "Amount" column
    resolve on a source that declares what kind of money it is.
    """
    profiles: dict[str, ColumnProfile] = {}
    for idx, header in enumerate(headers):
        values = [row[idx] for row in rows if idx < len(row)] if rows else []
        profiles[header] = profile_column(header, values)

    resolved_expected = expected_roles
    if resolved_expected is None:
        table = expected_roles_for or ROLES_BY_ARTIFACT_KIND
        if artifact_hint:
            resolved_expected = table.get(artifact_hint)

    # Best-guess role per header, used only for cross-column analysis. Computed
    # without cross-column bonuses to avoid circular reasoning.
    provisional: dict[str, str] = {}
    for header in headers:
        for cand in _score_column(header, profiles.get(header), profiles):
            if cand.score >= MIN_MAPPING_CONFIDENCE:
                provisional[header] = cand.role
                break

    mappings = [
        map_column(
            header,
            profile=profiles.get(header),
            all_profiles=profiles,
            role_to_profile=provisional,
            expected_roles=resolved_expected,
            artifact_hint=artifact_hint,
        )
        for header in headers
    ]
    return ArtifactColumnMap(mappings=tuple(mappings), artifact_hint=artifact_hint)
