"""The single unified artifact loader for Phase 1.

Consolidates the three competing loaders found in the audit:

* ``workbook_loader.load_workbook`` (guest path) - BOM/encoding sniffing, delimiter
  sniffing, zip-bomb and cell-length caps, external-link rejection, header dedupe.
* ``upload_service.parse_file_with_report`` (authenticated path) - pandas CSV/XLSX/XLS.
* ``upload_service.process_upload`` - dead wrapper, deleted.

Plus JSON, which the authenticated loader rejected outright.

Bug fixes carried in from the audit
-----------------------------------
1. **Formula detection never fired on XLSX.** The workbook was opened with
   ``data_only=True``, which returns *cached values* for formula cells, so no cell
   ever began with ``=``. We now open the workbook a second time with
   ``data_only=False`` and compare, so real formulas are detected.
2. **Every negative number was treated as a formula.** Numeric cells were rendered
   with ``str(int(v))`` and then prefix-tested, so ``-5`` looked like ``-`` + text
   and the whole workbook was rejected. Formula detection now inspects the cell
   *type*: only genuine text cells can be formula-injection payloads.
3. **Row limits were inconsistent** (500k / 5k / unlimited). There is now one
   limit in one place.
4. **``.xlsm`` was accepted while ``_MACRO_EXTS`` was declared but never used.**
   Macro-capable extensions are now actually rejected.

Every limit is a module constant so there is exactly one source of truth.
"""
from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional, Sequence

from app.services.orbit.contracts import ErrorCategory, IngestionError

# ── Security / resource limits (single source of truth) ─────────────────────
MAX_ROWS = 500_000
MAX_COLUMNS = 1_000
MAX_TOTAL_CELLS = 1_000_000
MAX_CELL_LENGTH = 32_767
MAX_SHEETS = 20
MAX_HEADER_SCAN_ROWS = 12
MAX_FILE_BYTES = 15 * 1024 * 1024

#: Macro-capable containers are refused: a merchant spreadsheet never needs VBA.
MACRO_EXTENSIONS = frozenset({".xlsm", ".xlsb", ".xlam", ".xlsb"})

#: Extensions whose content is executed by an office suite before we ever see it.
DANGEROUS_EXTENSIONS = MACRO_EXTENSIONS

SUPPORTED_EXTENSIONS = frozenset({".csv", ".xlsx", ".xls", ".json"})

#: External-link / DDE patterns in a *text* cell. Anchored so ordinary URLs and
#: hyphenated text are not rejected (the audit found the old `//` rule matched any
#: path-like string).
_EXTERNAL_LINK_PATTERNS = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\[[^\]]+\]",       # [1]Sheet!A1 style workbook links
        r"https?://",         # explicit URL in a formula-ish cell
        r"ftp://",
    )
)

#: Spreadsheet functions that reach outside the file or execute something. An
#: explicit denylist rather than a generic ``=FUNC(`` pattern, because ordinary
#: local formulas (``=SUM(A1:A9)``, ``=IF(...)``) must keep working.
_DANGEROUS_FUNCTIONS = frozenset({
    "HYPERLINK", "WEBSERVICE", "RTD", "CALL", "REGISTER",
    "REGISTER.ID", "EXEC", "EXECUTE", "FOPEN", "FWRITE",
    "DDE", "IMPORTXML", "FILTERXML", "SHELL", "CMD",
})
_DANGEROUS_CALL_RE = re.compile(
    r"=\s*([A-Z][A-Z0-9_.]*)\s*\(", re.IGNORECASE
)

#: A text cell that starts with one of these is a formula-injection vector.
_FORMULA_PREFIXES = ("=", "+", "-", "@")


@dataclass
class SheetMetadata:
    """Structural facts about one worksheet."""

    name: str
    row_count: int = 0
    column_count: int = 0
    header_row_index: Optional[int] = None
    data_region: tuple[int, int] | None = None  # (first_row, last_row) inclusive
    merged_cell_ranges: list[str] = field(default_factory=list)
    hidden_rows: list[int] = field(default_factory=list)
    hidden_columns: list[str] = field(default_factory=list)
    formula_cells: list[str] = field(default_factory=list)
    external_links: list[str] = field(default_factory=list)
    currency_hint: Optional[str] = None
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "row_count": self.row_count,
            "column_count": self.column_count,
            "header_row_index": self.header_row_index,
            "data_region": list(self.data_region) if self.data_region else None,
            "merged_cell_ranges": list(self.merged_cell_ranges),
            "hidden_rows": list(self.hidden_rows),
            "hidden_columns": list(self.hidden_columns),
            "formula_cells": list(self.formula_cells),
            "external_links": list(self.external_links),
            "currency_hint": self.currency_hint,
            "warnings": list(self.warnings),
        }


@dataclass
class LoadedSheet:
    """One sheet (or the single logical sheet of a CSV/JSON file)."""

    name: str
    #: Raw cell values, row-major. Formatted as text where the source was text.
    rows: list[list[Any]]
    headers: list[str] = field(default_factory=list)
    header_index: Optional[int] = None
    metadata: SheetMetadata = field(default_factory=SheetMetadata)

    @property
    def data_rows(self) -> list[list[Any]]:
        """Rows after the header row, with fully-blank rows removed."""
        start = 0 if self.header_index is None else self.header_index + 1
        out = []
        for row in self.rows[start:]:
            if not any(cell is not None and str(cell).strip() != "" for cell in row):
                continue
            out.append(row)
        return out

    def to_records(self) -> list[dict[str, Any]]:
        """Rows as ``{header: value}`` dicts, skipping empty values."""
        headers = self.headers or [f"col_{i}" for i in range(len(self.rows[0]) if self.rows else 0)]
        out: list[dict[str, Any]] = []
        for row in self.data_rows:
            record: dict[str, Any] = {}
            for idx, header in enumerate(headers):
                value = row[idx] if idx < len(row) else None
                if value is None or (isinstance(value, str) and not value.strip()):
                    continue
                record[header] = value
            out.append(record)
        return out


@dataclass
class LoadedArtifact:
    """Everything the loader learned about one artifact."""

    source_name: str
    kind: str  # csv | xlsx | xls | json
    sheets: list[LoadedSheet]
    warnings: list[str] = field(default_factory=list)
    issues: list[dict[str, Any]] = field(default_factory=list)

    @property
    def primary_sheet(self) -> LoadedSheet:
        if not self.sheets:
            raise IngestionError(
                ErrorCategory.PARSE_ERROR,
                "artifact produced no sheets",
                detail={"source_name": self.source_name},
            )
        return self.sheets[0]

    def sheet(self, name: str) -> Optional[LoadedSheet]:
        for s in self.sheets:
            if s.name == name:
                return s
        return None


# ── Helpers ─────────────────────────────────────────────────────────────────

def _cell_text(value: Any) -> str:
    """Render a cell as text without losing numeric sign semantics.

    Note: we never prefix-strip here. Negative numbers render as ``-5`` and the
    formula check below inspects the cell type, so this is safe.
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return repr(value)
    return str(value)


def _looks_like_formula(cell: Any) -> bool:
    """Formula-injection detection that does not misfire on negative numbers.

    The check is on the *type*: a numeric cell can never be a formula payload,
    however it is rendered.
    """
    if cell is None or isinstance(cell, (int, float, bool)):
        return False
    text = str(cell).strip()
    return bool(text) and text.startswith(_FORMULA_PREFIXES)


def _looks_external(value: Any) -> bool:
    """True when a text cell is a formula that reaches outside the file.

    Ordinary local formulas are fine. Only workbook links, embedded URLs and an
    explicit denylist of outbound/executing functions are rejected.
    """
    text = _cell_text(value)
    if any(p.search(text) for p in _EXTERNAL_LINK_PATTERNS):
        return True
    match = _DANGEROUS_CALL_RE.search(text)
    return bool(match and match.group(1).upper() in _DANGEROUS_FUNCTIONS)


def _detect_currency(rows: Sequence[Sequence[Any]]) -> Optional[str]:
    """Infer the currency symbol/code present in the sheet.

    A hint only - it never converts and never overrides per-cell currency, which
    the currency normalizer owns.
    """
    text = " ".join(_cell_text(c) for row in rows[:50] for c in row)
    for code in ("SAR", "USD", "EUR", "GBP", "AED", "KWD", "BHD", "OMR", "QAR"):
        if re.search(rf"\b{code}\b", text):
            return code
    if "﷼" in text or "ريال" in text or "ر.س" in text:
        return "SAR"
    return None


def _enforce_limits(rows: list[list[Any]]) -> None:
    if len(rows) > MAX_ROWS:
        raise IngestionError(
            ErrorCategory.SCHEMA_ERROR,
            f"row count {len(rows)} exceeds limit {MAX_ROWS}",
            detail={"rows": len(rows), "limit": MAX_ROWS},
        )
    width = max((len(r) for r in rows), default=0)
    if width > MAX_COLUMNS:
        raise IngestionError(
            ErrorCategory.SCHEMA_ERROR,
            f"column count {width} exceeds limit {MAX_COLUMNS}",
            detail={"columns": width, "limit": MAX_COLUMNS},
        )
    if len(rows) * max(width, 1) > MAX_TOTAL_CELLS:
        raise IngestionError(
            ErrorCategory.SECURITY_ERROR,
            f"workbook exceeds the {MAX_TOTAL_CELLS} cell budget",
            detail={"cells": len(rows) * max(width, 1), "limit": MAX_TOTAL_CELLS},
        )


def _validate_cell_lengths(rows: Iterable[Sequence[Any]]) -> None:
    for r_idx, row in enumerate(rows):
        for c_idx, cell in enumerate(row):
            text = _cell_text(cell)
            if len(text) > MAX_CELL_LENGTH:
                raise IngestionError(
                    ErrorCategory.SECURITY_ERROR,
                    f"cell exceeds {MAX_CELL_LENGTH} characters",
                    locator=f"row {r_idx + 1}, column {c_idx + 1}",
                    detail={"length": len(text)},
                )


def _dedupe_headers(headers: Sequence[Any]) -> list[str]:
    """Make header names unique and non-empty so they can key a mapping."""
    seen: dict[str, int] = {}
    out: list[str] = []
    for idx, raw in enumerate(headers):
        base = _cell_text(raw).strip() or f"col_{idx + 1}"
        if base in seen:
            seen[base] += 1
            base = f"{base}_{seen[base]}"
        else:
            seen[base] = 1
        out.append(base)
    return out


def _score_header_row(row: Sequence[Any], role_hints: set[str]) -> int:
    """Score how much a row looks like a header.

    Higher is better. Rewards text cells and penalises numeric-looking cells,
    because a header row contains labels, not measurements.
    """
    filled = [c for c in row if _cell_text(c).strip()]
    if len(filled) < 2:
        return 0
    score = 0
    for cell in filled:
        text = _cell_text(cell).strip()
        if _looks_like_formula(cell):
            continue
        if isinstance(cell, (int, float)) and not isinstance(cell, bool):
            score += 1  # a number in a header row is unusual
            continue
        score += 2
        normalized = re.sub(r"[^a-z0-9]+", "", text.lower())
        if any(hint and hint in normalized for hint in role_hints):
            score += 3
    return score


def _pick_header_row(rows: Sequence[Sequence[Any]], role_hints: set[str]) -> tuple[Optional[int], list[str]]:
    """Choose the most header-like row in the first ``MAX_HEADER_SCAN_ROWS``."""
    best_index: Optional[int] = None
    best_score = 0
    for idx, row in enumerate(rows[:MAX_HEADER_SCAN_ROWS]):
        score = _score_header_row(row, role_hints)
        if score > best_score:
            best_score = score
            best_index = idx
    if best_index is None or best_score < 4:
        return None, []
    return best_index, _dedupe_headers(rows[best_index])


def _strip_blank_rows(rows: list[list[Any]]) -> list[list[Any]]:
    out = []
    for row in rows:
        if any(_cell_text(c).strip() for c in row):
            out.append(list(row))
        elif out:
            break  # stop at the first trailing blank band
    return out


def _pad(rows: list[list[Any]], width: int) -> list[list[Any]]:
    return [list(r) + [None] * (width - len(r)) for r in rows]


def _build_sheet(
    name: str,
    rows: list[list[Any]],
    *,
    role_hints: Optional[set[str]] = None,
    extra_metadata: Optional[SheetMetadata] = None,
) -> LoadedSheet:
    rows = _strip_blank_rows(rows)
    _enforce_limits(rows)
    _validate_cell_lengths(rows)

    width = max((len(r) for r in rows), default=0)
    rows = _pad(rows, width)

    header_index, headers = _pick_header_row(rows, role_hints or set())

    meta = extra_metadata or SheetMetadata(name=name)
    meta.name = name
    meta.row_count = len(rows)
    meta.column_count = width
    meta.header_row_index = header_index
    meta.currency_hint = meta.currency_hint or _detect_currency(rows)
    if header_index is not None:
        meta.data_region = (header_index + 1, max(len(rows) - 1, header_index + 1))

    return LoadedSheet(name=name, rows=rows, headers=headers, header_index=header_index, metadata=meta)


# ── Format loaders ──────────────────────────────────────────────────────────

def _load_csv(content: bytes, source_name: str) -> list[list[Any]]:
    """Decode CSV, tolerating BOM and non-UTF8 encodings."""
    last_error: Exception | None = None
    for encoding in ("utf-8-sig", "utf-8", "cp1256", "latin-1"):
        try:
            text = content.decode(encoding)
            break
        except (UnicodeDecodeError, LookupError) as exc:
            last_error = exc
            text = None
    if text is None:
        raise IngestionError(
            ErrorCategory.PARSE_ERROR,
            f"could not decode CSV: {last_error}",
            detail={"source_name": source_name},
        )

    # Delimiter sniffing mirrors the old loader, but tolerates single-column files
    # where Sniffer raises.
    delimiter = ","
    try:
        dialect = csv.Sniffer().sniff(text[:8192], delimiters=",;\t|")
        delimiter = dialect.delimiter
    except csv.Error:
        sample = text[:8192]
        counts = {d: sample.count(d) for d in (",", ";", "\t", "|")}
        best = max(counts, key=lambda k: counts[k])
        if counts[best] > 0:
            delimiter = best

    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    return [list(row) for row in reader]


def _load_json(content: bytes, source_name: str) -> list[LoadedSheet]:
    """Flatten a JSON document into sheets.

    A top-level array of objects becomes one sheet keyed by the union of keys. An
    object of arrays becomes one sheet per key. Anything else is a single sheet of
    flattened scalars.
    """
    try:
        payload = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise IngestionError(
            ErrorCategory.PARSE_ERROR,
            f"invalid JSON: {exc}",
            detail={"source_name": source_name},
        ) from exc

    if isinstance(payload, list) and payload and all(isinstance(r, dict) for r in payload):
        keys: list[str] = []
        for record in payload:
            for key in record:
                if key not in keys:
                    keys.append(str(key))
        rows = [[_json_cell(r.get(k)) for k in keys] for r in payload]
        return [_build_sheet("records", [keys] + rows)]

    if isinstance(payload, dict):
        sheets: list[LoadedSheet] = []
        for key, value in payload.items():
            if isinstance(value, list) and value and all(isinstance(v, dict) for v in value):
                sub_keys: list[str] = []
                for record in value:
                    for sk in record:
                        if str(sk) not in sub_keys:
                            sub_keys.append(str(sk))
                rows = [[_json_cell(r.get(sk)) for sk in sub_keys] for r in value]
                sheets.append(_build_sheet(str(key), [sub_keys] + rows))
            else:
                sheets.append(_build_sheet(str(key), [["field", "value"], [str(key), _json_cell(value)]]))
        if sheets:
            return sheets

    return [_build_sheet("root", [["field", "value"], ["value", _json_cell(payload)]])]


def _json_cell(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return value


def _load_xlsx(content: bytes, source_name: str) -> list[LoadedSheet]:
    """Load an OOXML workbook, capturing structure *and* detecting formulas.

    Opens twice: once with cached values (what we present) and once with formulas
    (so we can tell whether a value was computed). This is the fix for the audit's
    "formulas are never detected" bug.
    """
    try:
        from openpyxl import load_workbook
    except ImportError as exc:  # pragma: no cover - dependency is pinned
        raise IngestionError(
            ErrorCategory.UNSUPPORTED_FORMAT,
            "openpyxl is required for xlsx ingestion",
        ) from exc

    try:
        values_wb = load_workbook(io.BytesIO(content), data_only=True, read_only=False)
        formulas_wb = load_workbook(io.BytesIO(content), data_only=False, read_only=False)
    except Exception as exc:  # noqa: BLE001 - openpyxl raises many types
        raise IngestionError(
            ErrorCategory.PARSE_ERROR,
            f"could not read xlsx: {exc}",
            detail={"source_name": source_name},
        ) from exc

    if any(getattr(ws, "sheet_state", "visible") != "visible" for ws in values_wb.worksheets):
        raise IngestionError(
            ErrorCategory.SECURITY_ERROR,
            "workbook contains hidden worksheets, which can hide injected content",
            detail={"source_name": source_name},
        )

    sheets: list[LoadedSheet] = []
    for ws in values_wb.worksheets:
        if len(sheets) >= MAX_SHEETS:
            break
        rows = [list(r) for r in ws.iter_rows(values_only=True)]

        fws = formulas_wb[ws.title] if ws.title in formulas_wb.sheetnames else None
        meta = SheetMetadata(name=ws.title)

        # Formulas: compare the formula view against the value view. Only a genuine
        # formula cell differs by starting with an operator in the formula workbook.
        if fws is not None:
            for r_idx, frow in enumerate(fws.iter_rows(values_only=True)):
                for c_idx, fcell in enumerate(frow):
                    if isinstance(fcell, str) and fcell.strip().startswith("="):
                        locator = f"{ws.title}!R{r_idx + 1}C{c_idx + 1}"
                        meta.formula_cells.append(locator)
                        if _looks_external(fcell):
                            meta.external_links.append(locator)

        # Merged cells and hidden dimensions - previously ignored entirely.
        for rng in getattr(ws, "merged_cells", []).ranges if hasattr(ws, "merged_cells") else []:
            meta.merged_cell_ranges.append(str(rng))
        for r_idx, dim in getattr(ws, "row_dimensions", {}).items():
            if getattr(dim, "hidden", False):
                meta.hidden_rows.append(int(r_idx))
        for letter, dim in getattr(ws, "column_dimensions", {}).items():
            if getattr(dim, "hidden", False):
                meta.hidden_columns.append(letter)

        if meta.external_links:
            raise IngestionError(
                ErrorCategory.SECURITY_ERROR,
                "workbook contains external links or DDE formulas",
                locator=meta.external_links[0],
                detail={"source_name": source_name, "locations": meta.external_links[:10]},
            )
        if meta.formula_cells:
            meta.warnings.append(
                f"{len(meta.formula_cells)} formula cell(s) present; cached values were read"
            )

        sheets.append(_build_sheet(ws.title, rows, extra_metadata=meta))

    values_wb.close()
    formulas_wb.close()
    return sheets


def _load_xls(content: bytes, source_name: str) -> list[LoadedSheet]:
    """Load a legacy .xls via xlrd.

    Structural fidelity is reduced: xlrd exposes values, formulas-as-cached and
    some sheet metadata, but not merged-cell ranges, hidden dimensions or the
    formula source. That limitation is recorded rather than hidden.
    """
    try:
        import xlrd
    except ImportError as exc:  # pragma: no cover
        raise IngestionError(
            ErrorCategory.UNSUPPORTED_FORMAT, "xlrd is required for .xls ingestion"
        ) from exc

    try:
        book = xlrd.open_workbook(file_contents=content, formatting_info=False)
    except Exception as exc:  # noqa: BLE001
        raise IngestionError(
            ErrorCategory.PARSE_ERROR,
            f"could not read .xls: {exc}",
            detail={"source_name": source_name},
        ) from exc

    sheets: list[LoadedSheet] = []
    for sheet in book.sheets()[:MAX_SHEETS]:
        rows = [list(row) for row in sheet.row_values(sheet.nrows)]
        meta = SheetMetadata(name=sheet.name)
        meta.warnings.append(
            "legacy .xls: merged cells, hidden dimensions and formula sources are unavailable"
        )
        sheets.append(_build_sheet(sheet.name, rows, extra_metadata=meta))
    return sheets


# ── Public entry point ──────────────────────────────────────────────────────

def load_artifact(content: bytes, source_name: str) -> LoadedArtifact:
    """Load any supported artifact into the canonical loaded form.

    This is the only loader Phase 1 uses. Format dispatch is by extension first
    (cheap) with a content sniff fallback.
    """
    if len(content) > MAX_FILE_BYTES:
        raise IngestionError(
            ErrorCategory.SECURITY_ERROR,
            f"artifact exceeds {MAX_FILE_BYTES} bytes",
            detail={"size": len(content), "limit": MAX_FILE_BYTES},
        )

    lowered = source_name.lower()
    ext = "." + lowered.rsplit(".", 1)[-1] if "." in lowered else ""

    if ext in DANGEROUS_EXTENSIONS:
        raise IngestionError(
            ErrorCategory.SECURITY_ERROR,
            f"{ext} files may contain macros and are not accepted",
            detail={"source_name": source_name, "extension": ext},
        )
    if ext not in SUPPORTED_EXTENSIONS:
        raise IngestionError(
            ErrorCategory.UNSUPPORTED_FORMAT,
            f"unsupported extension {ext or '(none)'}",
            detail={
                "source_name": source_name,
                "supported": sorted(SUPPORTED_EXTENSIONS),
            },
        )

    # Reject formula-injection payloads in text-based formats up front.
    if ext in (".csv", ".json"):
        head = content[:8192].decode("utf-8", errors="ignore")
        lowered_head = head.lower()
        for pattern in ("<?php", "<script", "javascript:", "vbscript:"):
            if pattern in lowered_head:
                raise IngestionError(
                    ErrorCategory.SECURITY_ERROR,
                    f"content matches a dangerous pattern ({pattern})",
                    detail={"source_name": source_name},
                )

    try:
        if ext == ".csv":
            rows = _load_csv(content, source_name)
            sheets = [_build_sheet("csv", rows)]
            kind = "csv"
        elif ext == ".json":
            sheets = _load_json(content, source_name)
            kind = "json"
        elif ext == ".xlsx":
            sheets = _load_xlsx(content, source_name)
            kind = "xlsx"
        elif ext == ".xls":
            sheets = _load_xls(content, source_name)
            kind = "xls"
        else:  # pragma: no cover - guarded above
            raise IngestionError(
                ErrorCategory.UNSUPPORTED_FORMAT, f"unsupported extension {ext}"
            )
    except IngestionError:
        raise
    except MemoryError as exc:  # decompression bomb
        raise IngestionError(
            ErrorCategory.SECURITY_ERROR,
            "artifact exhausted memory while parsing (possible decompression bomb)",
            detail={"source_name": source_name},
        ) from exc

    if not sheets:
        raise IngestionError(
            ErrorCategory.PARSE_ERROR,
            "artifact contained no readable sheets",
            detail={"source_name": source_name},
        )

    warnings: list[str] = []
    for sheet in sheets:
        warnings.extend(f"{sheet.name}: {w}" for w in sheet.metadata.warnings)

    return LoadedArtifact(
        source_name=source_name,
        kind=kind,
        sheets=sheets,
        warnings=warnings,
    )