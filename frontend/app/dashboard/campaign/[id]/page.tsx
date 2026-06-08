"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  getCampaignAnalysis,
  submitReview,
  type CampaignAnalysisResponse,
  type Recommendation,
} from "@/lib/api";
import {
  riskColors,
  recColors,
  formatCurrency,
  countryName,
  cn,
} from "@/lib/utils";
import {
  ArrowLeft,
  AlertTriangle,
  CheckCircle,
  XCircle,
  AlertCircle,
  Clock,
  Globe,
  User,
  Target,
  Brain,
  FileText,
  Loader2,
  ChevronRight,
  Info,
} from "lucide-react";

// ── Sub-components ─────────────────────────────────────────────────────────

function InfoRow({
  label,
  value,
}: {
  label: string;
  value: React.ReactNode;
}) {
  return (
    <div className="flex items-start justify-between py-2.5 border-b border-slate-100 last:border-0">
      <span className="text-xs font-medium text-slate-500 uppercase tracking-wide w-36 shrink-0">
        {label}
      </span>
      <span className="text-sm text-slate-800 text-right">{value || "—"}</span>
    </div>
  );
}

function DimensionBar({
  name,
  score,
  signals,
  weight,
}: {
  name: string;
  score: number;
  signals: string[];
  weight: number;
}) {
  const color =
    score >= 70 ? "bg-red-500" : score >= 30 ? "bg-amber-500" : "bg-emerald-500";
  const displayName = name
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-slate-700">{displayName}</span>
        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-400">w={weight.toFixed(2)}</span>
          <span className="text-xs font-bold text-slate-900 w-7 text-right tabular-nums">
            {score}
          </span>
        </div>
      </div>
      <div className="h-2 w-full rounded-full bg-slate-100 overflow-hidden">
        <div
          className={cn("h-full rounded-full transition-all duration-500", color)}
          style={{ width: `${score}%` }}
        />
      </div>
      {signals.length > 0 && (
        <div className="flex flex-wrap gap-1 mt-1">
          {signals.slice(0, 4).map((s) => (
            <span
              key={s}
              className="inline-flex text-xs bg-slate-100 text-slate-500 rounded px-1.5 py-0.5"
            >
              {s.replace(/_/g, " ")}
            </span>
          ))}
          {signals.length > 4 && (
            <span className="text-xs text-slate-400">+{signals.length - 4}</span>
          )}
        </div>
      )}
    </div>
  );
}

function Toast({
  message,
  type,
  onClose,
}: {
  message: string;
  type: "success" | "error";
  onClose: () => void;
}) {
  useEffect(() => {
    const t = setTimeout(onClose, 4000);
    return () => clearTimeout(t);
  }, [onClose]);

  return (
    <div
      className={cn(
        "fixed bottom-6 right-6 z-50 flex items-center gap-3 rounded-xl px-4 py-3 shadow-xl border text-sm font-medium",
        type === "success"
          ? "bg-emerald-50 border-emerald-200 text-emerald-800"
          : "bg-red-50 border-red-200 text-red-800"
      )}
    >
      {type === "success" ? (
        <CheckCircle size={16} className="text-emerald-600" />
      ) : (
        <AlertTriangle size={16} className="text-red-500" />
      )}
      {message}
    </div>
  );
}

// ── Decision Form ───────────────────────────────────────────────────────────

function DecisionForm({
  campaignId,
  aiRecommendation,
  onSuccess,
}: {
  campaignId: string;
  aiRecommendation: Recommendation | null;
  onSuccess: (decision: Recommendation) => void;
}) {
  const [decision, setDecision] = useState<Recommendation | null>(null);
  const [overrideReason, setOverrideReason] = useState("");
  const [notes, setNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isOverride = decision && aiRecommendation && decision !== aiRecommendation;
  const needsReason = isOverride && overrideReason.trim().length < 10;

  const DECISIONS: {
    value: Recommendation;
    label: string;
    icon: React.ElementType;
    style: string;
  }[] = [
    {
      value: "APPROVE",
      label: "Approve",
      icon: CheckCircle,
      style:
        "bg-emerald-600 hover:bg-emerald-700 text-white disabled:bg-emerald-200",
    },
    {
      value: "ESCALATE",
      label: "Escalate",
      icon: AlertCircle,
      style:
        "bg-amber-500 hover:bg-amber-600 text-white disabled:bg-amber-200",
    },
    {
      value: "REJECT",
      label: "Reject",
      icon: XCircle,
      style:
        "bg-red-600 hover:bg-red-700 text-white disabled:bg-red-200",
    },
  ];

  async function handleSubmit() {
    if (!decision) return;
    if (needsReason) return;
    setSubmitting(true);
    setError(null);
    try {
      await submitReview(campaignId, {
        reviewer_id: "ts-reviewer-1",
        decision,
        override_reason: overrideReason || undefined,
        notes: notes || undefined,
      });
      onSuccess(decision);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Submission failed");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="space-y-4">
      {/* Decision selection */}
      <div>
        <label className="block text-xs font-semibold text-slate-600 uppercase tracking-wide mb-2">
          Your Decision
        </label>
        <div className="grid grid-cols-3 gap-2">
          {DECISIONS.map(({ value, label, icon: Icon }) => (
            <button
              key={value}
              onClick={() => setDecision(value)}
              className={cn(
                "flex items-center justify-center gap-2 rounded-lg border-2 py-2.5 text-sm font-semibold transition-all",
                decision === value
                  ? value === "APPROVE"
                    ? "border-emerald-600 bg-emerald-600 text-white"
                    : value === "ESCALATE"
                    ? "border-amber-500 bg-amber-500 text-white"
                    : "border-red-600 bg-red-600 text-white"
                  : "border-slate-200 bg-white text-slate-700 hover:border-slate-300"
              )}
            >
              <Icon size={15} />
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Override reason — shown when human disagrees with AI */}
      {isOverride && (
        <div>
          <label className="block text-xs font-semibold text-slate-600 uppercase tracking-wide mb-1.5">
            Override Reason{" "}
            <span className="text-red-500">*</span>
            <span className="text-slate-400 normal-case font-normal ml-1">
              (AI recommended {aiRecommendation})
            </span>
          </label>
          <textarea
            value={overrideReason}
            onChange={(e) => setOverrideReason(e.target.value)}
            placeholder="Explain why you're overriding the AI recommendation (min 10 chars)…"
            rows={3}
            className={cn(
              "w-full rounded-lg border px-3 py-2 text-sm text-slate-800 placeholder:text-slate-400",
              "focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent",
              "resize-none transition-colors",
              needsReason ? "border-red-300 bg-red-50" : "border-slate-200 bg-white"
            )}
          />
          {needsReason && (
            <p className="text-xs text-red-500 mt-1">
              Please provide at least 10 characters.
            </p>
          )}
        </div>
      )}

      {/* Notes */}
      <div>
        <label className="block text-xs font-semibold text-slate-600 uppercase tracking-wide mb-1.5">
          Notes{" "}
          <span className="text-slate-400 normal-case font-normal">(optional)</span>
        </label>
        <textarea
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder="Additional context or follow-up actions for the team…"
          rows={2}
          className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-none transition-colors"
        />
      </div>

      {error && (
        <p className="flex items-center gap-2 text-sm text-red-600">
          <AlertTriangle size={14} />
          {error}
        </p>
      )}

      {/* Submit */}
      <button
        onClick={handleSubmit}
        disabled={!decision || !!needsReason || submitting}
        className={cn(
          "w-full flex items-center justify-center gap-2 rounded-lg px-4 py-3 text-sm font-semibold transition-all",
          !decision || !!needsReason
            ? "bg-slate-100 text-slate-400 cursor-not-allowed"
            : "bg-blue-600 hover:bg-blue-700 text-white shadow-sm"
        )}
      >
        {submitting && <Loader2 size={15} className="animate-spin" />}
        {submitting ? "Submitting…" : decision ? `Submit: ${decision}` : "Select a decision"}
      </button>
    </div>
  );
}

// ── Main page ──────────────────────────────────────────────────────────────

export default function CampaignDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [data, setData] = useState<CampaignAnalysisResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<{
    message: string;
    type: "success" | "error";
  } | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await getCampaignAnalysis(params.id);
      setData(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load campaign");
    } finally {
      setLoading(false);
    }
  }, [params.id]);

  useEffect(() => {
    load();
  }, [load]);

  function handleDecisionSuccess(decision: Recommendation) {
    setToast({
      message: `Decision submitted: ${decision}`,
      type: "success",
    });
    setTimeout(() => router.push("/dashboard"), 2000);
  }

  // ── Loading skeleton ─────────────────────────────────────────────────────
  if (loading) {
    return (
      <div className="space-y-6">
        <div className="h-8 w-48 bg-slate-200 rounded animate-pulse" />
        <div className="grid gap-6 lg:grid-cols-2">
          {[1, 2].map((i) => (
            <div key={i} className="bg-white rounded-xl border border-slate-200 p-6 space-y-4">
              {Array.from({ length: 5 }).map((_, j) => (
                <div key={j} className="h-4 bg-slate-200 rounded animate-pulse" style={{ width: `${70 + j * 5}%` }} />
              ))}
            </div>
          ))}
        </div>
      </div>
    );
  }

  // ── Error state ──────────────────────────────────────────────────────────
  if (error || !data) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[40vh] gap-4">
        <AlertTriangle size={32} className="text-red-400" />
        <p className="text-slate-600">{error ?? "Campaign not found"}</p>
        <div className="flex gap-3">
          <button
            onClick={load}
            className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
          >
            Retry
          </button>
          <button
            onClick={() => router.push("/dashboard")}
            className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            Back to Queue
          </button>
        </div>
      </div>
    );
  }

  const analysis = data.ai_analysis;
  const riskC = riskColors(analysis?.risk_level ?? null);

  const alreadyReviewed = ["approved", "rejected", "escalated"].includes(data.status);

  return (
    <>
      {toast && (
        <Toast
          message={toast.message}
          type={toast.type}
          onClose={() => setToast(null)}
        />
      )}

      <div className="space-y-6 max-w-6xl mx-auto">
        {/* Breadcrumb */}
        <div className="flex items-center gap-2 text-sm text-slate-500">
          <button
            onClick={() => router.push("/dashboard")}
            className="hover:text-slate-800 flex items-center gap-1.5"
          >
            <ArrowLeft size={14} />
            Campaign Queue
          </button>
          <ChevronRight size={14} />
          <span className="text-slate-800 font-medium truncate max-w-xs">
            {data.title}
          </span>
        </div>

        {/* Title + status banner */}
        <div
          className={cn(
            "rounded-xl border p-5 flex items-start justify-between gap-4",
            analysis ? riskC.border : "border-slate-200",
            analysis ? riskC.bg : "bg-white"
          )}
        >
          <div>
            <h1 className="text-xl font-bold text-slate-900">{data.title}</h1>
            <div className="flex flex-wrap items-center gap-3 mt-2">
              {data.category && (
                <span className="text-xs bg-white/70 border border-slate-200 rounded-full px-2.5 py-1 text-slate-600 capitalize">
                  {data.category}
                </span>
              )}
              {data.goal_amount && (
                <span className="text-xs bg-white/70 border border-slate-200 rounded-full px-2.5 py-1 text-slate-600">
                  {formatCurrency(data.goal_amount, data.currency ?? "USD")}
                </span>
              )}
              <span
                className={cn(
                  "text-xs rounded-full px-2.5 py-1 font-medium capitalize",
                  alreadyReviewed
                    ? "bg-slate-100 text-slate-600"
                    : "bg-blue-100 text-blue-700"
                )}
              >
                {data.status}
              </span>
            </div>
          </div>
          {analysis && (
            <div className="text-right shrink-0">
              <div
                className={cn(
                  "text-3xl font-black tabular-nums",
                  riskC.text
                )}
              >
                {analysis.risk_score}
              </div>
              <div className="text-xs text-slate-500 mt-0.5">risk score</div>
            </div>
          )}
        </div>

        {/* Two-column layout */}
        <div className="grid gap-6 lg:grid-cols-2">
          {/* ── Left: Campaign info ── */}
          <div className="space-y-4">
            {/* Campaign details */}
            <div className="bg-white rounded-xl border border-slate-200 p-5">
              <div className="flex items-center gap-2 mb-4">
                <FileText size={16} className="text-slate-400" />
                <h2 className="text-sm font-semibold text-slate-800">
                  Campaign Details
                </h2>
              </div>
              <InfoRow label="Title" value={data.title} />
              <InfoRow
                label="Category"
                value={
                  data.category ? (
                    <span className="capitalize">{data.category}</span>
                  ) : null
                }
              />
              <InfoRow
                label="Goal Amount"
                value={formatCurrency(
                  data.goal_amount,
                  data.currency ?? "USD"
                )}
              />
              <InfoRow
                label="Organisation"
                value={data.organization_name}
              />
              <InfoRow
                label="Submitted"
                value={new Date(data.submitted_at).toLocaleString()}
              />
            </div>

            {/* Creator info */}
            <div className="bg-white rounded-xl border border-slate-200 p-5">
              <div className="flex items-center gap-2 mb-4">
                <User size={16} className="text-slate-400" />
                <h2 className="text-sm font-semibold text-slate-800">
                  Creator
                </h2>
              </div>
              <InfoRow label="Name" value={data.creator_name} />
              <InfoRow
                label="Creator Country"
                value={countryName(data.creator_country)}
              />
              <InfoRow
                label="Beneficiary Country"
                value={countryName(data.beneficiary_country)}
              />
            </div>

            {/* Story */}
            {data.story && (
              <div className="bg-white rounded-xl border border-slate-200 p-5">
                <div className="flex items-center gap-2 mb-3">
                  <FileText size={16} className="text-slate-400" />
                  <h2 className="text-sm font-semibold text-slate-800">
                    Campaign Story
                  </h2>
                </div>
                <p className="text-sm text-slate-600 leading-relaxed whitespace-pre-wrap line-clamp-10">
                  {data.story}
                </p>
              </div>
            )}
          </div>

          {/* ── Right: AI Analysis + Decision ── */}
          <div className="space-y-4">
            {!analysis ? (
              <div className="bg-white rounded-xl border border-slate-200 p-8 text-center">
                <Brain size={32} className="mx-auto text-slate-300 mb-2" />
                <p className="text-slate-500 text-sm">
                  AI analysis not yet available
                </p>
              </div>
            ) : (
              <>
                {/* AI Summary card */}
                <div className="bg-white rounded-xl border border-slate-200 p-5">
                  <div className="flex items-center gap-2 mb-4">
                    <Brain size={16} className="text-slate-400" />
                    <h2 className="text-sm font-semibold text-slate-800">
                      AI Analysis
                    </h2>
                    {analysis.model_version && (
                      <span className="ml-auto text-xs text-slate-400">
                        {analysis.model_version}
                      </span>
                    )}
                  </div>

                  {/* Top metrics row */}
                  <div className="grid grid-cols-3 gap-3 mb-4">
                    <div className="text-center rounded-lg bg-slate-50 p-3">
                      <div
                        className={cn(
                          "text-2xl font-black tabular-nums",
                          riskC.text
                        )}
                      >
                        {analysis.risk_score}
                      </div>
                      <div className="text-xs text-slate-400 mt-0.5">Score</div>
                    </div>
                    <div className="text-center rounded-lg bg-slate-50 p-3">
                      <span
                        className={cn(
                          "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-bold",
                          riskC.badge
                        )}
                      >
                        {analysis.risk_level}
                      </span>
                      <div className="text-xs text-slate-400 mt-1.5">Level</div>
                    </div>
                    <div className="text-center rounded-lg bg-slate-50 p-3">
                      <div className="text-sm font-bold text-slate-700">
                        {analysis.confidence != null
                          ? `${(analysis.confidence * 100).toFixed(0)}%`
                          : "—"}
                      </div>
                      <div className="text-xs text-slate-400 mt-0.5">Confidence</div>
                    </div>
                  </div>

                  {/* Recommendation */}
                  <div
                    className={cn(
                      "flex items-center justify-between rounded-lg px-4 py-3 mb-4",
                      recColors(analysis.recommendation)
                    )}
                  >
                    <span className="text-xs font-semibold uppercase tracking-wide opacity-70">
                      AI Recommendation
                    </span>
                    <span className="font-bold text-sm">
                      {analysis.recommendation}
                    </span>
                  </div>

                  {/* Reasoning summary */}
                  {analysis.reasoning_summary && (
                    <div className="rounded-lg bg-blue-50 border border-blue-100 px-4 py-3">
                      <div className="flex items-center gap-1.5 mb-1.5">
                        <Info size={12} className="text-blue-500" />
                        <span className="text-xs font-semibold text-blue-700 uppercase tracking-wide">
                          Reasoning
                        </span>
                      </div>
                      <p className="text-sm text-slate-700 leading-relaxed">
                        {analysis.reasoning_summary}
                      </p>
                    </div>
                  )}
                </div>

                {/* Risk Dimensions */}
                {analysis.risk_dimensions &&
                  Object.keys(analysis.risk_dimensions).length > 0 && (
                    <div className="bg-white rounded-xl border border-slate-200 p-5">
                      <div className="flex items-center gap-2 mb-4">
                        <Target size={16} className="text-slate-400" />
                        <h2 className="text-sm font-semibold text-slate-800">
                          Risk Dimensions
                        </h2>
                      </div>
                      <div className="space-y-4">
                        {Object.entries(analysis.risk_dimensions).map(
                          ([name, dim]) => (
                            <DimensionBar
                              key={name}
                              name={name}
                              score={dim.score}
                              signals={dim.signals}
                              weight={dim.weight}
                            />
                          )
                        )}
                      </div>
                    </div>
                  )}

                {/* Flags */}
                {analysis.flags && analysis.flags.length > 0 && (
                  <div className="bg-white rounded-xl border border-slate-200 p-5">
                    <div className="flex items-center gap-2 mb-3">
                      <AlertTriangle size={16} className="text-slate-400" />
                      <h2 className="text-sm font-semibold text-slate-800">
                        Flags ({analysis.flags.length})
                      </h2>
                    </div>
                    <div className="space-y-2">
                      {analysis.flags.map((flag, i) => (
                        <div
                          key={i}
                          className="flex items-start gap-3 rounded-lg bg-slate-50 px-3 py-2"
                        >
                          <span
                            className={cn(
                              "mt-0.5 h-2 w-2 rounded-full shrink-0",
                              flag.severity === "HIGH"
                                ? "bg-red-500"
                                : flag.severity === "MEDIUM"
                                ? "bg-amber-500"
                                : "bg-slate-400"
                            )}
                          />
                          <div>
                            <p className="text-xs font-semibold text-slate-700">
                              {flag.type}
                            </p>
                            <p className="text-xs text-slate-500">{flag.detail}</p>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Performance */}
                {analysis.processing_time_ms && (
                  <div className="flex items-center gap-2 text-xs text-slate-400 px-1">
                    <Clock size={12} />
                    Analysis completed in {analysis.processing_time_ms}ms ·{" "}
                    {new Date(analysis.analyzed_at).toLocaleString()}
                  </div>
                )}
              </>
            )}

            {/* Decision form */}
            {alreadyReviewed ? (
              <div className="bg-white rounded-xl border border-slate-200 p-5 text-center">
                <CheckCircle size={24} className="mx-auto text-emerald-500 mb-2" />
                <p className="text-sm font-medium text-slate-700">
                  This campaign has been{" "}
                  <span className="font-bold capitalize">{data.status}</span>.
                </p>
              </div>
            ) : (
              <div className="bg-white rounded-xl border border-slate-200 p-5">
                <div className="flex items-center gap-2 mb-4">
                  <CheckCircle size={16} className="text-slate-400" />
                  <h2 className="text-sm font-semibold text-slate-800">
                    Reviewer Decision
                  </h2>
                </div>
                <DecisionForm
                  campaignId={params.id}
                  aiRecommendation={analysis?.recommendation ?? null}
                  onSuccess={handleDecisionSuccess}
                />
              </div>
            )}
          </div>
        </div>
      </div>
    </>
  );
}
