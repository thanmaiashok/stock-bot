import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { Search, Loader2, TrendingUp, Zap, BarChart2, Activity, ChevronRight } from "lucide-react";

const api = (url) => axios.get(url).then((r) => r.data);

const PATTERN_COLORS = {
  VCP: "bg-purple-500/20 text-purple-300 border-purple-500/30",
  NR7: "bg-blue-500/20 text-blue-300 border-blue-500/30",
  NR7_INSIDE_DAY: "bg-blue-600/20 text-blue-200 border-blue-600/30",
  INSIDE_DAY: "bg-sky-500/20 text-sky-300 border-sky-500/30",
  BB_SQUEEZE: "bg-yellow-500/20 text-yellow-300 border-yellow-500/30",
  STAGE2: "bg-green-500/20 text-green-300 border-green-500/30",
  STAGE4_AVOID: "bg-red-500/20 text-red-300 border-red-500/30",
};

const STAGE_COLORS = {
  1: "text-yellow-400",
  2: "text-green-400",
  3: "text-orange-400",
  4: "text-red-400",
  0: "text-slate-500",
};

function PatternBadge({ pattern }) {
  const cls = PATTERN_COLORS[pattern] ?? "bg-slate-700 text-slate-300 border-slate-600";
  return (
    <span className={`px-1.5 py-0.5 rounded border text-[9px] font-bold uppercase tracking-wide ${cls}`}>
      {pattern.replace(/_/g, " ")}
    </span>
  );
}

function ScoreBar({ score, max = 100 }) {
  const pct = Math.min(100, (score / max) * 100);
  const color = pct >= 65 ? "bg-green-500" : pct >= 40 ? "bg-yellow-500" : "bg-slate-600";
  return (
    <div className="w-full h-1 bg-slate-800 rounded-full overflow-hidden">
      <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
    </div>
  );
}

function SingleTickerPanel({ ticker }) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["patterns", ticker],
    queryFn: () => api(`/api/patterns/${ticker}`),
    enabled: !!ticker,
    staleTime: 30_000,
  });

  if (isLoading) return <div className="flex items-center gap-2 text-slate-500 py-8"><Loader2 size={16} className="animate-spin" /> Running pattern scan...</div>;
  if (isError) return <div className="text-red-400 text-sm py-4">No data for {ticker}. Check ticker symbol.</div>;
  if (!data) return null;

  const { vcp, nr7, stage, bb_squeeze, patterns, pattern_score } = data;

  return (
    <div className="space-y-4">
      {/* Summary bar */}
      <div className="bg-card border border-border rounded-xl p-4 flex items-center gap-4 flex-wrap">
        <div>
          <p className="text-2xl font-bold font-mono">{data.ticker}</p>
          <p className="text-xs text-slate-500">Pattern Score: <span className="text-white font-mono">{(pattern_score * 100).toFixed(0)}/100</span></p>
        </div>
        <div className="flex-1 min-w-[100px]">
          <ScoreBar score={pattern_score * 100} />
        </div>
        <div className="flex flex-wrap gap-1.5">
          {patterns?.length > 0
            ? patterns.map((p) => <PatternBadge key={p} pattern={p} />)
            : <span className="text-xs text-slate-500">No patterns detected</span>
          }
        </div>
      </div>

      <div className="grid md:grid-cols-2 xl:grid-cols-4 gap-4">
        {/* VCP */}
        <div className="bg-card border border-border rounded-xl p-4 space-y-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Activity size={14} className="text-purple-400" />
              <span className="text-xs font-semibold text-slate-300">VCP</span>
            </div>
            <span className={`text-xs font-bold ${vcp?.detected ? "text-green-400" : "text-slate-500"}`}>
              {vcp?.detected ? "DETECTED" : "—"}
            </span>
          </div>
          <ScoreBar score={vcp?.score ?? 0} />
          <div className="text-[10px] text-slate-500 space-y-0.5">
            <div>Score: <span className="text-slate-300">{vcp?.score ?? 0}</span></div>
            <div>Bases: <span className="text-slate-300">{vcp?.num_bases ?? 0}</span> {vcp?.contracting_depth && "✓ contracting"}</div>
            {vcp?.pivot && <div>Pivot: <span className="text-slate-300 font-mono">{vcp.pivot}</span> ({vcp.distance_to_pivot_pct > 0 ? "+" : ""}{vcp.distance_to_pivot_pct}%)</div>}
            {vcp?.ready_for_breakout && <div className="text-green-400 font-semibold">⚡ Ready for breakout!</div>}
            {vcp?.bases_depths?.length > 0 && <div>Depths: {vcp.bases_depths.map(d => `${d}%`).join(" → ")}</div>}
          </div>
        </div>

        {/* NR7 / Inside Day */}
        <div className="bg-card border border-border rounded-xl p-4 space-y-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Zap size={14} className="text-blue-400" />
              <span className="text-xs font-semibold text-slate-300">NR7 / Inside Day</span>
            </div>
            <span className={`text-xs font-bold ${nr7?.detected ? "text-green-400" : "text-slate-500"}`}>
              {nr7?.detected ? nr7.subtype?.toUpperCase() : "—"}
            </span>
          </div>
          <ScoreBar score={nr7?.score ?? 0} />
          <div className="text-[10px] text-slate-500 space-y-0.5">
            <div>Score: <span className="text-slate-300">{nr7?.score ?? 0}</span></div>
            {nr7?.detected && <>
              <div>Trigger High: <span className="font-mono text-slate-300">{nr7.trigger_high}</span></div>
              <div>Range: <span className="text-slate-300">{nr7.range_pct?.toFixed(3)}%</span></div>
              <div>Vol Ratio: <span className="text-slate-300">{nr7.volume_ratio}</span> {nr7.volume_ratio < 0.9 && "✓ dry"}</div>
              <div>Above EMA21: <span className={nr7.close_above_ema21 ? "text-green-400" : "text-red-400"}>{nr7.close_above_ema21 ? "Yes" : "No"}</span></div>
              <div>Recency: <span className="text-slate-300">{nr7.recency_bars} bars ago</span></div>
            </>}
          </div>
        </div>

        {/* Stage */}
        <div className="bg-card border border-border rounded-xl p-4 space-y-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <TrendingUp size={14} className="text-green-400" />
              <span className="text-xs font-semibold text-slate-300">Weinstein Stage</span>
            </div>
            <span className={`text-lg font-bold ${STAGE_COLORS[stage?.stage ?? 0]}`}>
              {stage?.stage ?? "?"} — {stage?.stage_name ?? "Unknown"}
            </span>
          </div>
          <ScoreBar score={stage?.confidence ?? 0} />
          <div className="text-[10px] text-slate-500 space-y-0.5">
            <div>Confidence: <span className="text-slate-300">{stage?.confidence ?? 0}%</span></div>
            <div>MA200 Trend: <span className="text-slate-300">{stage?.ma200_trend}</span></div>
            <div>Price Trend: <span className="text-slate-300">{stage?.price_trend}</span></div>
            <div>Above MA200: <span className={stage?.above_ma200 ? "text-green-400" : "text-red-400"}>{stage?.above_ma200 ? "Yes" : "No"}</span></div>
            {stage?.description && <div className="text-[9px] pt-1 border-t border-border text-slate-600 leading-tight">{stage.description}</div>}
          </div>
        </div>

        {/* BB Squeeze */}
        <div className="bg-card border border-border rounded-xl p-4 space-y-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <BarChart2 size={14} className="text-yellow-400" />
              <span className="text-xs font-semibold text-slate-300">BB Squeeze</span>
            </div>
            <span className={`text-xs font-bold ${bb_squeeze?.detected ? "text-yellow-400" : "text-slate-500"}`}>
              {bb_squeeze?.detected ? "SQUEEZED" : "—"}
            </span>
          </div>
          <ScoreBar score={bb_squeeze?.score ?? 0} />
          <div className="text-[10px] text-slate-500 space-y-0.5">
            <div>Score: <span className="text-slate-300">{bb_squeeze?.score ?? 0}</span></div>
            <div>BB Width: <span className="text-slate-300">{bb_squeeze?.bb_width?.toFixed(2)}%</span></div>
            <div>50d Min: <span className="text-slate-300">{bb_squeeze?.bb_width_min_50d?.toFixed(2)}%</span></div>
            <div>Above Min: <span className="text-slate-300">{bb_squeeze?.pct_above_min?.toFixed(1)}%</span></div>
            <div>Price Band: <span className="text-slate-300">{((bb_squeeze?.price_band_position ?? 0.5) * 100).toFixed(0)}%</span></div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function PatternsPage() {
  const nav = useNavigate();
  const [search, setSearch] = useState("");
  const [activeSearch, setActiveSearch] = useState("");

  const { data: scanData, isLoading: scanLoading } = useQuery({
    queryKey: ["patterns-scan"],
    queryFn: () => api("/api/patterns/scan/top?limit=100"),
    staleTime: 120_000,
  });

  const handleSearch = (e) => {
    e.preventDefault();
    const t = search.trim().toUpperCase();
    if (t) setActiveSearch(t);
  };

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Pattern Scanner</h1>
        <p className="text-slate-500 text-sm">
          VCP · NR7 / Inside Day · Weinstein Stage · BB Squeeze — open-source algorithms, no external APIs
        </p>
      </div>

      {/* Single ticker search */}
      <form onSubmit={handleSearch} className="flex gap-2">
        <div className="relative">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value.toUpperCase())}
            placeholder="AAPL, RELIANCE.NS..."
            className="bg-card border border-border rounded-lg pl-8 pr-3 py-2 text-sm font-mono w-48 focus:outline-none focus:border-accent"
          />
        </div>
        <button type="submit" className="px-4 py-2 bg-accent/20 text-accent border border-accent/30 rounded-lg text-sm hover:bg-accent/30 transition-colors">
          Scan Ticker
        </button>
        {activeSearch && (
          <button type="button" onClick={() => setActiveSearch("")} className="px-3 py-2 text-slate-500 text-sm hover:text-slate-300">
            Clear
          </button>
        )}
      </form>

      {/* Single ticker result */}
      {activeSearch && <SingleTickerPanel ticker={activeSearch} />}

      {/* Scan results */}
      {!activeSearch && (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-slate-300">Top Pattern Matches — Active Universe</h2>
            {scanLoading && <Loader2 size={14} className="animate-spin text-slate-500" />}
            {scanData && <span className="text-xs text-slate-500">{scanData.count} tickers with patterns</span>}
          </div>

          <div className="bg-card border border-border rounded-xl overflow-hidden">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-border">
                  <th className="text-left px-4 py-2.5 text-slate-500 font-normal">Ticker</th>
                  <th className="text-left px-4 py-2.5 text-slate-500 font-normal">Patterns</th>
                  <th className="text-right px-4 py-2.5 text-slate-500 font-normal">Score</th>
                  <th className="text-center px-4 py-2.5 text-slate-500 font-normal">Stage</th>
                  <th className="text-right px-4 py-2.5 text-slate-500 font-normal">VCP</th>
                  <th className="text-right px-4 py-2.5 text-slate-500 font-normal">NR7</th>
                  <th className="px-4 py-2.5" />
                </tr>
              </thead>
              <tbody>
                {scanData?.results?.map((r) => (
                  <tr key={r.ticker}
                    className="border-b border-white/5 hover:bg-white/5 cursor-pointer transition-colors"
                    onClick={() => { setSearch(r.ticker); setActiveSearch(r.ticker); }}
                  >
                    <td className="px-4 py-2.5 font-mono font-bold text-white">{r.ticker}</td>
                    <td className="px-4 py-2.5">
                      <div className="flex flex-wrap gap-1">
                        {r.patterns?.map((p) => <PatternBadge key={p} pattern={p} />)}
                      </div>
                    </td>
                    <td className="px-4 py-2.5 text-right">
                      <div className="inline-flex flex-col items-end gap-0.5 min-w-[50px]">
                        <span className="font-mono font-bold text-white">{(r.pattern_score * 100).toFixed(0)}</span>
                        <ScoreBar score={r.pattern_score * 100} />
                      </div>
                    </td>
                    <td className="px-4 py-2.5 text-center">
                      <span className={`font-bold ${STAGE_COLORS[r.stage?.stage ?? 0]}`}>
                        {r.stage?.stage ?? "?"} {r.stage?.stage_name ? `· ${r.stage.stage_name}` : ""}
                      </span>
                    </td>
                    <td className="px-4 py-2.5 text-right font-mono">{r.vcp?.score ?? 0}</td>
                    <td className="px-4 py-2.5 text-right font-mono">{r.nr7?.score ?? 0}</td>
                    <td className="px-4 py-2.5">
                      <button
                        onClick={(e) => { e.stopPropagation(); nav(`/stocks/stock/${r.ticker}`); }}
                        className="p-1 rounded hover:bg-white/10 text-slate-500 hover:text-white"
                      >
                        <ChevronRight size={12} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!scanLoading && (!scanData?.results || scanData.results.length === 0) && (
              <div className="text-center py-12 text-slate-600">
                <Activity size={32} className="mx-auto mb-2 opacity-30" />
                <p>No patterns detected yet — signals need to run first</p>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
