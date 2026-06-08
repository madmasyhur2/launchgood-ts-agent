"use client";

import { useCallback, useEffect, useState } from "react";
import { getEvalMetrics, type EvalMetricsResponse } from "@/lib/api";
import { formatPercent, cn } from "@/lib/utils";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
  PieChart,
  Pie,
  Legend,
} from "recharts";
import {
  TrendingUp,
  AlertTriangle,
  Clock,
  Users,
  RefreshCw,
  CheckCircle,
  Target,
  Zap,
} from "lucide-react";

// ── Stat card ───────────────────────────────────────────────────────────────

function MetricCard({
  label,
  value,
  sub,
  icon: Icon,
  color,
  status,
}: {
  label: string;
  value: string;
  sub?: string;
  icon: React.ElementType;
  color: string;
  status?: "good" | "warn" | "bad" | "neutral";
}) {
  const statusBorder =
    status === "good"
      ? "border-emerald-200"
      : status === "warn"
      ? "border-amber-200"
      : status === "bad"
      ? "border-red-200"
      : "border-slate-200";

  return (
    <div
      className={cn(
        "bg-white rounded-xl border-2 p-5 flex flex-col gap-3",
        statusBorder
      )}
    >
      <div className="flex items-center justify-between">
        <div
          className={cn(
            "h-9 w-9 rounded-lg flex items-center justify-center",
            color
          )}
        >
          <Icon size={17} className="text-white" />
        </div>
        {status && status !== "neutral" && (
          <span
            className={cn(
              "text-xs font-medium rounded-full px-2 py-0.5",
              status === "good"
                ? "bg-emerald-100 text-emerald-700"
                : status === "warn"
                ? "bg-amber-100 text-amber-700"
                : "bg-red-100 text-red-700"
            )}
          >
            {status === "good" ? "On target" : status === "warn" ? "Monitor" : "Needs attention"}
          </span>
        )}
      </div>
      <div>
        <p className="text-3xl font-black text-slate-900">{value}</p>
        <p className="text-sm font-medium text-slate-600 mt-1">{label}</p>
        {sub && <p className="text-xs text-slate-400 mt-0.5">{sub}</p>}
      </div>
    </div>
  );
}

// ── Section wrapper ─────────────────────────────────────────────────────────

function Section({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="bg-white rounded-xl border border-slate-200 p-5">
      <div className="mb-5">
        <h2 className="text-sm font-semibold text-slate-800">{title}</h2>
        {subtitle && (
          <p className="text-xs text-slate-400 mt-0.5">{subtitle}</p>
        )}
      </div>
      {children}
    </div>
  );
}

// ── Custom Tooltip ──────────────────────────────────────────────────────────

function ChartTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: { name: string; value: number; color: string }[];
  label?: string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-white border border-slate-200 rounded-lg shadow-lg px-3 py-2 text-xs">
      {label && <p className="font-semibold text-slate-700 mb-1">{label}</p>}
      {payload.map((p) => (
        <p key={p.name} style={{ color: p.color }} className="font-medium">
          {p.name}: {(p.value * 100).toFixed(1)}%
        </p>
      ))}
    </div>
  );
}

// ── Skeleton ────────────────────────────────────────────────────────────────

function Skeleton({ className }: { className?: string }) {
  return (
    <div className={cn("bg-slate-200 rounded animate-pulse", className)} />
  );
}

// ── Main page ───────────────────────────────────────────────────────────────

export default function AnalyticsPage() {
  const [data, setData] = useState<EvalMetricsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [period, setPeriod] = useState(30);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(
    async (silent = false) => {
      if (!silent) setLoading(true);
      else setRefreshing(true);
      setError(null);
      try {
        const res = await getEvalMetrics(period);
        setData(res);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load metrics");
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [period]
  );

  useEffect(() => {
    load();
  }, [load]);

  // ── Error ────────────────────────────────────────────────────────────────
  if (error) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[40vh] gap-4">
        <AlertTriangle size={32} className="text-red-400" />
        <p className="text-slate-600">{error}</p>
        <button
          onClick={() => load()}
          className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
        >
          Retry
        </button>
      </div>
    );
  }

  // ── Chart data ───────────────────────────────────────────────────────────
  const overrideData = data
    ? [
        {
          name: "AI Approve → Human Reject",
          value: data.ai_performance.override_breakdown.ai_approve_human_reject,
          fill: "#ef4444",
        },
        {
          name: "AI Reject → Human Approve",
          value: data.ai_performance.override_breakdown.ai_reject_human_approve,
          fill: "#f59e0b",
        },
        {
          name: "AI Escalate → Human Approve",
          value: data.ai_performance.override_breakdown.ai_escalate_human_approve,
          fill: "#3b82f6",
        },
      ]
    : [];

  const riskData = data
    ? [
        { name: "LOW", value: data.risk_distribution.LOW, fill: "#10b981" },
        { name: "MEDIUM", value: data.risk_distribution.MEDIUM, fill: "#f59e0b" },
        { name: "HIGH", value: data.risk_distribution.HIGH, fill: "#ef4444" },
      ]
    : [];

  const acc = data?.ai_performance.accuracy_rate ?? 0;
  const ovr = data?.ai_performance.override_rate ?? 0;

  return (
    <div className="space-y-6 max-w-6xl">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">
            AI Eval Metrics
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Performance monitoring · Human-in-the-Loop accuracy tracking
          </p>
        </div>
        <div className="flex items-center gap-3">
          {/* Period selector */}
          <select
            value={period}
            onChange={(e) => setPeriod(Number(e.target.value))}
            className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value={7}>Last 7 days</option>
            <option value={30}>Last 30 days</option>
            <option value={90}>Last 90 days</option>
          </select>
          <button
            onClick={() => load(true)}
            disabled={refreshing}
            className="flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3.5 py-2 text-sm font-medium text-slate-700 shadow-sm hover:bg-slate-50 disabled:opacity-50"
          >
            <RefreshCw size={14} className={refreshing ? "animate-spin" : ""} />
            Refresh
          </button>
        </div>
      </div>

      {/* Metric cards */}
      {loading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-32" />
          ))}
        </div>
      ) : data ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <MetricCard
            label="AI Accuracy Rate"
            value={formatPercent(acc)}
            sub="Target: > 85%"
            icon={CheckCircle}
            color="bg-emerald-500"
            status={acc >= 0.85 ? "good" : acc >= 0.70 ? "warn" : "bad"}
          />
          <MetricCard
            label="Override Rate"
            value={formatPercent(ovr)}
            sub="Target: < 15%"
            icon={AlertTriangle}
            color="bg-amber-500"
            status={ovr <= 0.15 ? "good" : ovr <= 0.25 ? "warn" : "bad"}
          />
          <MetricCard
            label="Human Time Saved"
            value={`${data.throughput.human_time_saved_hours}h`}
            sub={`${data.throughput.ai_auto_resolved} auto-resolved`}
            icon={Zap}
            color="bg-blue-500"
            status="neutral"
          />
          <MetricCard
            label="Total Reviews"
            value={String(data.throughput.required_human_review)}
            sub={`${data.total_campaigns} campaigns total`}
            icon={Users}
            color="bg-violet-500"
            status="neutral"
          />
        </div>
      ) : null}

      {/* Secondary stats */}
      {!loading && data && (
        <div className="grid gap-4 sm:grid-cols-3">
          <MetricCard
            label="Avg. AI Processing Time"
            value={`${Math.round(data.ai_performance.avg_processing_time_ms)}ms`}
            sub="Target: P95 < 10,000ms"
            icon={Clock}
            color="bg-slate-500"
            status={
              data.ai_performance.avg_processing_time_ms < 10000
                ? "good"
                : "bad"
            }
          />
          <MetricCard
            label="Avg. Human Review Time"
            value={`${data.ai_performance.avg_human_review_time_minutes} min`}
            sub="Baseline: 4.2 min"
            icon={Users}
            color="bg-teal-500"
            status="neutral"
          />
          <MetricCard
            label="Auto-Resolved by AI"
            value={String(data.throughput.ai_auto_resolved)}
            sub="LOW risk, no human needed"
            icon={TrendingUp}
            color="bg-indigo-500"
            status="neutral"
          />
        </div>
      )}

      {/* Charts row */}
      <div className="grid gap-6 lg:grid-cols-2">
        {/* Override breakdown bar chart */}
        <Section
          title="Override Breakdown"
          subtitle="How often humans override AI recommendations (% of total reviews)"
        >
          {loading ? (
            <Skeleton className="h-56" />
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart
                data={overrideData}
                layout="vertical"
                margin={{ top: 0, right: 20, left: 0, bottom: 0 }}
              >
                <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#f1f5f9" />
                <XAxis
                  type="number"
                  tickFormatter={(v) => `${(v * 100).toFixed(0)}%`}
                  tick={{ fontSize: 11, fill: "#94a3b8" }}
                  axisLine={false}
                  tickLine={false}
                />
                <YAxis
                  type="category"
                  dataKey="name"
                  width={180}
                  tick={{ fontSize: 10, fill: "#64748b" }}
                  axisLine={false}
                  tickLine={false}
                />
                <Tooltip content={<ChartTooltip />} />
                <Bar dataKey="value" radius={[0, 4, 4, 0]} barSize={22}>
                  {overrideData.map((entry, index) => (
                    <Cell key={index} fill={entry.fill} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </Section>

        {/* Risk distribution chart */}
        <Section
          title="Risk Distribution"
          subtitle="Proportion of campaigns by AI risk level in selected period"
        >
          {loading ? (
            <Skeleton className="h-56" />
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart
                data={riskData}
                margin={{ top: 5, right: 20, left: 0, bottom: 5 }}
              >
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                <XAxis
                  dataKey="name"
                  tick={{ fontSize: 12, fill: "#64748b" }}
                  axisLine={false}
                  tickLine={false}
                />
                <YAxis
                  tickFormatter={(v) => `${(v * 100).toFixed(0)}%`}
                  tick={{ fontSize: 11, fill: "#94a3b8" }}
                  axisLine={false}
                  tickLine={false}
                />
                <Tooltip
                  formatter={(v) => [`${(Number(v) * 100).toFixed(1)}%`, "Share"]}
                />
                <Bar dataKey="value" radius={[4, 4, 0, 0]} barSize={60}>
                  {riskData.map((entry, index) => (
                    <Cell key={index} fill={entry.fill} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
          {!loading && data && (
            <div className="flex justify-center gap-6 mt-4">
              {riskData.map((d) => (
                <div key={d.name} className="flex items-center gap-1.5">
                  <div
                    className="h-2.5 w-2.5 rounded-sm"
                    style={{ backgroundColor: d.fill }}
                  />
                  <span className="text-xs text-slate-500">
                    {d.name} {formatPercent(d.value)}
                  </span>
                </div>
              ))}
            </div>
          )}
        </Section>
      </div>

      {/* Period label */}
      {data && (
        <p className="text-xs text-slate-400 text-center">
          Showing data for period: <strong>{data.period.replace(/_/g, " ")}</strong>
        </p>
      )}
    </div>
  );
}
