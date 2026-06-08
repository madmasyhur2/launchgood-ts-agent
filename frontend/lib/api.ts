// lib/api.ts
// Typed API client for the LaunchGood T&S backend.
// All functions throw on HTTP error — callers should wrap in try/catch.

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api";

// ---------------------------------------------------------------------------
// Types (mirroring backend Pydantic schemas)
// ---------------------------------------------------------------------------

export type RiskLevel = "LOW" | "MEDIUM" | "HIGH";
export type Recommendation = "APPROVE" | "ESCALATE" | "REJECT";

export interface RiskDimension {
  score: number;
  signals: string[];
  weight: number;
}

export interface AnalysisFlag {
  type: string;
  severity: string;
  detail: string;
}

export interface AIAnalysisDetail {
  risk_score: number;
  risk_level: RiskLevel;
  recommendation: Recommendation;
  confidence: number | null;
  reasoning_summary: string | null;
  risk_dimensions: Record<string, RiskDimension> | null;
  flags: AnalysisFlag[] | null;
  processing_time_ms: number | null;
  model_version: string | null;
  analyzed_at: string;
}

export interface CampaignQueueItem {
  campaign_id: string;
  title: string;
  category: string | null;
  goal_amount: number | null;
  currency: string | null;
  creator_country: string | null;
  beneficiary_country: string | null;
  status: string;
  risk_score: number | null;
  risk_level: RiskLevel | null;
  recommendation: Recommendation | null;
  submitted_at: string;
  time_in_queue_minutes: number | null;
}

export interface CampaignQueueResponse {
  total: number;
  pending: number;
  page: number;
  limit: number;
  items: CampaignQueueItem[];
}

export interface CampaignAnalysisResponse {
  campaign_id: string;
  title: string;
  story: string | null;
  category: string | null;
  goal_amount: number | null;
  currency: string | null;
  creator_name: string | null;
  creator_country: string | null;
  beneficiary_country: string | null;
  organization_name: string | null;
  status: string;
  submitted_at: string;
  ai_analysis: AIAnalysisDetail | null;
}

export interface ReviewRequest {
  reviewer_id: string;
  decision: Recommendation;
  override_reason?: string;
  notes?: string;
}

export interface ReviewResponse {
  campaign_id: string;
  review_id: string;
  decision: Recommendation;
  ai_recommendation: Recommendation | null;
  is_override: boolean;
  audit_log_id: string;
  processed_at: string;
}

export interface OverrideBreakdown {
  ai_approve_human_reject: number;
  ai_reject_human_approve: number;
  ai_escalate_human_approve: number;
}

export interface EvalMetricsResponse {
  period: string;
  total_campaigns: number;
  ai_performance: {
    accuracy_rate: number;
    override_rate: number;
    override_breakdown: OverrideBreakdown;
    avg_processing_time_ms: number;
    avg_human_review_time_minutes: number;
  };
  throughput: {
    ai_auto_resolved: number;
    required_human_review: number;
    human_time_saved_hours: number;
  };
  risk_distribution: {
    LOW: number;
    MEDIUM: number;
    HIGH: number;
  };
}

// ---------------------------------------------------------------------------
// HTTP helper
// ---------------------------------------------------------------------------

async function apiFetch<T>(
  path: string,
  options?: RequestInit
): Promise<T> {
  const url = `${API_BASE}${path}`;
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`API ${res.status}: ${body || res.statusText}`);
  }
  return res.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// API functions
// ---------------------------------------------------------------------------

/** Fetch the campaign review queue with optional filters and pagination. */
export async function getCampaignQueue(params?: {
  status?: string;
  risk_level?: RiskLevel;
  recommendation?: Recommendation;
  page?: number;
  limit?: number;
}): Promise<CampaignQueueResponse> {
  const qs = new URLSearchParams();
  if (params?.status) qs.set("status", params.status);
  if (params?.risk_level) qs.set("risk_level", params.risk_level);
  if (params?.recommendation) qs.set("recommendation", params.recommendation);
  if (params?.page) qs.set("page", String(params.page));
  if (params?.limit) qs.set("limit", String(params.limit));
  const query = qs.toString() ? `?${qs}` : "";
  return apiFetch<CampaignQueueResponse>(`/campaigns/queue${query}`);
}

/** Fetch full campaign detail + latest AI analysis. */
export async function getCampaignAnalysis(
  campaignId: string
): Promise<CampaignAnalysisResponse> {
  return apiFetch<CampaignAnalysisResponse>(
    `/campaigns/${campaignId}/analysis`
  );
}

/** Submit a human reviewer decision for a campaign. */
export async function submitReview(
  campaignId: string,
  payload: ReviewRequest
): Promise<ReviewResponse> {
  return apiFetch<ReviewResponse>(`/campaigns/${campaignId}/review`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

/** Fetch AI performance eval metrics. */
export async function getEvalMetrics(
  periodDays = 30
): Promise<EvalMetricsResponse> {
  return apiFetch<EvalMetricsResponse>(
    `/analytics/eval-metrics?period_days=${periodDays}`
  );
}
