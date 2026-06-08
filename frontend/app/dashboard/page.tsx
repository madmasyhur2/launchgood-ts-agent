"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  getCampaignQueue,
  type CampaignQueueItem,
  type RiskLevel,
} from "@/lib/api";
import { riskColors, recColors, formatCurrency, formatMinutes, cn } from "@/lib/utils";
import {
  RefreshCw,
  AlertTriangle,
  ChevronRight,
  Filter,
  Clock,
  TrendingUp,
  CheckCircle,
  XCircle,
  AlignJustify,
} from "lucide-react";

const RISK_FILTERS: (RiskLevel | "ALL")[] = ["ALL", "HIGH", "MEDIUM", "LOW"];
const AUTO_REFRESH_MS = 30_000;

// ── Sub-components ─────────────────────────────────────────────────────────

function RiskBadge({ level }: { level: RiskLevel | null }) {
  if (!level) return <span className="text-slate-400 text-xs">—</span>;
  const c = riskColors(level);
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold ring-1 ring-inset",
        c.badge
      )}
    >
      <span className={cn("h-1.5 w-1.5 rounded-full", c.dot)} />
      {level}
    </span>
  );
}

function RecBadge({ rec }: { rec: string | null }) {
  if (!rec) return <span className="text-slate-400 text-xs">—</span>;
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-1 text-xs font-medium",
        recColors(rec as "APPROVE" | "ESCALATE" | "REJECT")
      )}
    >
      {rec}
    </span>
  );
}

function ScoreBar({ score }: { score: number | null }) {
  if (score == null) return <span className="text-slate-400 text-xs">—</span>;
  const color =
    score >= 70 ? "bg-red-500" : score >= 30 ? "bg-amber-500" : "bg-emerald-500";
  return (
    <div className="flex items-center gap-2">
      <div className="w-16 h-1.5 rounded-full bg-slate-200 overflow-hidden">
        <div
          className={cn("h-full rounded-full transition-all", color)}
          style={{ width: `${score}%` }}
        />
      </div>
      <span className="text-xs font-mono text-slate-600 tabular-nums">
        {score}
      </span>
    </div>
  );
}

function StatCard({
  label,
  value,
  icon: Icon,
  color,
}: {
  label: string;
  value: string | number;
  icon: React.ElementType;
  color: string;
}) {
  return (
    <div className="bg-white rounded-xl border border-slate-200 p-4 flex items-center gap-4">
      <div className={cn("h-10 w-10 rounded-lg flex items-center justify-center", color)}>
        <Icon size={18} className="text-white" />
      </div>
      <div>
        <p className="text-2xl font-bold text-slate-900">{value}</p>
        <p className="text-xs text-slate-500 mt-0.5">{label}</p>
      </div>
    </div>
  );
}

function SkeletonRow() {
  return (
    <tr>
      {Array.from({ length: 6 }).map((_, i) => (
        <td key={i} className="px-4 py-3">
          <div className="h-4 bg-slate-200 rounded animate-pulse" style={{ width: `${60 + i * 10}%` }} />
        </td>
      ))}
    </tr>
  );
}

// ── Main page ──────────────────────────────────────────────────────────────

export default function DashboardPage() {
  const router = useRouter();
  const [data, setData] = useState<CampaignQueueItem[]>([]);
  const [total, setTotal] = useState(0);
  const [pending, setPending] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [riskFilter, setRiskFilter] = useState<RiskLevel | "ALL">("ALL");
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const load = useCallback(
    async (silent = false) => {
      if (!silent) setLoading(true);
      else setRefreshing(true);
      setError(null);
      try {
        const res = await getCampaignQueue({
          risk_level: riskFilter === "ALL" ? undefined : riskFilter,
          limit: 50,
        });
        setData(res.items);
        setTotal(res.total);
        setPending(res.pending);
        setLastRefresh(new Date());
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load queue");
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [riskFilter]
  );

  // Initial load + filter change
  useEffect(() => {
    load();
  }, [load]);

  // Auto-refresh every 30s
  useEffect(() => {
    timerRef.current = setInterval(() => load(true), AUTO_REFRESH_MS);
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [load]);

  const highCount = data.filter((d) => d.risk_level === "HIGH").length;
  const medCount = data.filter((d) => d.risk_level === "MEDIUM").length;
  const lowCount = data.filter((d) => d.risk_level === "LOW").length;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Campaign Queue</h1>
          <p className="text-sm text-slate-500 mt-1">
            AI-screened campaigns awaiting human review · sorted by risk
          </p>
        </div>
        <button
          onClick={() => load(true)}
          disabled={refreshing}
          className="flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3.5 py-2 text-sm font-medium text-slate-700 shadow-sm hover:bg-slate-50 disabled:opacity-50 transition-all"
        >
          <RefreshCw size={14} className={refreshing ? "animate-spin" : ""} />
          Refresh
        </button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <StatCard label="Total campaigns" value={total} icon={AlignJustify} color="bg-blue-500" />
        <StatCard label="Awaiting review" value={pending} icon={Clock} color="bg-amber-500" />
        <StatCard label="High risk" value={highCount} icon={AlertTriangle} color="bg-red-500" />
        <StatCard label="Low risk / clear" value={lowCount} icon={CheckCircle} color="bg-emerald-500" />
      </div>

      {/* Filter bar */}
      <div className="flex items-center gap-2">
        <Filter size={14} className="text-slate-400" />
        <span className="text-sm text-slate-500 mr-1">Filter:</span>
        {RISK_FILTERS.map((f) => (
          <button
            key={f}
            onClick={() => setRiskFilter(f)}
            className={cn(
              "rounded-full px-3 py-1 text-xs font-medium border transition-all",
              riskFilter === f
                ? f === "HIGH"
                  ? "bg-red-100 border-red-300 text-red-800"
                  : f === "MEDIUM"
                  ? "bg-amber-100 border-amber-300 text-amber-800"
                  : f === "LOW"
                  ? "bg-emerald-100 border-emerald-300 text-emerald-800"
                  : "bg-blue-100 border-blue-300 text-blue-800"
                : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
            )}
          >
            {f}
          </button>
        ))}
        {lastRefresh && (
          <span className="ml-auto text-xs text-slate-400">
            Updated {lastRefresh.toLocaleTimeString()}
            {" · "}auto-refresh in 30s
          </span>
        )}
      </div>

      {/* Error */}
      {error && (
        <div className="flex items-center gap-3 rounded-xl border border-red-200 bg-red-50 px-4 py-3">
          <AlertTriangle size={16} className="text-red-500 shrink-0" />
          <p className="text-sm text-red-700">{error}</p>
          <button
            onClick={() => load()}
            className="ml-auto text-sm font-medium text-red-700 hover:text-red-900 underline"
          >
            Retry
          </button>
        </div>
      )}

      {/* Table */}
      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-100 bg-slate-50">
              <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-500">
                Risk
              </th>
              <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-500">
                Campaign
              </th>
              <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-500">
                Score
              </th>
              <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-500">
                AI Rec.
              </th>
              <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-500">
                In Queue
              </th>
              <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-500">
                Status
              </th>
              <th className="w-10" />
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {loading &&
              Array.from({ length: 6 }).map((_, i) => <SkeletonRow key={i} />)}
            {!loading && data.length === 0 && (
              <tr>
                <td colSpan={7} className="px-4 py-16 text-center text-slate-400">
                  <CheckCircle size={32} className="mx-auto mb-2 text-slate-300" />
                  No campaigns in queue
                </td>
              </tr>
            )}
            {!loading &&
              data.map((item) => (
                <tr
                  key={item.campaign_id}
                  onClick={() =>
                    router.push(`/dashboard/campaign/${item.campaign_id}`)
                  }
                  className={cn(
                    "cursor-pointer transition-colors hover:bg-slate-50 group",
                    item.risk_level === "HIGH" &&
                      "border-l-4 border-l-red-400"
                  )}
                >
                  <td className="px-4 py-3">
                    <RiskBadge level={item.risk_level} />
                  </td>
                  <td className="px-4 py-3 max-w-xs">
                    <p className="font-medium text-slate-900 truncate group-hover:text-blue-700 transition-colors">
                      {item.title}
                    </p>
                    <p className="text-xs text-slate-400 mt-0.5">
                      {item.category ?? "—"} ·{" "}
                      {formatCurrency(item.goal_amount, item.currency ?? "USD")}
                      {item.beneficiary_country && ` · ${item.beneficiary_country}`}
                    </p>
                  </td>
                  <td className="px-4 py-3">
                    <ScoreBar score={item.risk_score} />
                  </td>
                  <td className="px-4 py-3">
                    <RecBadge rec={item.recommendation} />
                  </td>
                  <td className="px-4 py-3 text-xs text-slate-500 tabular-nums">
                    {formatMinutes(item.time_in_queue_minutes)}
                  </td>
                  <td className="px-4 py-3">
                    <span className="inline-flex items-center rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-600 capitalize">
                      {item.status}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <ChevronRight
                      size={14}
                      className="text-slate-300 group-hover:text-blue-500 transition-colors"
                    />
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
