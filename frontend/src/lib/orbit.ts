import api from "@/lib/api";

export interface OrbitAudit {
  audit_id: string;
  business_id: string;
  business_type: string;
  period: { start: string; end: string };
  health_score: number;
  health_breakdown: any;
  exposures: any;
  findings: any[];
  opportunities: any[];
  evidence: any;
  limitations: any;
  sources: any[];
  generated_at: string;
  metrics: Record<string, any>;
}

export interface OrbitHistoryItem {
  id: string;
  business_id: string;
  business_type: string;
  period_start: string;
  period_end: string;
  health_score: number;
  health_breakdown: any;
  created_at: string;
}

export interface OrbitComparison {
  current: any;
  previous: any;
  delta: any;
}

export interface FindingDrilldown {
  finding: any;
  products: any[];
  evidence: any[];
  source_rows: any[];
}

export interface IngestionManifest {
  file_id: string;
  filename: string;
  classification: string;
  confidence: number;
  rows: number;
  columns: number;
  mapped_fields: Record<string, string>;
  missing_fields: string[];
  ambiguous_fields: string[];
  quality: {
    duplicate_rows: number;
    null_rate: number;
    invalid_dates: number;
  };
  metadata: Record<string, any>;
  file_type: string;
  selected_sheet: string | null;
  sheet_count: number | null;
  header_row_index: number | null;
  detected_columns: string[];
  column_confidence: number;
  is_arabic_headers: boolean;
  is_arabic_data: boolean;
}

export interface BusinessSnapshot {
  business_id: string | null;
  business_type: string;
  period_start: string | null;
  period_end: string | null;
  branches: any[];
  products: any[];
  sales: any[];
  inventory: any[];
  purchases: any[];
  suppliers: any[];
  expenses: any[];
  data_quality: any;
  evidence_ids: Record<string, string>;
  ingestion_manifests: any[];
}

export interface OrbitAuditResult {
  version: string;
  audit_id: string;
  business_id: string | null;
  business_type: string;
  period: { start: string; end: string };
  health_score: number;
  health_breakdown: any;
  exposures: any;
  metrics: Record<string, any>;
  findings: any[];
  opportunities: any[];
  evidence: Record<string, any>;
  limitations: any;
  sources: any[];
  generated_at: string;
}

export async function fetchOrbitHistory(businessId?: string, limit = 50, offset = 0) {
  const params = new URLSearchParams();
  if (businessId) params.set("business_id", businessId);
  params.set("limit", limit.toString());
  params.set("offset", offset.toString());
  const res = await fetch(`/api/v1/orbit/audits?${params.toString()}`, {
    headers: { "Content-Type": "application/json" },
  });
  if (!res.ok) throw new Error("Failed to fetch orbit history");
  return res.json();
}

export async function fetchOrbitAudit(auditId: string) {
  const res = await fetch(`/api/v1/orbit/audits/${auditId}`, {
    headers: { "Content-Type": "application/json" },
  });
  if (!res.ok) throw new Error("Failed to fetch audit");
  return res.json();
}

export async function fetchOrbitComparison(auditId: string, vsAuditId?: string) {
  const params = new URLSearchParams();
  if (vsAuditId) params.set("vs_audit_id", vsAuditId);
  const res = await fetch(`/api/v1/orbit/audits/${auditId}/compare?${params.toString()}`, {
    headers: { "Content-Type": "application/json" },
  });
  if (!res.ok) throw new Error("Failed to fetch comparison");
  return res.json();
}

export async function fetchFindingDrilldown(auditId: string, findingId: string) {
  const res = await fetch(`/api/v1/orbit/audits/${auditId}/findings/${findingId}`, {
    headers: { "Content-Type": "application/json" },
  });
  if (!res.ok) throw new Error("Failed to fetch finding drilldown");
  return res.json();
}

export async function fetchDataQualityHistory(businessId?: string, limit = 50) {
  const params = new URLSearchParams();
  if (businessId) params.set("business_id", businessId);
  params.set("limit", limit.toString());
  const res = await fetch(`/api/v1/orbit/data-quality/history?${params.toString()}`, {
    headers: { "Content-Type": "application/json" },
  });
  if (!res.ok) throw new Error("Failed to fetch data quality history");
  return res.json();
}

export async function runOrbitAnalysis(snapshot: any, businessType = "retail") {
  const res = await fetch("/api/v1/orbit/analyze", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ snapshot, business_type: businessType }),
  });
  if (!res.ok) throw new Error("Failed to run orbit analysis");
  return res.json();
}

export async function runOrbitIntake(files: File[], businessType = "retail") {
  const formData = new FormData();
  files.forEach((file) => formData.append("files", file));
  formData.append("business_type", businessType);

  const res = await fetch("/api/v1/orbit/intake", {
    method: "POST",
    body: formData,
  });
  if (!res.ok) throw new Error("Failed to process intake");
  return res.json();
}

export async function analyzeOrbit(snapshot: any, businessType = "retail") {
  const res = await fetch("/api/v1/orbit/analyze", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ snapshot, business_type: businessType }),
  });
  if (!res.ok) throw new Error("Failed to analyze");
  return res.json();
}