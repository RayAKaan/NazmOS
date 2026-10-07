"""Artifact classification (spec §2).

    filename + extension + MIME + size + sheet names + headers + structure
        ↓
    deterministic scoring
        ↓
    ArtifactClassification

Two rules:

**Every CSV is not a POS file.** Content decides, not the extension. A CSV with
``balance`` and ``transaction date`` columns is a bank statement; the same
extension with ``qty`` and ``amount`` is a sales export. Classifying by filename
alone is what let the old guest path treat everything as one shape.

**UNKNOWN is a real answer.** When the evidence is insufficient the classifier
returns ``UNKNOWN`` with the ambiguity recorded, rather than the nearest plausible
type. An unclassified artifact is honest; a wrongly classified one silently
corrupts every downstream projection.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Sequence

from app.services.orbit.contracts import (
    ArtifactType,
    DecisionOrigin,
    DomainCapability,
    SourceType,
    normalize_text,
)
from app.services.orbit.semantics.vocabulary import (
    PRIMARY_DOMAIN_BY_ARTIFACT_KIND,
    domain_of,
)


def domain_for_artifact(artifact_type: ArtifactType) -> Optional[DomainCapability]:
    """The domain an artifact kind primarily carries, if known."""
    return PRIMARY_DOMAIN_BY_ARTIFACT_KIND.get(artifact_type.value)

#: Minimum confidence before a semantic (content-based) type is accepted.
MIN_SEMANTIC_CONFIDENCE = 0.55
#: Below this nothing is claimed, even a format.
MIN_ACCEPT_CONFIDENCE = 0.35

#: Minimum gap between the leading two candidates before accepting the winner.
#: Below this the two are not distinguishable and the answer must be UNKNOWN.
AMBIGUITY_MARGIN = 0.10

#: Binary floating point makes 0.75 - 0.65 evaluate to 0.09999999999999998, which
#: would trip the margin check on an exact tie. Comparisons are made with this
#: tolerance so an exact-margin difference is not treated as "close".
_MARGIN_EPSILON = 1e-9

#: Extensions mapped to a format. This is a *format* claim, not a business one.
_EXTENSION_FORMAT: dict[str, ArtifactType] = {
    ".csv": ArtifactType.CSV,
    ".tsv": ArtifactType.CSV,
    ".txt": ArtifactType.TEXT,
    ".xlsx": ArtifactType.XLSX,
    ".xlsm": ArtifactType.XLSX,
    ".xls": ArtifactType.XLS,
    ".json": ArtifactType.JSON,
    ".pdf": ArtifactType.PDF,
    ".docx": ArtifactType.DOCX,
    ".doc": ArtifactType.DOCX,
    ".png": ArtifactType.IMAGE,
    ".jpg": ArtifactType.IMAGE,
    ".jpeg": ArtifactType.IMAGE,
    ".webp": ArtifactType.IMAGE,
}

#: Magic bytes, checked before the extension so a mislabelled file still routes
#: to the correct extractor.
_MAGIC: tuple[tuple[bytes, ArtifactType], ...] = (
    (b"%PDF-", ArtifactType.PDF),
    (b"PK\x03\x04", ArtifactType.XLSX),   # also DOCX; refined by extension
    (b"\xd0\xcf\x11\xe0", ArtifactType.XLS),
    (b"\x89PNG", ArtifactType.IMAGE),
    (b"\xff\xd8\xff", ArtifactType.IMAGE),
    (b"{", ArtifactType.JSON),
    (b"[", ArtifactType.JSON),
)

#: Filename hints are the weakest signal by design. Their weights sit below the
#: range reachable by mapped content roles, so a filename can never outrank
#: content and can never mask a contradiction penalty.
#: Filename tokens that indicate a business artifact kind. These are *hints*
#: only: a file called "inventory" whose columns are all sales columns is a sales
#: export with a misleading name, and content wins.
_FILENAME_HINTS: tuple[tuple[tuple[str, ...], ArtifactType, float], ...] = (
    (("pos", "sales", "sell", "transaction", "receipt", "order", "بيع", "مبيعات", "صندوق"),
     ArtifactType.POS_EXPORT, 0.45),
    (("inventory", "stock", "wms", "مخزون", "الجرد"),
     ArtifactType.INVENTORY_EXPORT, 0.45),
    (("bank", "statement", "iban", "حساب", "بنك", "كشف"),
     ArtifactType.BANK_STATEMENT, 0.50),
    (("quote", "quotation", "offer price", "عرض سعر", "تسعير"),
     ArtifactType.SUPPLIER_QUOTE, 0.50),
    (("invoice", "فاتورة", "bill"),
     ArtifactType.INVOICE, 0.50),
    (("purchase", "po", "purchase order", "امر شراء", "أمر شراء"),
     ArtifactType.PURCHASE_ORDER, 0.50),
    (("staff", "roster", "schedule", "shift", "employee", "موظفين", "دوام", "جدول"),
     ArtifactType.STAFF_SCHEDULE, 0.50),
    (("marketing", "campaign", "ads", "حملة", "تسويق", "تسويقي"),
     ArtifactType.MARKETING_REPORT, 0.50),
    (("contract", "agreement", "عقد", "عقود", "اتفاقية"),
     ArtifactType.CONTRACT, 0.45),
    (("expense", "مصروف", "مصاريف"),
     ArtifactType.INVOICE, 0.35),
)

#: Penalty applied when a rule's forbidden roles are present. A penalty rather
#: than a disqualification, because these roles contradict without making the
#: classification impossible: a bank statement may legitimately list stock as a
#: memo line, and a sales export may carry a stock column for running balances.
FORBIDDEN_ROLE_PENALTY = 0.22

#: Semantic signals per artifact kind: (roles that must be present, roles that
#: contradict, domain).
_SEMANTIC_RULES: dict[ArtifactType, tuple[frozenset[str], frozenset[str], DomainCapability]] = {
    ArtifactType.POS_EXPORT: (
        frozenset({"product_name", "quantity"}),
        frozenset({"stock", "opening_balance"}),
        DomainCapability.SALES,
    ),
    ArtifactType.INVENTORY_EXPORT: (
        frozenset({"stock"}),
        frozenset({"sale_amount", "payment_amount"}),
        DomainCapability.INVENTORY,
    ),
    ArtifactType.BANK_STATEMENT: (
        frozenset({"balance"}),
        frozenset({"product_name", "stock", "quantity"}),
        DomainCapability.FINANCE,
    ),
    ArtifactType.SUPPLIER_QUOTE: (
        frozenset({"supplier_name"}),
        frozenset({"stock", "balance"}),
        DomainCapability.PROCUREMENT,
    ),
    ArtifactType.PURCHASE_ORDER: (
        frozenset({"supplier_name", "purchase_quantity"}),
        frozenset({"stock", "balance"}),
        DomainCapability.PROCUREMENT,
    ),
    ArtifactType.INVOICE: (
        frozenset({"sale_amount"}),
        frozenset({"stock", "opening_stock"}),
        DomainCapability.FINANCE,
    ),
    ArtifactType.STAFF_SCHEDULE: (
        frozenset({"employee_name"}),
        frozenset({"product_name", "stock"}),
        DomainCapability.WORKFORCE,
    ),
    ArtifactType.MARKETING_REPORT: (
        frozenset({"campaign_name"}),
        frozenset({"stock", "balance"}),
        DomainCapability.MARKETING,
    ),
}

#: Document kinds, identified from text rather than columns.
_DOCUMENT_SIGNALS: dict[ArtifactType, tuple[str, ...]] = {
    ArtifactType.INVOICE: ("invoice", "فاتورة", "invoice no", "amount due", "bill to"),
    ArtifactType.SUPPLIER_QUOTE: ("quotation", "quote", "عرض سعر", "valid until", "quote ref"),
    ArtifactType.PURCHASE_ORDER: ("purchase order", "po number", "امر شراء", "أمر شراء"),
    ArtifactType.BANK_STATEMENT: ("statement of account", "account statement", "كشف حساب",
                                   "opening balance", "closing balance", "iban"),
    ArtifactType.CONTRACT: ("agreement", "contract", "terms and conditions", "عقد", "اتفاقية"),
    ArtifactType.STAFF_SCHEDULE: ("shift", "roster", "schedule", "الوردية", "دوام"),
    ArtifactType.MARKETING_REPORT: ("campaign", "impressions", "reach", "ad spend", "حملة"),
}


@dataclass(frozen=True)
class ClassificationCandidate:
    artifact_type: ArtifactType
    score: float
    reasons: tuple[str, ...] = ()
    #: True when the score is backed by content evidence (mapped roles, document
    #: text, sheet names) rather than by the filename alone. A filename-only guess
    #: must never outrank a content-supported candidate.
    content_supported: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_type": self.artifact_type.value,
            "score": round(self.score, 4),
            "reasons": list(self.reasons),
            "content_supported": self.content_supported,
        }


@dataclass(frozen=True)
class ArtifactClassification:
    """The classification decision, including what was rejected."""

    artifact_type: ArtifactType = ArtifactType.UNKNOWN
    domain: Optional[DomainCapability] = None
    confidence: float = 0.0
    candidates: tuple[ClassificationCandidate, ...] = ()
    classification_method: DecisionOrigin = DecisionOrigin.DETERMINISTIC
    #: True when the evidence could not separate the leading candidates.
    ambiguity: tuple[str, ...] = ()
    needs_review: bool = False
    #: The format we detected, which may differ from the business type.
    format_type: Optional[ArtifactType] = None
    notes: tuple[str, ...] = ()

    @property
    def is_known(self) -> bool:
        return self.artifact_type is not ArtifactType.UNKNOWN

    @property
    def artifact_kind(self) -> Optional[str]:
        """The key used by the semantic vocabulary's per-kind role allowlists."""
        if self.artifact_type is None:
            return None
        value = self.artifact_type.value
        return value if value in PRIMARY_DOMAIN_BY_ARTIFACT_KIND else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_type": self.artifact_type.value,
            "domain": self.domain.value if self.domain else None,
            "confidence": round(self.confidence, 4),
            "candidates": [c.to_dict() for c in self.candidates],
            "classification_method": self.classification_method.value,
            "ambiguity": list(self.ambiguity),
            "needs_review": self.needs_review,
            "format_type": self.format_type.value if self.format_type else None,
            "artifact_kind": self.artifact_kind,
            "is_known": self.is_known,
            "notes": list(self.notes),
        }


def _normalize_artifact_name(name: str) -> str:
    """Normalize a filename or sheet name for hint matching.

    ``normalize_text`` preserves underscores (they are word characters), so
    "sales_report.csv" would normalize to "sales_report csv" and never match the
    token "sales". Separators are therefore folded to spaces first.
    """
    if not name:
        return ""
    folded = re.sub(r"[_\-.]+", " ", str(name))
    return normalize_text(folded)


def _hint_hit(normalized_text: str, token: str) -> bool:
    """Whole-word hint matching.

    Substring matching is unsafe for short tokens: ``"po"`` (purchase order) matches
    inside "re**po**rt", which classified ordinary sales exports as purchase
    orders. Tokens are therefore compared as whole words, with multiword phrases
    matched as phrases.
    """
    token_norm = _normalize_artifact_name(token)
    if not token_norm:
        return False
    if " " in token_norm:
        return token_norm in normalized_text
    if token_norm in normalized_text.split():
        return True
    # Accept a simple plural/singular mismatch: "quote" must match "quotes".
    for word in normalized_text.split():
        if len(word) - len(token_norm) in (1, 2) and word.startswith(token_norm):
            if word[len(token_norm):] in ("s", "es", "'s"):
                return True
    return False


def _extension_of(filename: str) -> str:
    name = (filename or "").strip().lower()
    if "." not in name:
        return ""
    return "." + name.rsplit(".", 1)[1]


def detect_format(content: bytes, filename: str) -> Optional[ArtifactType]:
    """Detect the *format* from magic bytes, falling back to the extension."""
    head = (content or b"")[:8]
    for magic, kind in _MAGIC:
        if head.startswith(magic):
            # PK covers both xlsx and docx; the extension decides which.
            if kind is ArtifactType.XLSX:
                ext = _extension_of(filename)
                if ext in (".docx", ".doc"):
                    return ArtifactType.DOCX
            if kind is ArtifactType.JSON:
                # A leading '[' or '{' is weak evidence; trust the extension more.
                ext = _extension_of(filename)
                if ext not in (".json",):
                    return None
            return kind
    return _EXTENSION_FORMAT.get(_extension_of(filename))


def _filename_named_kinds(filename: str, sheet_names: Sequence[str]) -> set[ArtifactType]:
    """Artifact kinds explicitly named by the filename or a sheet name."""
    named: set[ArtifactType] = set()
    texts = [_normalize_artifact_name(filename)] + [_normalize_artifact_name(s) for s in sheet_names]
    for text in texts:
        if not text:
            continue
        for tokens, kind, _weight in _FILENAME_HINTS:
            if any(_hint_hit(text, t) for t in tokens):
                named.add(kind)
    return named


def classify_artifact(
    *,
    filename: str = "",
    content: Optional[bytes] = None,
    mime_type: Optional[str] = None,
    size_bytes: Optional[int] = None,
    sheet_names: Sequence[str] = (),
    headers: Sequence[str] = (),
    mapped_roles: Sequence[str] = (),
    document_text: Optional[str] = None,
    known_source_type: Optional[SourceType] = None,
    jev: Optional[Any] = None,
) -> ArtifactClassification:
    """Classify one artifact.

    Content outranks filename. ``mapped_roles`` — the semantic roles the column
    mapper assigned — is the strongest signal available, because it has already
    resolved header ambiguity.
    """
    fmt = detect_format(content or b"", filename)
    notes: list[str] = []
    if fmt is None:
        notes.append("no recognised format from magic bytes or extension")
    elif fmt in (ArtifactType.XLSX, ArtifactType.DOCX) and content:
        notes.append(f"format {fmt.value} confirmed from content signature")

    candidates: dict[ArtifactType, ClassificationCandidate] = {}

    def offer(
        kind: ArtifactType, score: float, reason: str, *, content: bool = False
    ) -> None:
        existing = candidates.get(kind)
        if existing is None:
            candidates[kind] = ClassificationCandidate(kind, score, (reason,), content)
            return
        # Repeated independent signals reinforce; they do not merely add up, so a
        # weak second signal cannot lift a poor first signal into confidence.
        boosted = min(1.0, max(existing.score, score) + 0.1)
        candidates[kind] = ClassificationCandidate(
            kind, boosted, tuple({*existing.reasons, reason}),
            content_supported=existing.content_supported or content,
        )

    # 1. Semantic roles from mapped columns: the strongest evidence available.
    roles = {r for r in mapped_roles if r}
    if roles:
        for kind, (required, forbidden, domain) in _SEMANTIC_RULES.items():
            present = roles & required
            contradicted = roles & forbidden
            # Every required role must be present. Accepting a rule on partial
            # evidence let a sales signature match a purchase-order file, because
            # a lone ``product_name`` satisfied half of the rule.
            if present != required:
                continue
            # Contradicting roles lower the score rather than disqualifying it.
            score = 0.50 + 0.10 * len(present) + (0.05 if forbidden else 0.0)
            if contradicted:
                score -= FORBIDDEN_ROLE_PENALTY
            reasons = [f"mapped roles include {sorted(present)}"]
            if forbidden:
                reasons.append(f"forbidden roles absent: {sorted(forbidden)}")
            if contradicted:
                reasons.append(
                    f"contradicted by {sorted(contradicted)} (penalty applied)"
                )
            offer(kind, score, reasons[0], content=True)
            candidates[kind] = ClassificationCandidate(
                kind, score, tuple(reasons), content_supported=True
            )

    # 2. Document text signals.
    if document_text:
        lowered = normalize_text(document_text)
        for kind, signals in _DOCUMENT_SIGNALS.items():
            hits = [s for s in signals if normalize_text(s) in lowered]
            if hits:
                offer(kind, min(0.9, 0.5 + 0.12 * len(hits)), f"document text contains {hits[:3]}",
                      content=True)

    # 3. Filename hints: weaker than content, applied last.
    lowered_name = _normalize_artifact_name(filename)
    if lowered_name:
        for tokens, kind, weight in _FILENAME_HINTS:
            if any(_hint_hit(lowered_name, t) for t in tokens):
                offer(kind, weight, f"filename contains one of {tokens[:3]}")

    # 4. Sheet names.
    if sheet_names:
        lowered_sheets = [_normalize_artifact_name(s) for s in sheet_names]
        for tokens, kind, weight in _FILENAME_HINTS:
            if any(any(_hint_hit(sheet, t) for t in tokens) for sheet in lowered_sheets):
                offer(kind, weight * 0.9, "a sheet name matches the artifact kind")

    # 5. Known source type is a strong prior.
    if known_source_type is SourceType.SYSTEM_EXPORT:
        for kind, (_, _, _domain) in _SEMANTIC_RULES.items():
            if kind in candidates:
                offer(kind, candidates[kind].score + 0.15, "declared as a system export")

    if fmt in (ArtifactType.PDF, ArtifactType.DOCX, ArtifactType.TEXT) and not document_text:
        notes.append(
            "document format with no extracted text; classification is limited to the "
            "format and filename"
        )

    ranked = sorted(candidates.values(), key=lambda c: (-c.score, c.artifact_type.value))

    if not ranked:
        notes.append("no artifact-kind signal found; reporting UNKNOWN")
        return ArtifactClassification(
            artifact_type=ArtifactType.UNKNOWN,
            confidence=0.0,
            format_type=fmt,
            needs_review=True,
            notes=tuple(notes),
        )

    top = ranked[0]
    runner = ranked[1] if len(ranked) > 1 else None

    if top.score < MIN_ACCEPT_CONFIDENCE:
        notes.append(f"best candidate {top.artifact_type.value} scored only {top.score:.2f}")
        return ArtifactClassification(
            artifact_type=ArtifactType.UNKNOWN,
            confidence=top.score,
            candidates=tuple(ranked[:4]),
            format_type=fmt,
            needs_review=True,
            notes=tuple(notes),
        )

    # Close scores are not a decision. A coin-flip classification is worse than
    # asking for review, because everything downstream inherits the error.
    if runner is not None and (top.score - runner.score) < (AMBIGUITY_MARGIN - _MARGIN_EPSILON):
        # A filename is a deliberate human label. When it names exactly one of the
        # tied candidates it is allowed to break the tie — as a *recorded* decision
        # requiring review, never as a silent one.
        named = _filename_named_kinds(filename, sheet_names)
        tied = {c.artifact_type for c in ranked[:2]}
        decisive = named & tied
        # A filename may break a tie only when its candidate is not losing to a
        # candidate the *content* supports. "inventory_report.xlsx" holding sales
        # columns is a mislabelled sales export, not an inventory report.
        top_content_backed = ranked[0].content_supported
        chosen_backed = next(
            (c.content_supported for c in ranked[:2] if c.artifact_type in decisive), False
        )
        if len(decisive) == 1 and not (top_content_backed and not chosen_backed):
            chosen = next(c for c in ranked[:2] if c.artifact_type in decisive)
            notes.append(
                f"content could not separate {top.artifact_type.value} from "
                f"{runner.artifact_type.value}; the filename named "
                f"{chosen.artifact_type.value}, so it is used and flagged for review"
            )
            return ArtifactClassification(
                artifact_type=chosen.artifact_type,
                domain=domain_for_artifact(chosen.artifact_type),
                confidence=chosen.score,
                candidates=tuple(ranked[:4]),
                ambiguity=(
                    f"{top.artifact_type.value} ({top.score:.2f}) and "
                    f"{runner.artifact_type.value} ({runner.score:.2f}) were close; "
                    "resolved by filename",
                ),
                needs_review=True,
                format_type=fmt,
                notes=tuple(notes),
            )
        ambiguity = (
            f"{top.artifact_type.value} ({top.score:.2f}) and "
            f"{runner.artifact_type.value} ({runner.score:.2f}) are too close to distinguish"
        )
        notes.append("reporting UNKNOWN rather than guessing between close candidates")
        return ArtifactClassification(
            artifact_type=ArtifactType.UNKNOWN,
            confidence=top.score,
            candidates=tuple(ranked[:4]),
            classification_method=DecisionOrigin.DETERMINISTIC,
            ambiguity=(ambiguity,),
            needs_review=True,
            format_type=fmt,
            notes=tuple(notes),
        )

    # Optional bounded judgment, only when determinism could not decide.
    if jev is not None and (runner is not None or top.score < MIN_SEMANTIC_CONFIDENCE):
        judged = _consult_jev(jev, ranked[:4], filename, notes)
        if judged is not None:
            return judged

    if not top.content_supported:
        # No content evidence at all: only the filename. That is a weak claim, so
        # it is never presented as a confident classification.
        notes.append(
            f"classification rests on the filename alone; no content evidence "
            f"supported {top.artifact_type.value}"
        )

    return ArtifactClassification(
        artifact_type=top.artifact_type,
        domain=domain_for_artifact(top.artifact_type),
        confidence=top.score,
        candidates=tuple(ranked[:4]),
        ambiguity=(),
        # A filename-only classification is always flagged, however high it scored.
        needs_review=not top.content_supported or top.score < 0.7,
        format_type=fmt,
        notes=tuple(notes),
    )


def _consult_jev(
    jev: Any, ranked: Sequence[ClassificationCandidate], filename: str, notes: list[str]
) -> Optional[ArtifactClassification]:
    """Ask bounded judgment to choose among already-identified candidates.

    JEV chooses *from* the candidate list; it cannot introduce a type that
    deterministic evidence never raised. A failure leaves determinism in charge.
    """
    try:
        decision = jev.decide_artifact_type(
            candidates=[c.artifact_type.value for c in ranked],
            filename=filename,
        )
    except Exception:
        notes.append("bounded judgment unavailable; kept the deterministic result")
        return None
    if decision is None:
        return None
    chosen = getattr(decision, "choice", None)
    if chosen in (None, "ambiguous", "unknown"):
        return None
    match = next((c for c in ranked if c.artifact_type.value == chosen), None)
    if match is None:
        # Refuse a type deterministic evidence never raised.
        return None
    return ArtifactClassification(
        artifact_type=match.artifact_type,
        domain=domain_for_artifact(match.artifact_type),
        confidence=float(getattr(decision, "confidence", match.score)),
        candidates=tuple(ranked),
        classification_method=DecisionOrigin.JEV,
        ambiguity=(),
        needs_review=True,
        format_type=None,
        notes=tuple(notes + [f"artifact kind chosen by bounded judgment as {chosen!r}"]),
    )