"""Deterministic document extraction for business documents (spec §11).

PDF, DOCX and plain-text extraction with **full source location** on every
extracted item, so any canonical number can be traced back to a page, table, row,
column or character offset.

No LLM is involved. Extraction is mechanical:
- PDF: ``pdfplumber`` for text, tables and layout-derived numbers.
- DOCX: ``python-docx`` for paragraphs, tables and core metadata.

Scope and honesty
------------------
* **OCR is not implemented.** A scanned PDF yields no text and is reported as
  ``EXTRACTION_EMPTY`` with a limitation, rather than being guessed at. Low-
  confidence OCR must never be treated as unquestioned truth, and we do not have
  an OCR engine in this phase.
* **Field classification is deliberately conservative.** We extract labelled
  fields (invoice number, dates, totals, currency) using explicit patterns. A
  field we cannot identify confidently is recorded as an *unclassified line* with
  its text and locator, never silently mapped onto a business semantic.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from app.services.orbit.contracts import (
    ErrorCategory,
    ExtractionMethod,
    IngestionError,
    SourceLocator,
    normalize_text,
)

#: Label patterns for high-value business identifiers. Deliberately explicit —
#: an unmatched label produces an unclassified line, never a guessed field.
_LABELED_FIELD_PATTERNS: dict[str, tuple[str, ...]] = {
    "invoice_number": (r"invoice\s*(?:no|number|#|num)", r"فاتورة"),
    "purchase_order_number": (r"(?:purchase\s*order|po)\s*(?:no|number|#|num)", r"أمر\s*شراء"),
    "quote_number": (r"(?:quotation|quote)\s*(?:no|number|#|num)", r"عرض\s*سعر"),
    "contract_number": (r"contract\s*(?:no|number|#|ref)", r"عقد"),
    "supplier_name": (r"supplier|vendor|from|غير", r"مورد", r"المورد"),
    "customer_name": (r"bill\s*to|customer|ship\s*to", r"عميل"),
    "invoice_date": (r"invoice\s*date|date\s*issued|issue\s*date", r"تاريخ"),
    "due_date": (r"due\s*date|payment\s*due", r"تاريخ\s*الاستحقاق"),
    "total": (r"grand\s*total|^total|total\s*due|amount\s*due", r"المجموع", r"الإجمالي"),
    "subtotal": (r"sub\s*total|subtotal", r"المجموع\s*الفرعي"),
    "tax": (r"tax|vat| vat\b", r"ضريبة", r"الضريبة"),
    "currency": (r"currency", r"عملة"),
}

_AMOUNT_RE = re.compile(r"(?P<cur>SAR|USD|EUR|GBP|AED|﷼|ر\.?س\.?)?\s*(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)")

_DATE_PATTERNS = (
    re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"),
    re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b"),
)


@dataclass
class ExtractedField:
    """One labelled value found in a document, with its location."""

    field_name: str
    raw_value: str
    normalized_value: Optional[str]
    confidence: float
    locator: SourceLocator
    method: ExtractionMethod = ExtractionMethod.DOCUMENT_TEXT
    is_currency: Optional[str] = None
    is_amount: Optional[Decimal] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "field_name": self.field_name,
            "raw_value": self.raw_value,
            "normalized_value": self.normalized_value,
            "confidence": self.confidence,
            "locator": self.locator.to_dict(),
            "method": self.method.value,
            "currency": self.is_currency,
            "amount": None if self.is_amount is None else float(self.is_amount),
        }


@dataclass
class ExtractedTable:
    """A table found in a document."""

    table_index: int
    page: Optional[int]
    rows: list[list[str]]
    locator: SourceLocator

    @property
    def row_count(self) -> int:
        return len(self.rows)

    @property
    def column_count(self) -> int:
        return max((len(r) for r in self.rows), default=0)

    def to_dict(self) -> dict[str, Any]:
        return {
            "table_index": self.table_index,
            "page": self.page,
            "row_count": self.row_count,
            "column_count": self.column_count,
            "locator": self.locator.to_dict(),
            "rows": self.rows,
        }


@dataclass
class ExtractedDocument:
    """Everything extracted from one document."""

    source_name: str
    doc_type: str  # pdf | docx | text
    pages: int = 0
    text: str = ""
    fields: list[ExtractedField] = field(default_factory=list)
    tables: list[ExtractedTable] = field(default_factory=list)
    unclassified_lines: list[ExtractedField] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    limitations: list[str] = field(default_factory=list)
    is_empty: bool = False

    def field_value(self, name: str) -> Optional[str]:
        for f in self.fields:
            if f.field_name == name:
                return f.normalized_value
        return None

    def amount_field(self, name: str) -> Optional[Decimal]:
        for f in self.fields:
            if f.field_name == name:
                return f.is_amount
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_name": self.source_name,
            "doc_type": self.doc_type,
            "pages": self.pages,
            "text_length": len(self.text),
            "fields": [f.to_dict() for f in self.fields],
            "tables": [t.to_dict() for t in self.tables],
            "unclassified_line_count": len(self.unclassified_lines),
            "metadata": dict(self.metadata),
            "limitations": list(self.limitations),
            "is_empty": self.is_empty,
        }


# ── Field classification ────────────────────────────────────────────────────

def _compile_patterns() -> dict[str, re.Pattern[str]]:
    return {
        name: re.compile("|".join(patterns), re.IGNORECASE)
        for name, patterns in _LABELED_FIELD_PATTERNS.items()
    }


_COMPILED = _compile_patterns()


def _find_dates(text: str) -> list[str]:
    found: list[str] = []
    for pattern in _DATE_PATTERNS:
        found.extend(m.group(0) for m in pattern.finditer(text))
    return found


#: Only these fields may carry a monetary amount. Without this, the first number
#: after any label is scraped, so an invoice number or a year would be reported as
#: a currency amount.
_MONEY_FIELDS = frozenset({"total", "subtotal", "tax"})

#: Words that are document *titles* rather than values. "TAX INVOICE" and
#: "Supplier Quotation" both contain a real label but the label is not the value,
#: so a match whose tail is one of these is a title, not a field.
_LABEL_WORDS = frozenset({
    "invoice", "tax", "quote", "quotation", "statement", "order",
    "purchase", "receipt", "supplier", "vendor", "bill", "total",
    "subtotal", "sub total", "amount", "date", "currency", "item",
    "description", "qty", "quantity", "unit", "price", "net", "gross",
    "credit", "debit", "balance", "due", "notes", "terms",
})


def _is_title_word(text: str) -> bool:
    normalized = normalize_text(text)
    return normalized in _LABEL_WORDS


def _extract_fields_from_line(
    line: str,
    *,
    page: Optional[int],
    line_no: int,
    text_offset: int,
) -> tuple[list[ExtractedField], Optional[ExtractedField]]:
    """Classify one line into labelled fields, or return it unclassified.

    A line is matched against explicit label patterns. The first label hit on the
    line becomes the field; a line with a date but no recognised label still
    contributes an ``unclassified`` entry so nothing disappears silently.
    """
    normalized = normalize_text(line)
    if not normalized:
        return [], None

    results: list[ExtractedField] = []
    matched_fields: set[str] = set()

    for name, pattern in _COMPILED.items():
        if name in matched_fields:
            continue
        match = pattern.search(line)
        if not match:
            continue
        # The value is whatever follows the label on this line.
        tail = line[match.end():].strip(" :=\t")
        if not tail:
            continue
        # "TAX INVOICE" / "Supplier Quotation": the label is part of a title, and
        # the tail is another label word rather than a value.
        if _is_title_word(tail):
            continue
        amount: Optional[Decimal] = None
        currency: Optional[str] = None
        if name in _MONEY_FIELDS:
            amount_match = _AMOUNT_RE.search(tail)
            if amount_match:
                currency = amount_match.group("cur")
                try:
                    amount = Decimal(amount_match.group("num").replace(",", ""))
                except InvalidOperation:
                    amount = None
        results.append(
            ExtractedField(
                field_name=name,
                raw_value=line.strip(),
                normalized_value=tail[:200],
                confidence=0.85 if amount is not None else 0.7,
                locator=SourceLocator(
                    page=page, row=line_no, char_offset=text_offset, locator=line.strip()[:120]
                ),
                is_currency=currency,
                is_amount=amount,
            )
        )
        matched_fields.add(name)

    if results:
        return results, None

    # Unrecognised but non-trivial line: keep it rather than discarding it.
    if len(normalized) > 3 and not _is_pure_number(normalized):
        return [], ExtractedField(
            field_name="unclassified",
            raw_value=line.strip(),
            normalized_value=normalized[:200],
            confidence=0.3,
            locator=SourceLocator(page=page, row=line_no, char_offset=text_offset),
        )
    return [], None


def _is_pure_number(text: str) -> bool:
    return bool(re.fullmatch(r"[\d.,\s%﷼$€£]+", text))


def _table_from_rows(rows: list[list[str]], index: int, page: Optional[int]) -> ExtractedTable:
    cleaned = [[(c or "").strip() for c in row] for row in rows if any((c or "").strip() for c in row)]
    return ExtractedTable(
        table_index=index,
        page=page,
        rows=cleaned,
        locator=SourceLocator(table=index, page=page, locator=f"table {index}"),
    )



# ── PDF ─────────────────────────────────────────────────────────────────────

def _extract_pdf(content: bytes, source_name: str) -> ExtractedDocument:
    try:
        import pdfplumber
    except ImportError as exc:  # pragma: no cover - pinned dependency
        raise IngestionError(
            ErrorCategory.UNSUPPORTED_FORMAT, "pdfplumber is required for PDF ingestion"
        ) from exc

    doc = ExtractedDocument(source_name=source_name, doc_type="pdf")
    text_parts: list[str] = []
    offset = 0
    table_index = 0

    try:
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            doc.pages = len(pdf.pages)
            for page_no, page in enumerate(pdf.pages, start=1):
                page_text = page.extract_text() or ""
                if page_text:
                    text_parts.append(page_text)
                for line_no, line in enumerate(page_text.splitlines(), start=1):
                    fields, unclassified = _extract_fields_from_line(
                        line, page=page_no, line_no=line_no, text_offset=offset + len(line)
                    )
                    doc.fields.extend(fields)
                    if unclassified is not None:
                        doc.unclassified_lines.append(unclassified)
                try:
                    tables = page.extract_tables() or []
                except Exception:  # noqa: BLE001 - pdfplumber table extraction is fragile
                    tables = []
                for rows in tables:
                    doc.tables.append(_table_from_rows(rows, table_index, page_no))
                    table_index += 1
                offset += len(page_text)
            doc.metadata = {k: str(v) for k, v in (pdf.metadata or {}).items() if v}
    except IngestionError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise IngestionError(
            ErrorCategory.PARSE_ERROR,
            f"could not read PDF: {exc}",
            detail={"source_name": source_name},
        ) from exc

    doc.text = "\n".join(text_parts)
    if not doc.text.strip():
        doc.is_empty = True
        doc.limitations.append(
            "no extractable text layer (likely a scanned document); "
            "OCR is not implemented in this phase, so no values were inferred"
        )
    return doc


# ── DOCX ────────────────────────────────────────────────────────────────────

def _extract_docx(content: bytes, source_name: str) -> ExtractedDocument:
    try:
        import docx  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise IngestionError(
            ErrorCategory.UNSUPPORTED_FORMAT, "python-docx is required for DOCX ingestion"
        ) from exc

    doc = ExtractedDocument(source_name=source_name, doc_type="docx")
    try:
        document = docx.Document(io.BytesIO(content))
    except Exception as exc:  # noqa: BLE001
        raise IngestionError(
            ErrorCategory.PARSE_ERROR,
            f"could not read DOCX: {exc}",
            detail={"source_name": source_name},
        ) from exc

    offset = 0
    for line_no, para in enumerate(document.paragraphs, start=1):
        text = para.text or ""
        if not text.strip():
            continue
        fields, unclassified = _extract_fields_from_line(
            text, page=None, line_no=line_no, text_offset=offset
        )
        doc.fields.extend(fields)
        if unclassified is not None:
            doc.unclassified_lines.append(unclassified)
        offset += len(text)

    for table_index, table in enumerate(document.tables):
        rows = [[cell.text for cell in row.cells] for row in table.rows]
        doc.tables.append(_table_from_rows(rows, table_index, None))

    props = document.core_properties
    doc.metadata = {
        k: str(v)
        for k, v in {
            "author": props.author,
            "title": props.title,
            "subject": props.subject,
            "created": props.created,
            "modified": props.modified,
        }.items()
        if v
    }

    doc.text = "\n".join(p.text for p in document.paragraphs if p.text)
    if not doc.text.strip() and not doc.tables:
        doc.is_empty = True
        doc.limitations.append("DOCX contained no paragraphs or tables")
    return doc


# ── Plain text ──────────────────────────────────────────────────────────────

def _extract_text(content: bytes, source_name: str) -> ExtractedDocument:
    text = ""
    for encoding in ("utf-8-sig", "utf-8", "cp1256", "latin-1"):
        try:
            text = content.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    doc = ExtractedDocument(source_name=source_name, doc_type="text", text=text)
    offset = 0
    for line_no, line in enumerate(text.splitlines(), start=1):
        fields, unclassified = _extract_fields_from_line(
            line, page=None, line_no=line_no, text_offset=offset
        )
        doc.fields.extend(fields)
        if unclassified is not None:
            doc.unclassified_lines.append(unclassified)
        offset += len(line) + 1
    if not text.strip():
        doc.is_empty = True
        doc.limitations.append("text artifact was empty")
    return doc


# ── Public entry point ──────────────────────────────────────────────────────

def extract_document(content: bytes, source_name: str) -> ExtractedDocument:
    """Extract a PDF / DOCX / text artifact deterministically.

    Every extracted item carries a :class:`SourceLocator` so a canonical value can
    be traced back to a page, row, column or character offset.
    """
    lowered = source_name.lower()
    ext = "." + lowered.rsplit(".", 1)[-1] if "." in lowered else ""

    if ext == ".pdf" or content[:5] == b"%PDF-":
        return _extract_pdf(content, source_name)
    if ext == ".docx":
        return _extract_docx(content, source_name)
    if ext in (".txt", ".md", ".text"):
        return _extract_text(content, source_name)

    # DOCX and OOXML are zip containers; sniff before giving up.
    if content[:2] == b"PK":
        try:
            return _extract_docx(content, source_name)
        except IngestionError:
            raise
        except Exception:  # noqa: BLE001
            pass

    raise IngestionError(
        ErrorCategory.UNSUPPORTED_FORMAT,
        f"no document extractor for {ext or '(unknown)'}",
        detail={"source_name": source_name, "supported": ["pdf", "docx", "txt", "md"]},
    )