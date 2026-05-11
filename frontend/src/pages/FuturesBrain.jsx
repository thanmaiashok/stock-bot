import { useQuery } from "@tanstack/react-query";
import axios from "axios";
import {
  AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer,
  RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Legend,
} from "recharts";
import { Brain, Zap, TrendingUp, Activity, RefreshCw } from "lucide-react";

const api = (path) => axios.get(path).then(r => r.data);

const W_COLORS = {
  momentum:    "#f97316",
  ema:         "#3b82f6",
  rsi:         "#22c55e",
  bbands:      "#a855f7",
  consistency: "#06b6d4",
};
const W_LABELS = {
  momentum:    "Momentum",
  ema:         "EMA Cross",
  rsi:         "RSI",
  bbands:      "Bollinger",
  consistency: "Consistency",
};

const REGIME_BADGE = {
  TRENDING: "bg-blue-500/20 text-blue-400 border-blue-500/30",
  RANGING:  "bg-yellow-500/20 text-yellow-400 border-yellow-500/30",
  VOLATILE: "bg-red-500/20 text-red-400 border-red-500/30",
  UNKNOWN:  "bg-slate-700/40 text-slate-400 border-slate-600/30",
};

function WeightBar({ name, value, defaultVal }) {
  const color = W_COLORS[name];
  const pct   = Math.round(value * 100);
  const diff  = Math.round((value - defaultVal) * 100);
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-xs">
        <span className="font-medium" style={{ color }}>{W_LABELS[name]}</span>
        <div className="flex items-center gap-2">
          {diff !== 0 && (
            <span className={`text-[10px] font-mono ${diff > 0 ? "text-green-400" : "text-red-400"}`}>
              {diff > 0 ? "+" : ""}{diff}%
            </span>
          )}
          <span className="font-bold text-white font-mono">{pct}%</span>
        </div>
      </div>
      <div className="relative h-2 bg-white/5 rounded-full overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-700"
          style={{ width: `${Math.min(pct / 0.6, 100)}%`, background: color }}
        />
        {/* default marker */}
        <div
          className="absolute top-0 w-px h-full bg-white/30"
          style={{ left: `${(defaultVal / 0.6) * 100}%` }}
        />
      </div>
    </div>
  );
}

export default function FuturesBrain() {
  const { data, isLoading, refetch, isFetching } = useQuery({
    queryKey: ["futures-brain"],
    queryFn: () => api("/api/futures/brain"),
    refetchInterval: 30_000,
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64 text-slate-500">
        <Brain size={24} className="mr-2 animate-pulse" /> Initializing brain…
      </div>
    );
  }

  const weights   = data?.weights ?? {};
  const defaults  = data?.defaults ?? {};
  const history   = data?.history ?? [];
  const regime    = data?.regime ?? "UNKNOWN";
  const episodes  = data?.learning_episodes ?? 0;
  const winRate   = data?.recent_win_rate ?? 50;

  // Radar data: current vs default
  const radarData = Object.keys(weights).map(k => ({
    subject: W_LABELS[k],
    current: Math.round(weights[k] * 100),
    default: Math.round((defaults[k] ?? 0) * 100),
  }));

  // History as area chart data
  const histData = history.map(h => ({
    ep:          h.episode,
    momentum:    Math.round(h.momentum_w * 100),
    ema:         Math.round(h.ema_w * 100),
    rsi:         Math.round(h.rsi_w * 100),
    bbands:      Math.round(h.bbands_w * 100),
    consistency: Math.round(h.consistency_w * 100),
    win_rate:    Math.round(h.win_rate * 100),
  }));

  return (
    <div className="p-6 space-y-5 max-w-5xl">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          <Brain size={26} className="text-orange-400" />
          <div>
            <h1 className="text-2xl font-bold">AI Trading Brain</h1>
            <p className="text-slate-500 text-sm">Self-learning weight optimizer · policy-gradient updates after every trade</p>
          </div>
        </div>
        <button
          onClick={refetch}
          disabled={isFetching}
          className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-300 transition-colors"
        >
          <RefreshCw size={12} className={isFetching ? "animate-spin" : ""} />
          Refresh
        </button>
      </div>

      {/* Stat row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="bg-card border border-border rounded-xl p-4">
          <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">Learning Episodes</p>
          <p className="text-2xl font-bold text-orange-400">{episodes}</p>
          <p className="text-[10px] text-slate-600 mt-0.5">closed trades learned from</p>
        </div>
        <div className="bg-card border border-border rounded-xl p-4">
          <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">Recent Win Rate</p>
          <p className={`text-2xl font-bold ${winRate >= 50 ? "text-green-400" : "text-red-400"}`}>
            {winRate.toFixed(1)}%
          </p>
          <p className="text-[10px] text-slate-600 mt-0.5">exponential moving avg</p>
        </div>
        <div className="bg-card border border-border rounded-xl p-4">
          <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">Market Regime</p>
          <span className={`inline-flex items-center gap-1 text-sm font-bold px-2 py-0.5 rounded-full border mt-1 ${REGIME_BADGE[regime] ?? REGIME_BADGE.UNKNOWN}`}>
            <Activity size={10} /> {regime}
          </span>
          <p className="text-[10px] text-slate-600 mt-1">re-detected every 30 min</p>
        </div>
        <div className="bg-card border border-border rounded-xl p-4">
          <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">Recent P&L</p>
          <p className={`text-2xl font-bold ${(data?.recent_pnl ?? 0) >= 0 ? "text-green-400" : "text-red-400"}`}>
            {(data?.recent_pnl ?? 0) >= 0 ? "+" : ""}${data?.recent_pnl?.toFixed(2) ?? "0.00"}
          </p>
          <p className="text-[10px] text-slate-600 mt-0.5">last {data?.recent_trades ?? 0} trades</p>
        </div>
      </div>

      {/* Current weights + radar */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Weight bars */}
        <div className="bg-card border border-border rounded-xl p-4">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Current Weights</h2>
            <span className="text-[10px] text-slate-600">│ = default · bar = learned</span>
          </div>
          <div className="space-y-3">
            {Object.entries(weights).map(([k, v]) => (
              <WeightBar key={k} name={k} value={v} defaultVal={defaults[k] ?? 0} />
            ))}
          </div>

          <div className="mt-4 pt-3 border-t border-border">
            <p className="text-[10px] text-slate-600 leading-relaxed">
              Algorithm: <span className="text-slate-400">w += LR × outcome × component_score</span> per trade.
              Regime shifts apply a nudge toward regime-optimal weights.
              Weights bounded [5%, 60%] and renormalized.
            </p>
          </div>
        </div>

        {/* Radar chart */}
        <div className="bg-card border border-border rounded-xl p-4">
          <h2 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">
            Learned vs Default
          </h2>
          <ResponsiveContainer width="100%" height={220}>
            <RadarChart data={radarData}>
              <PolarGrid stroke="#1e293b" />
              <PolarAngleAxis dataKey="subject" tick={{ fontSize: 10, fill: "#64748b" }} />
              <PolarRadiusAxis domain={[0, 50]} tick={false} axisLine={false} />
              <Radar name="Default" dataKey="default" stroke="#475569" fill="#475569" fillOpacity={0.15} strokeWidth={1} />
              <Radar name="Learned" dataKey="current" stroke="#f97316" fill="#f97316" fillOpacity={0.25} strokeWidth={2} />
              <Legend iconSize={8} wrapperStyle={{ fontSize: 10, color: "#64748b" }} />
              <Tooltip
                contentStyle={{ background: "#0f1117", border: "1px solid #1e293b", borderRadius: 8, fontSize: 10 }}
                formatter={(v) => [`${v}%`]}
              />
            </RadarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Weight evolution history */}
      {histData.length > 0 ? (
        <div className="bg-card border border-border rounded-xl p-4">
          <h2 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">
            Weight Evolution — {histData.length} snapshots (logged every 5 episodes)
          </h2>
          <ResponsiveContainer width="100%" height={220}>
            <AreaChart data={histData} stackOffset="expand"
              margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
              <XAxis dataKey="ep" tick={{ fontSize: 9, fill: "#475569" }} tickLine={false}
                label={{ value: "Episode", position: "insideBottom", offset: -2, style: { fontSize: 9, fill: "#475569" } }} />
              <YAxis tickFormatter={v => `${Math.round(v * 100)}%`} tick={{ fontSize: 9, fill: "#475569" }} tickLine={false} axisLine={false} />
              <Tooltip
                contentStyle={{ background: "#0f1117", border: "1px solid #1e293b", borderRadius: 8 }}
                labelFormatter={v => `Episode ${v}`}
                formatter={(v, name) => [`${Math.round(v * 100)}%`, W_LABELS[name] ?? name]}
              />
              {Object.keys(W_COLORS).map(k => (
                <Area key={k} type="monotone" dataKey={k}
                  stackId="1"
                  stroke={W_COLORS[k]}
                  fill={W_COLORS[k]}
                  fillOpacity={0.7}
                  strokeWidth={0}
                />
              ))}
            </AreaChart>
          </ResponsiveContainer>
          <div className="flex flex-wrap gap-3 mt-2">
            {Object.entries(W_COLORS).map(([k, c]) => (
              <span key={k} className="flex items-center gap-1 text-[10px] text-slate-500">
                <span className="w-2 h-2 rounded-full inline-block" style={{ background: c }} />
                {W_LABELS[k]}
              </span>
            ))}
          </div>
        </div>
      ) : (
        <div className="bg-card border border-border rounded-xl p-8 text-center">
          <Zap size={32} className="mx-auto mb-3 text-slate-700" />
          <p className="text-slate-500 text-sm">No learning history yet</p>
          <p className="text-slate-600 text-xs mt-1">
            Brain logs a snapshot every 5 closed trades. Open some positions and let the bot trade to start building history.
          </p>
        </div>
      )}

      {/* How it works */}
      <div className="bg-card border border-border rounded-xl p-4">
        <h2 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">How The Brain Works</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-[11px] text-slate-500">
          <div className="space-y-1.5">
            <p className="text-slate-300 font-semibold">1. Signal Generation</p>
            <p>Every 8s, the engine computes 5 raw component scores (momentum, EMA, RSI, Bollinger, consistency) for all 42 instruments using live prices.</p>
          </div>
          <div className="space-y-1.5">
            <p className="text-slate-300 font-semibold">2. Weighted Decision</p>
            <p>Scores are multiplied by brain's current weights and summed. If composite &gt; 0.08 → LONG, &lt; −0.08 → SHORT. Bot opens position + snapshots component scores.</p>
          </div>
          <div className="space-y-1.5">
            <p className="text-slate-300 font-semibold">3. Policy-Gradient Update</p>
            <p>When trade closes: outcome = P&L / 3.0 (normalized). For each component: w += 0.015 × outcome × score. Regime shifts (TRENDING/RANGING/VOLATILE) apply additional nudge.</p>
          </div>
        </div>
      </div>
    </div>
  );
}
