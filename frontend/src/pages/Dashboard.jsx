import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { TrendingUp, TrendingDown, DollarSign, Activity, Zap, Brain, BarChart2, Flame } from "lucide-react";
import SignalCard from "../components/SignalCard";
import MarketCommentary from "../components/MarketCommentary";

const api = (path) => axios.get(path).then((r) => r.data);
const REFRESH = 30_000; // 30s auto-refresh

const PATTERN_COLORS = {
  VCP: "bg-purple-500/20 text-purple-300",
  NR7: "bg-blue-500/20 text-blue-300",
  CUP_HANDLE: "bg-yellow-500/20 text-yellow-300",
  STAGE2: "bg-green-500/20 text-green-300",
  BB_SQUEEZE: "bg-orange-500/20 text-orange-300",
};

function StatCard({ label, value, sub, icon: Icon, color = "text-white" }) {
  return (
    <div className="bg-card border border-border rounded-xl p-4">
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-[11px] text-slate-500 uppercase tracking-wider">{label}</span>
        {Icon && <Icon size={14} className="text-slate-600" />}
      </div>
      <p className={`text-xl font-bold ${color}`}>{value}</p>
      {sub && <p className="text-[11px] text-slate-500 mt-0.5">{sub}</p>}
    </div>
  );
}

function FearGreedBar({ score, label }) {
  const color = score <= 25 ? "bg-green-500" : score <= 45 ? "bg-yellow-500" : score <= 65 ? "bg-orange-400" : "bg-red-500";
  const textColor = score <= 25 ? "text-green-400" : score <= 45 ? "text-yellow-400" : score <= 65 ? "text-orange-400" : "text-red-400";
  return (
    <div className="bg-card border border-border rounded-xl p-4">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <Brain size={14} className={textColor} />
          <span className="text-xs font-medium text-slate-400">Fear & Greed</span>
        </div>
        <span className={`text-sm font-bold ${textColor}`}>{score} · {label}</span>
      </div>
      <div className="h-2 bg-white/5 rounded-full overflow-hidden">
        <div className={`h-full rounded-full transition-all ${color}`} style={{ width: `${score}%` }} />
      </div>
      <div className="flex justify-between mt-1">
        <span className="text-[9px] text-green-500">Extreme Fear</span>
        <span className="text-[9px] text-red-500">Extreme Greed</span>
      </div>
    </div>
  );
}

function BreadthCard({ data }) {
  if (!data?.latest) return null;
  const { mcclellan, trin, ad_ratio } = data.latest;
  const bullish = data.signals?.breadth_bull;
  const bearish = data.signals?.breadth_bear;
  return (
    <div className="bg-card border border-border rounded-xl p-4">
      <div className="flex items-center gap-2 mb-2">
        <BarChart2 size={14} className="text-slate-500" />
        <span className="text-xs font-medium text-slate-400">Market Breadth</span>
        <span className={`ml-auto text-[10px] font-bold px-2 py-0.5 rounded-full ${
          bullish ? "bg-green-500/20 text-green-400" :
          bearish ? "bg-red-500/20 text-red-400" : "bg-slate-700 text-slate-400"
        }`}>{data.breadth_label?.split(" ")[0] ?? "Neutral"}</span>
      </div>
      <div className="grid grid-cols-3 gap-2">
        <div className="text-center">
          <p className={`text-sm font-bold ${mcclellan >= 0 ? "text-green-400" : "text-red-400"}`}>
            {mcclellan >= 0 ? "+" : ""}{mcclellan?.toFixed(0)}
          </p>
          <p className="text-[9px] text-slate-600">McClellan</p>
        </div>
        <div className="text-center">
          <p className={`text-sm font-bold ${trin <= 1 ? "text-green-400" : "text-red-400"}`}>
            {trin?.toFixed(2)}
          </p>
          <p className="text-[9px] text-slate-600">TRIN</p>
        </div>
        <div className="text-center">
          <p className="text-sm font-bold text-slate-300">{ad_ratio?.toFixed(1)}x</p>
          <p className="text-[9px] text-slate-600">Adv/Dec</p>
        </div>
      </div>
    </div>
  );
}

function PatternAlerts({ items }) {
  const nav = useNavigate();
  if (!items?.length) return null;
  return (
    <div>
      <div className="flex items-center gap-2 mb-2">
        <Flame size={14} className="text-orange-400" />
        <h2 className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Pattern Alerts</h2>
      </div>
      <div className="flex flex-wrap gap-2">
        {items.slice(0, 8).map((item) => (
          <button
            key={item.ticker}
            onClick={() => nav(`/stocks/stock/${item.ticker}`)}
            className="flex items-center gap-1.5 bg-card border border-border rounded-lg px-2.5 py-1.5 hover:border-accent/40 transition-colors"
          >
            <span className="text-xs font-mono font-bold">{item.ticker}</span>
            {(item.patterns || []).slice(0, 2).map((p) => (
              <span key={p} className={`px-1 py-px rounded text-[8px] font-bold ${PATTERN_COLORS[p] ?? "bg-slate-700 text-slate-400"}`}>
                {p.replace(/_/g, " ")}
              </span>
            ))}
          </button>
        ))}
      </div>
    </div>
  );
}

function MomentumLeaderboard() {
  const nav = useNavigate();
  const { data = [] } = useQuery({
    queryKey: ["momentum-rank"],
    queryFn: () => api("/api/universe/momentum-rank?limit=10"),
    staleTime: 5 * 60_000,
    refetchInterval: 5 * 60_000,
  });

  if (!data.length) return null;

  return (
    <div>
      <div className="flex items-center gap-2 mb-2">
        <TrendingUp size={14} className="text-accent" />
        <h2 className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Momentum Leaders</h2>
      </div>
      <div className="space-y-1">
        {data.slice(0, 8).map((item, i) => {
          const pos = item.risk_adj_score >= 0;
          const barW = Math.min(Math.abs(item.risk_adj_score) * 60, 100);
          return (
            <div
              key={item.ticker}
              className="flex items-center gap-2 py-1 px-2 rounded-lg hover:bg-white/5 cursor-pointer transition-colors"
              onClick={() => nav(`/stocks/stock/${item.ticker}`)}
            >
              <span className="text-[10px] text-slate-600 w-4 shrink-0">{i + 1}</span>
              <span className="text-xs font-mono font-bold w-14 shrink-0">{item.ticker}</span>
              <div className="flex-1 h-1 bg-white/5 rounded-full overflow-hidden">
                <div className={`h-full rounded-full ${pos ? "bg-green-500" : "bg-red-500"}`} style={{ width: `${barW}%` }} />
              </div>
              <span className={`text-[10px] font-mono w-12 text-right shrink-0 ${pos ? "text-green-400" : "text-red-400"}`}>
                {pos ? "+" : ""}{item.momentum_30d}%
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default function Dashboard() {
  const nav = useNavigate();

  const { data: signals = [] } = useQuery({
    queryKey: ["signals"],
    queryFn: () => api("/api/signals?limit=30"),
    refetchInterval: REFRESH,
    staleTime: REFRESH,
  });

  const { data: portfolio } = useQuery({
    queryKey: ["portfolio"],
    queryFn: () => api("/api/portfolio"),
    refetchInterval: REFRESH,
    staleTime: REFRESH,
  });

  const { data: stats } = useQuery({
    queryKey: ["universe-stats"],
    queryFn: () => api("/api/universe/stats"),
    staleTime: 5 * 60_000,
  });

  const { data: fg } = useQuery({
    queryKey: ["fear-greed"],
    queryFn: () => api("/api/market/fear-greed"),
    staleTime: 60 * 60_000,
    refetchInterval: 60 * 60_000,
  });

  const { data: breadth } = useQuery({
    queryKey: ["breadth"],
    queryFn: () => api("/api/market/breadth?days=10"),
    staleTime: 30 * 60_000,
    refetchInterval: 30 * 60_000,
  });

  const { data: patterns = [] } = useQuery({
    queryKey: ["patterns-top-dash"],
    queryFn: () => api("/api/patterns/scan/top?limit=20"),
    staleTime: 5 * 60_000,
    refetchInterval: 5 * 60_000,
  });

  const buys  = signals.filter((s) => s.signal === "BUY").slice(0, 6);
  const sells = signals.filter((s) => s.signal === "SELL").slice(0, 3);
  const pnl   = portfolio?.unrealized_pnl ?? 0;

  return (
    <div className="p-5 space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold">Dashboard</h1>
          <p className="text-slate-500 text-xs mt-0.5">
            {stats ? `${stats.total_active?.toLocaleString()} stocks · ${stats.tier2_deep_analysis} in deep analysis` : "Loading…"}
            <span className="ml-2 text-slate-700">· auto-refresh 30s</span>
          </p>
        </div>
      </div>

      <MarketCommentary mode="stocks" />

      {/* Portfolio stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <StatCard
          label="Portfolio Value"
          value={portfolio ? `$${portfolio.total_value?.toLocaleString()}` : "—"}
          sub={`Cash: $${portfolio?.cash?.toLocaleString() ?? "—"}`}
          icon={DollarSign}
        />
        <StatCard
          label="Unrealized P&L"
          value={portfolio ? `${pnl >= 0 ? "+" : ""}$${pnl?.toFixed(2)}` : "—"}
          icon={pnl >= 0 ? TrendingUp : TrendingDown}
          color={pnl >= 0 ? "text-green-400" : "text-red-400"}
        />
        <StatCard
          label="Open Positions"
          value={portfolio?.positions?.length ?? "—"}
          sub={`Holdings: $${portfolio?.holdings_value?.toLocaleString() ?? "—"}`}
          icon={Activity}
        />
        <StatCard
          label="Live Signals"
          value={signals.length}
          sub={`BUY: ${signals.filter(s => s.signal === "BUY").length} · SELL: ${signals.filter(s => s.signal === "SELL").length}`}
          icon={Zap}
          color={signals.length > 0 ? "text-accent" : "text-white"}
        />
      </div>

      {/* Market regime row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        {fg && <FearGreedBar score={fg.score} label={fg.label} />}
        {breadth && <BreadthCard data={breadth} />}
      </div>

      {/* Pattern alerts */}
      {patterns.length > 0 && <PatternAlerts items={patterns} />}

      {/* Two-column: momentum + signals */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <MomentumLeaderboard />

        <div>
          <div className="flex items-center gap-2 mb-2">
            <Zap size={14} className="text-accent" />
            <h2 className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Top BUY Signals</h2>
            <button onClick={() => nav("signals")} className="ml-auto text-[10px] text-slate-600 hover:text-slate-400">
              View all →
            </button>
          </div>
          {buys.length === 0 ? (
            <p className="text-slate-600 text-xs py-4">No high-confidence BUY signals yet · signals run every 15 min</p>
          ) : (
            <div className="grid grid-cols-2 gap-2">
              {buys.map((s) => <SignalCard key={s.ticker} signal={s} />)}
            </div>
          )}
        </div>
      </div>

      {/* Sell signals (compact) */}
      {sells.length > 0 && (
        <div>
          <div className="flex items-center gap-2 mb-2">
            <TrendingDown size={14} className="text-red-400" />
            <h2 className="text-xs font-semibold text-slate-400 uppercase tracking-wider">SELL Signals</h2>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
            {sells.map((s) => <SignalCard key={s.ticker} signal={s} />)}
          </div>
        </div>
      )}
    </div>
  );
}
