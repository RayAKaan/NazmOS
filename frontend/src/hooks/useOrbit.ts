import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
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

export interface DataQualityHistoryItem {
  run_id: string;
  overall_score: number;
  domain_scores: any;
  created_at: string;
  period_start: string;
  period_end: string;
}

export function useOrbitHistory(businessId?: string, limit = 50, offset = 0) {
  return useQuery({
    queryKey: ["orbit-history", businessId, limit, offset],
    queryFn: async () => {
      const params = new URLSearchParams();
      if (businessId) params.set("business_id", businessId);
      params.set("limit", limit.toString());
      params.set("offset", offset.toString());
      const res = await api.get(`/orbit/audits?${params.toString()}`);
      return res.data as { audits: OrbitHistoryItem[]; count: number };
    },
  });
}

export function useOrbitAudit(auditId: string) {
  return useQuery({
    queryKey: ["orbit-audit", auditId],
    queryFn: async () => {
      const res = await api.get(`/orbit/audits/${auditId}`);
      return res.data as OrbitAudit;
    },
    enabled: !!auditId,
  });
}

export function useOrbitComparison(auditId: string, vsAuditId?: string) {
  return useQuery({
    queryKey: ["orbit-comparison", auditId, vsAuditId],
    queryFn: async () => {
      const params = new URLSearchParams();
      if (vsAuditId) params.set("vs_audit_id", vsAuditId);
      const res = await api.get(`/orbit/audits/${auditId}/compare?${params.toString()}`);
      return res.data as OrbitComparison;
    },
    enabled: !!auditId,
  });
}

export function useFindingDrilldown(auditId: string, findingId: string) {
  return useQuery({
    queryKey: ["finding-drilldown", auditId, findingId],
    queryFn: async () => {
      const res = await api.get(`/orbit/audits/${auditId}/findings/${findingId}`);
      return res.data as FindingDrilldown;
    },
    enabled: !!auditId && !!findingId,
  });
}

export function useDataQualityHistory(businessId?: string, limit = 50) {
  return useQuery({
    queryKey: ["data-quality-history", businessId, limit],
    queryFn: async () => {
      const params = new URLSearchParams();
      if (businessId) params.set("business_id", businessId);
      params.set("limit", limit.toString());
      const res = await api.get(`/orbit/data-quality/history?${params.toString()}`);
      return res.data as { history: any[]; count: number };
    },
  });
}