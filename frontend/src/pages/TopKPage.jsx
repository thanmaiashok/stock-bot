import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { Layers, TrendingUp, TrendingDown, Loader2, RefreshCw, ChevronRight, ArrowUpDown, Brain, AlertTriangle } from "lucide-react";

const api = (url) => axios.get(url).then((r) => r.data);

const SIG_COLORS = { BUY: "text-green-400", SELL: "text-red-400", HOLD: "text-yellow-400" };
const STAGE_COLORS = { 1: "text-yellow-400", 2: "text-green-400", 3: "text-orange-400", 4: "text-red-400" };

function PatternBadge({ pattern }) {
  const MAP = {
    VCP: "bg-purple-500/20 text-purple-300",
    NR7: "bg-blue-500/20 text-blue-300",
    NR7_INSIDE_DAY: "bg-blue-600/20 text-blue-200",
    BB_SQUEEZE: "bg-yellow-500/20 text-yellow-300",
    STAGE2: "bg-green-500/20 text-green-300",
  };
  const cls = MAP[pattern] ?? "bg-slate-700 text-slate-400";
  return <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold ${cls}`}>{pattern.replace(/_/g, " ")}</span>;
}

export default function TopKPage() {
  const nav = useNavigate();
  const [k, setK] = useState(10);
  const [minStage, setMinStage] = useState("");
  const [tab, setTab] = useState("longs");

  const params = new URLSearchParams({ k });
  if (minStage) params.set("min_stage", minStage);

  const { data, isLoading, refetch, isFetching } = useQuery({
    queryKey: ["topk", k, minStage],
    queryFn: () => api(`/api/topk?${params}`),
    staleTime: 60_000,
  });

  const { data: rotData } = useQuery({
    queryKey: ["topk-rotation", k],
    queryFn: () => api(`/api/topk/rotation?k=${k}`),
    staleTime: 60_000,
  });

  const { data: fgData } = useQuery({
    queryKey: ["fear-greed"],
    queryFn: () => api("/api/market/fear-greed"),
    staleTime: 3_600_000,
  });

  const items = tab === "longs" ? (data?.longs ?? []) : (data?.shorts ?? []);

  return (
    <div className="p-6 space-y-5">
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <div className="flex items-center gap-2">
            <Layers size={20} className="text-accent" />
            <h1 className="text-2xl font-bold">TopK Portfolio Rotation</h1>
          </div>
          <p className="text-slate-500 text-sm mt-0.5">
            Composite ranking: signal + pattern + momentum · Inspired by Qlib TopK strategy
          </p>
        </div>
        <button
          onClick={() => refetch()}
          disabled={isFetching}
          className="flex items-center gap-2 px-3 py-2 bg-card border border-border rounded-lg text-xs text-slate-400 hover:text-white hover:border-accent/50 transition-colors"
        >
          <RefreshCw size={12} className={isFetching ? "animate-spin" : ""} />
          Recalculate
        </button>
      </div>

      {/* Fear & Greed widget */}
      {fgData && (
        <div className={`p-4 rounded-xl border flex items-center gap-4 ${
          fgData.score <= 25 ? "bg-green-500/10 border-green-500/30" :
          fgData.score >= 75 ? "bg-red-500/10 border-red-500/30" :
          "bg-card border-border"
        }`}>
          <Brain size={28} className={
            fgData.score <= 25 ? "text-green-400" :
            fgData.score >= 75 ? "text-red-400" : "text-yellow-400"
          } />
          <div className="flex-1">
            <div className="flex items-center gap-3">
              <span className="font-bold text-xl">{fgData.score}</span>
              <span className={`text-sm font-medium ${
                fgData.score <= 25 ? "text-green-400" :
                fgData.score >= 75 ? "text-red-400" : "text-yellow-400"
              }`}>{fgData.label}</span>
              <span className="text-xs text-slate-500 ml-auto">{fgData.interpretation?.action}</span>
            </div>
            <div className="flex gap-3 mt-1">
              {fgData.components && Object.entries(fgData.components).map(([k, v]) => (
                <span key={k} className="text-[10px] text-slate-500">{k}: <span className="text-slate-300">{v}</span></span>
              ))}
            </div>
          </div>
          {fgData.score <= 25 && <span className="text-xs text-green-400 font-medium">Buffett buy zone</span>}
          {fgData.score >= 75 && <AlertTriangle size={14} className="text-red-400" />}
        </div>
      )}

      {/* Controls */}
      <div className="flex items-center gap-3 flex-wrap">
        <div className="flex items-center gap-1">
          <span className="text-xs text-slate-500">K =</span>
          {[5, 10, 15, 20].map((n) => (
            <button
              key={n}
              onClick={() => setK(n)}
              className={`px-3 py-1.5 rounded-lg text-xs border transition-colors ${
                k === n
                  ? "bg-accent/20 text-accent border-accent/30"
                  : "text-slate-500 border-transparent hover:border-border"
              }`}
            >{n}</button>
          ))}
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-500">Min Stage</span>
          <select
            value={minStage}
            onChange={(e) => setMinStage(e.target.value)}
            className="bg-card border border-border rounded-lg px-2 py-1.5 text-xs text-slate-300 outline-none focus:border-accent"
          >
            <option value="">Any</option>
            <option value="2">Stage 2+ only</option>
          </select>
        </div>
        {isLoading && <Loader2 size={14} className="animate-spin text-slate-500" />}
      </div>

      {/* Rotation summary */}
      {rotData && (
        <div className="bg-card border border-border rounded-xl p-4">
          <div className="flex items-center gap-2 mb-3">
            <ArrowUpDown size={14} className="text-accent" />
            <span className="text-xs font-semibold text-slate-300 uppercase tracking-wide">Rotation vs Current Holdings</span>
          </div>
          <div className="grid grid-cols-3 gap-4 text-xs">
            <div>
              <p className="text-slate-500 mb-1">Buy ({rotData.add?.length ?? 0})</p>
              {rotData.add?.length > 0
                ? rotData.add.map((t) => <span key={t} className="inline-block mr-2 font-mono text-green-400">{t}</span>)
                : <span className="text-slate-600">—</span>
              }
            </div>
            <div>
              <p className="text-slate-500 mb-1">Sell ({rotData.remove?.length ?? 0})</p>
              {rotData.remove?.length > 0
                ? rotData.remove.map((t) => <span key={t} className="inline-block mr-2 font-mono text-red-400">{t}</span>)
                : <span className="text-slate-600">—</span>
              }
            </div>
            <div>
              <p className="text-slate-500 mb-1">Keep ({rotData.keep?.length ?? 0})</p>
              {rotData.keep?.length > 0
                ? rotData.keep.map((t) => <span key={t} className="inline-block mr-2 font-mono text-slate-400">{t}</span>)
                : <span className="text-slate-600">—</span>
              }
            </div>
          </div>
        </div>
      )}

      {/* Tab toggle */}
      <div className="flex gap-1">
        <button
          onClick={() => setTab("longs")}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
            tab === "longs" ? "bg-green-500/20 text-green-400" : "text-slate-500 hover:text-slate-300"
          }`}
        >
          <TrendingUp size={12} /> Longs ({data?.longs?.length ?? 0})
        </button>
        <button
          onClick={() => setTab("shorts")}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
            tab === "shorts" ? "bg-red-500/20 text-red-400" : "text-slate-500 hover:text-slate-300"
          }`}
        >
          <TrendingDown size={12} /> Shorts ({data?.shorts?.length ?? 0})
        </button>
      </div>

      {/* Table */}
      <div className="bg-card border border-border rounded-xl overflow-hidden">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-border">
              <th className="text-left px-4 py-2.5 text-slate-500 font-normal">#</th>
              <th className="text-left px-4 py-2.5 text-slate-500 font-normal">Ticker</th>
              <th className="text-left px-4 py-2.5 text-slate-500 font-normal">Sector</th>
              <th className="text-right px-4 py-2.5 text-slate-500 font-normal">Signal</th>
              <th className="text-right px-4 py-2.5 text-slate-500 font-normal">Composite</th>
              <th className="text-right px-4 py-2.5 text-slate-500 font-normal">Momentum</th>
              <th className="text-left px-4 py-2.5 text-slate-500 font-normal">Patterns</th>
              <th className="text-center px-4 py-2.5 text-slate-500 font-normal">Stage</th>
              <th className="px-4 py-2.5" />
            </tr>
          </thead>
          <tbody>
            {items.map((item, i) => (
              <tr
                key={item.ticker}
                className="border-b border-white/5 hover:bg-white/5 cursor-pointer transition-colors"
                onClick={() => nav(`/stocks/stock/${item.ticker}`)}
              >
                <td className="px-4 py-2.5 text-slate-600 font-mono">{i + 1}</td>
                <td className="px-4 py-2.5">
                  <span className="font-mono font-bold text-white">{item.ticker}</span>
                  {item.name && <span className="text-slate-500 ml-2 text-[9px]">{item.name}</span>}
                </td>
                <td className="px-4 py-2.5 text-slate-400">{item.sector || "—"}</td>
                <td className={`px-4 py-2.5 text-right font-bold ${SIG_COLORS[item.signal] ?? "text-slate-400"}`}>
                  {item.signal}
                </td>
                <td className="px-4 py-2.5 text-right font-mono">
                  <span className={item.composite_score >= 0 ? "text-green-400" : "text-red-400"}>
                    {item.composite_score >= 0 ? "+" : ""}{item.composite_score.toFixed(3)}
                  </span>
                </td>
                <td className="px-4 py-2.5 text-right font-mono text-slate-400">
                  {item.momentum_score >= 0 ? "+" : ""}{item.momentum_score.toFixed(2)}
                </td>
                <td className="px-4 py-2.5">
                  <div className="flex flex-wrap gap-1">
                    {item.patterns?.map((p) => <PatternBadge key={p} pattern={p} />)}
                  </div>
                </td>
                <td className={`px-4 py-2.5 text-center font-bold ${STAGE_COLORS[item.stage] ?? "text-slate-500"}`}>
                  {item.stage || "?"} {item.stage_name ? `· ${item.stage_name}` : ""}
                </td>
                <td className="px-4 py-2.5">
                  <ChevronRight size={12} className="text-slate-600" />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!isLoading && items.length === 0 && (
          <div className="text-center py-12 text-slate-600">
            <Layers size={32} className="mx-auto mb-2 opacity-30" />
            <p>No signals yet — run signal generation first</p>
          </div>
        )}
      </div>
    </div>
  );
}
