export type UploadStatus = "pending" | "uploaded" | "validating" | "scanning" | "mapping_required" | "mapping" | "processing" | "completed" | "failed";

export interface UploadedFile {
  id: string;
  business_id: string;
  original_filename: string;
  stored_filename: string;
  file_path: string;
  file_size: number;
  mime_type: string;
  status: UploadStatus;
  row_count: number;
  column_count: number;
  error_message?: string;
  created_at: string;
  completed_at?: string;
}

export interface UploadResult {
  upload_id: string;
  filename: string;
  file_size: number;
  mime_type: string;
  row_count: number;
  detected_columns: Record<string, string>;
  confidence_scores: Record<string, number>;
  unmapped_columns: string[];
  sample_rows: Record<string, unknown>[];
  suggested_file_kind?: "sales_history" | "inventory_snapshot" | string;
  schema_valid: boolean;
}

export interface ColumnMapping {
  source_column: string;
  target_column: string;
  confidence: number;
  sample_values: unknown[];
}

export interface ColumnMapperResult {
  upload_id: string;
  mappings: ColumnMapping[];
  unmapped_columns: string[];
  validation_errors: ValidationError[];
}

export interface ValidationError {
  column: string;
  row: number;
  value: unknown;
  error_type: "missing" | "invalid" | "duplicate";
  message: string;
}

export interface IngestionProgress {
  upload_id: string;
  status: UploadStatus;
  progress: number;
  rows_processed: number;
  total_rows: number;
  errors: IngestionError[];
  started_at: string | null;
  estimated_completion?: string | null;
}

export interface IngestionError {
  row: number;
  column: string;
  value: unknown;
  error: string;
}

export interface IngestionResult {
  upload_id: string;
  status: "completed" | "partial" | "failed";
  rows_imported: number;
  rows_failed: number;
  errors: IngestionError[];
  duration_seconds: number;
}

export const REQUIRED_COLUMNS = ["item_name"] as const;

export const SALES_SIGNAL_COLUMNS = ["transaction_at", "total_amount", "unit_price", "quantity", "cost_price"] as const;
export const INVENTORY_SIGNAL_COLUMNS = ["current_stock", "cost_price", "sell_price", "reorder_level", "max_stock"] as const;

export const TARGET_COLUMNS = [
  "item_name",
  "item_sku",
  "barcode",
  "category_name",
  "brand",
  "pack_size",
  "storage_type",
  "transaction_at",
  "quantity",
  "unit_price",
  "cost_price",
  "total_amount",
  "current_stock",
  "sell_price",
  "reorder_level",
  "max_stock",
  "expiry_date",
  "batch_number",
] as const;

export type TargetColumn = typeof TARGET_COLUMNS[number];

export const COLUMN_LABELS: Record<TargetColumn, string> = {
  item_name: "Product name",
  item_sku: "SKU / item code",
  barcode: "Barcode",
  category_name: "Category",
  brand: "Brand",
  pack_size: "Pack size",
  storage_type: "Storage type",
  transaction_at: "Sale date",
  quantity: "Sold quantity",
  unit_price: "Selling price",
  cost_price: "Cost price",
  total_amount: "Sale total",
  current_stock: "Current stock",
  sell_price: "Shelf price",
  reorder_level: "Reorder level",
  max_stock: "Max stock",
  expiry_date: "Expiry date",
  batch_number: "Batch number",
};

export const COLUMN_HELP: Record<TargetColumn, string> = {
  item_name: "Required. Product or item name as shown in POS.",
  item_sku: "Optional but useful for exact matching.",
  barcode: "Best for Recovery Match and duplicate cleanup.",
  category_name: "Used for category-level leakage and guardrails.",
  brand: "Useful for exact product matching.",
  pack_size: "Example: 24x330ml, 1kg, 250g.",
  storage_type: "Ambient only for Recovery Match v1. Avoid chilled/frozen/regulated.",
  transaction_at: "Needed for sales history, stockout risk, and velocity.",
  quantity: "Units sold in each sale row.",
  unit_price: "Price customer paid per unit.",
  cost_price: "Needed to estimate trapped cash and margin leakage.",
  total_amount: "Total sale value for the row.",
  current_stock: "Needed for inventory snapshot, dead stock, and Recovery Match preview.",
  sell_price: "Current shelf selling price from inventory export.",
  reorder_level: "Minimum stock before reorder.",
  max_stock: "Target full stock level.",
  expiry_date: "Required before any real Recovery Match listing.",
  batch_number: "Optional proof field for stock recovery.",
};

export const COLUMN_ALIASES: Record<TargetColumn, string[]> = {
  item_name: ["product_name", "product", "name", "item_name", "item", "description", "title", "اسم الصنف", "اسم المنتج", "منتج", "صنف"],
  item_sku: ["sku", "item_sku", "product_sku", "code", "item_code", "product_code", "رمز الصنف", "كود", "رمز"],
  barcode: ["barcode", "bar_code", "upc", "ean", "gtin", "باركود"],
  category_name: ["category", "cat", "product_category", "item_category", "department", "section", "group", "تصنيف", "قسم"],
  brand: ["brand", "make", "manufacturer", "ماركة", "علامة"],
  pack_size: ["pack_size", "pack", "size", "unit_size", "case_pack", "عبوة", "حجم"],
  storage_type: ["storage", "storage_type", "temperature", "ambient", "chilled", "frozen", "تخزين"],
  transaction_at: ["transaction_at", "date", "sale_date", "sales_date", "sold_at", "invoice_date", "bill_date", "التاريخ", "تاريخ البيع"],
  quantity: ["quantity", "qty", "sold_qty", "sales_qty", "units", "pieces", "كمية", "الكمية"],
  unit_price: ["unit_price", "price", "selling_price", "sale_price", "retail_price", "rate", "سعر", "سعر البيع"],
  cost_price: ["cost_price", "cost", "purchase_price", "buy_price", "landed_cost", "تكلفة", "سعر الشراء"],
  total_amount: ["total", "amount", "net_amount", "gross_amount", "total_amount", "revenue", "اجمالي", "المبلغ"],
  current_stock: ["current_stock", "quantity_on_hand", "stock", "stock_qty", "current_qty", "available", "on_hand", "inventory", "رصيد", "مخزون"],
  sell_price: ["sell_price", "shelf_price", "selling_price", "retail_price", "mrp", "سعر الرف"],
  reorder_level: ["reorder_level", "reorder", "reorder_point", "min_stock", "minimum_stock", "حد الطلب", "الحد الادنى"],
  max_stock: ["max_stock", "maximum_stock", "max", "par_level", "capacity", "الحد الاعلى"],
  expiry_date: ["expiry_date", "expiry", "expiration_date", "expires", "best_before", "تاريخ الصلاحية", "صلاحية"],
  batch_number: ["batch_number", "batch", "batch_no", "lot", "lot_number", "تشغيلة", "دفعة"],
};
