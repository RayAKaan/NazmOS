/**
 * Client-side schema detector — TypeScript port of backend/app/services/schema_detector.py.
 *
 * Detects column mappings for 17 target fields using name hints + sample value scoring.
 * Used when USE_CLIENT_ETL=true so the browser does the parsing instead of server-side pandas.
 */

import Papa from "papaparse";
import {
  TARGET_COLUMNS,
  COLUMN_ALIASES,
  type TargetColumn,
  type UploadResult,
} from "@/types/upload";

// ---------------------------------------------------------------------------
// Text cleaning (mirrors Python _clean)
// ---------------------------------------------------------------------------
function clean(name: string): string {
  return name.toLowerCase().trim().replace(/[\s-]+/g, "_");
}

// ---------------------------------------------------------------------------
// Levenshtein similarity
// ---------------------------------------------------------------------------
function levenshteinSimilarity(a: string, b: string): number {
  if (!a.length || !b.length) return 1.0;
  const la = a.length;
  const lb = b.length;
  const d: number[][] = Array.from({ length: la + 1 }, () => Array(lb + 1).fill(0));
  for (let i = 0; i <= la; i++) d[i][0] = i;
  for (let j = 0; j <= lb; j++) d[0][j] = j;
  for (let i = 1; i <= la; i++) {
    for (let j = 1; j <= lb; j++) {
      const cost = a[i - 1] === b[j - 1] ? 0 : 1;
      d[i][j] = Math.min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + cost);
    }
  }
  return 1 - d[la][lb] / Math.max(la, lb);
}

// ---------------------------------------------------------------------------
// Name similarity — exact substring or fuzzy Levenshtein > 0.82
// ---------------------------------------------------------------------------
function nameSimilarity(colName: string, hints: string[]): number {
  const c = clean(colName);
  for (const hint of hints) {
    const h = clean(hint);
    if (c.includes(h) || h.includes(c)) return 1.0;
    if (levenshteinSimilarity(c, h) > 0.82) return 0.82;
  }
  return 0.0;
}

// ---------------------------------------------------------------------------
// Sample validators
// ---------------------------------------------------------------------------
const DATE_REGEX = [
  /^\d{4}-\d{2}-\d{2}/,          // 2024-01-15
  /^\d{2}\/\d{2}\/\d{4}/,       // 15/01/2024
  /^\d{2}-\d{2}-\d{4}/,         // 15-01-2024
  /^\d{2}-[A-Za-z]{3}-\d{4}/,   // 15-Jan-2024
  /^\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}/, // 15 January 2024
  /^\d{4}\/\d{2}\/\d{2}/,       // 2024/01/15
];

function isDateLike(value: unknown): boolean {
  if (value instanceof Date) return true;
  if (typeof value === "number" && value > 20000 && value < 60000) return true; // Excel serial date
  const s = String(value ?? "").trim();
  if (!s) return false;
  if (DATE_REGEX.some((rx) => rx.test(s))) return true;
  const t = Date.parse(s);
  return !isNaN(t);
}

function isPositiveNumeric(value: unknown): boolean {
  const s = String(value ?? "").trim();
  if (!s) return false;
  // Strip currency tokens (SAR, ر.س, ريال, etc.)
  const cleaned = s.replace(/SAR|S\.A\.R|ر\.س|ريال|﷼|,/gi, "").replace(/[^0-9.\-]/g, "").trim();
  if (!cleaned) return false;
  const n = parseFloat(cleaned);
  return !isNaN(n) && n >= 0;
}

function isText(value: unknown): boolean {
  return typeof value === "string" && value.trim().length > 1;
}

function isNonEmptyString(value: unknown): boolean {
  return typeof value === "string" && value.trim().length > 0;
}

// ---------------------------------------------------------------------------
// Field definitions — mirrors Python FIELD_PATTERNS
// ---------------------------------------------------------------------------
type SampleValidator = (value: unknown) => boolean;

interface FieldDef {
  target: TargetColumn;
  validator: SampleValidator;
  skipIf?: (colCleaned: string) => boolean;
}

const FIELD_DEFS: FieldDef[] = [
  { target: "expiry_date", validator: isDateLike,
    skipIf: (c) => !/(expir|exp_|best_before|bestbefore|صلاح|انتهاء)/.test(c) },
  { target: "transaction_at", validator: isDateLike },
  { target: "item_name", validator: isText },
  { target: "barcode", validator: (v) => String(v ?? "").trim().length >= 6 },
  { target: "item_sku", validator: (v) => String(v ?? "").trim().length > 1 },
  { target: "brand", validator: isText },
  { target: "pack_size", validator: isText },
  { target: "storage_type", validator: isText },
  { target: "current_stock", validator: isPositiveNumeric,
    skipIf: (c) => /^(qty|quantity|qnty|units|كمية|الكمية)$/.test(c) },
  { target: "quantity", validator: isPositiveNumeric },
  { target: "reorder_level", validator: isPositiveNumeric },
  { target: "max_stock", validator: isPositiveNumeric },
  { target: "unit_price", validator: isPositiveNumeric,
    skipIf: (c) => /(cost|purchase|buy|landed|شراء|تكلفة)/.test(c) },
  { target: "cost_price", validator: isPositiveNumeric },
  { target: "total_amount", validator: isPositiveNumeric },
  { target: "category_name", validator: isText },
  { target: "batch_number", validator: isNonEmptyString },
];

// ---------------------------------------------------------------------------
// Score a column against all target fields, return best match
// ---------------------------------------------------------------------------
function scoreColumn(
  colName: string,
  sampleValues: unknown[]
): { target: TargetColumn; score: number } | null {
  const c = clean(colName);
  let bestTarget: TargetColumn | null = null;
  let bestScore = 0;

  for (const def of FIELD_DEFS) {
    if (def.skipIf?.(c)) continue;

    const hints = COLUMN_ALIASES[def.target] || [];
    const nameScore = nameSimilarity(colName, hints);

    const samples = sampleValues.slice(0, 20).filter((v) => v != null && v !== "");
    const matchCount = samples.filter((v) => def.validator(v)).length;
    const sampleScore = samples.length > 0 ? matchCount / samples.length : 0;

    const combined = nameScore * 0.7 + sampleScore * 0.3;
    if (combined > bestScore) {
      bestScore = combined;
      bestTarget = def.target;
    }
  }

  if (bestTarget && bestScore >= 0.4) {
    return { target: bestTarget as TargetColumn, score: bestScore };
  }
  return null;
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Parse a CSV file with PapaParse and detect column mappings.
 * Returns the same shape as the server-side UploadResult so the ColumnMapper UI works unchanged.
 */
export function detectSchemaFromCSV(file: File): Promise<Omit<UploadResult, "upload_id">> {
  return new Promise((resolve, reject) => {
    Papa.parse(file, {
      header: true,
      skipEmptyLines: true,
      preview: 100, // Only read first 100 rows for detection
      complete(results) {
        const rows = results.data as Record<string, unknown>[];
        const allColumns = results.meta.fields || [];

        // Count total rows (re-parse without preview for accurate count)
        Papa.parse(file, {
          header: false,
          skipEmptyLines: true,
          complete(countResults) {
            const totalRows = (countResults.data as unknown[][]).length;
            const detection = detectFromRows(allColumns, rows, totalRows, file.name);
            resolve(detection);
          },
          error(err) {
            reject(err);
          },
        });
      },
      error(err) {
        reject(err);
      },
    });
  });
}

/**
 * Detect schema from pre-parsed rows (e.g., already parsed by PapaParse in the upload page).
 */
export function detectFromRows(
  columns: string[],
  sampleRows: Record<string, unknown>[],
  totalRows: number,
  filename: string = "upload.csv"
): Omit<UploadResult, "upload_id"> {
  const detectedColumns: Record<string, string> = {};
  const confidenceScores: Record<string, number> = {};
  const usedTargets = new Set<string>();

  for (const col of columns) {
    const sampleValues = sampleRows.map((r) => r[col]);
    const result = scoreColumn(col, sampleValues);

    if (result && !usedTargets.has(result.target)) {
      detectedColumns[col] = result.target;
      confidenceScores[col] = result.score;
      usedTargets.add(result.target);
    }
  }

  const mappedTargets = Object.values(detectedColumns);
  const unmappedColumns = columns.filter((c) => !detectedColumns[c]);

  // Determine file kind
  const hasTransactionAt = mappedTargets.includes("transaction_at");
  let suggestedFileKind: string = hasTransactionAt ? "sales_history" : "inventory_snapshot";

  // If no sales date detected, remap quantity → current_stock (Python behavior)
  if (!hasTransactionAt) {
    for (const [src, tgt] of Object.entries(detectedColumns)) {
      if (tgt === "quantity") {
        detectedColumns[src] = "current_stock";
        break;
      }
    }
  }

  return {
    filename,
    file_size: 0, // Will be set by caller
    mime_type: "text/csv",
    row_count: totalRows,
    detected_columns: detectedColumns,
    confidence_scores: confidenceScores,
    unmapped_columns: unmappedColumns,
    sample_rows: sampleRows.slice(0, 5),
    suggested_file_kind: suggestedFileKind,
    schema_valid: Object.keys(detectedColumns).length > 0,
  };
}

/**
 * Detect Foodics/Salla export signature.
 * Returns a suggested file kind if the column set matches a known POS export.
 */
export function detectPOSSignature(columns: string[]): string | null {
  const c = columns.map(clean);

  const foodicsMarkers = ["date", "item", "qty", "amount", "cost"];
  const foodicsScore = foodicsMarkers.filter((m) => c.some((col) => col.includes(m))).length;
  if (foodicsScore >= 4) return "foodics_export";

  const sallaMarkers = ["order", "product", "quantity", "price", "total"];
  const sallaScore = sallaMarkers.filter((m) => c.some((col) => col.includes(m))).length;
  if (sallaScore >= 4) return "salla_export";

  return null;
}
