import { useState, useRef, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import axios from "axios";
import { useNavigate } from "react-router-dom";
import MarketCommentary from "../components/MarketCommentary";

const SIG_COLOR = {
  BUY:  { fill: "#22c55e", bg: "rgba(34,197,94,",  label: "text-green-400" },
  SELL: { fill: "#ef4444", bg: "rgba(239,68,68,",   label: "text-red-400"   },
  HOLD: { fill: "#475569", bg: "rgba(71,85,105,",   label: "text-slate-400" },
};

// Binary-split treemap layout
function treemapLayout(items, x, y, w, h) {
  if (!items.length) return [];
  if (items.length === 1) return [{ ...items[0], x, y, w, h }];
  const total  = items.reduce((s, i) => s + (i._val || 1), 0);
  let sum = 0, split = 0;
  for (let i = 0; i < items.length; i++) {
    sum += items[i]._val || 1;
    if (sum >= total / 2) { split = i + 1; break; }
  }
  const left = items.slice(0, split);
  const right = items.slice(split);
  const ratio = left.reduce((s, i) => s + (i._val || 1), 0) / total;
  if (w >= h) {
    const wL = w * ratio;
    return [...treemapLayout(left, x, y, wL, h), ...treemapLayout(right, x + wL, y, w - wL, h)];
  } else {
    const hL = h * ratio;
    return [...treemapLayout(left, x, y, w, hL), ...treemapLayout(right, x, y + hL, w, h - hL)];
  }
}

const GAP = 2;

function SectorBlock({ sector, items, navigate }) {
  const [hovered, setHovered] = useState(null);
  const [tooltip, setTooltip] = useState({ x: 0, y: 0 });
  const svgRef = useRef(null);

  const W = 700, H = Math.max(120, Math.min(300, items.length * 18));

  const sorted = [...items].sort((a, b) => (b.market_cap || b.confidence || 1) - (a.market_cap || a.confidence || 1));
  const withVal = sorted.map((d) => ({ ...d, _val: Math.max(d.market_cap || 0, 1e8) }));
  const laid = treemapLayout(withVal, GAP, GAP, W - GAP * 2, H - GAP * 2);

  return (
    <div className="bg-card border border-border rounded-xl overflow-hidden">
      <div className="px-3 py-2 border-b border-border flex items-center justify-between">
        <span className="text-xs font-semibold text-slate-300">{sector}</span>
        <div className="flex gap-2 text-[10px]">
          {["BUY","SELL","HOLD"].map((s) => {
            const n = items.filter((i) => i.signal === s).length;
            if (!n) return null;
            return <span key={s} className={SIG_COLOR[s]?.label}>{s} {n}</span>;
          })}
        </div>
      </div>
      <div className="relative" style={{ height: H }}>
        <svg
          ref={svgRef}
          width="100%"
          height={H}
          viewBox={`0 0 ${W} ${H}`}
          className="block"
          onMouseLeave={() => setHovered(null)}
        >
          {laid.map((node) => {
            const sig  = SIG_COLOR[node.signal] ?? SIG_COLOR.HOLD;
            const conf = node.confidence ?? 0;
            const isH  = hovered?.ticker === node.ticker;
            const chg  = node.change_pct ?? 0;
            const showLabel = node.w > 40 && node.h > 18;
            return (
              <g key={node.ticker}
                style={{ cursor: "pointer" }}
                onMouseEnter={(e) => {
                  setHovered(node);
                  const rect = svgRef.current?.getBoundingClientRect();
                  setTooltip({ x: e.clientX - (rect?.left ?? 0), y: e.clientY - (rect?.top ?? 0) });
                }}
                onClick={() => navigate(`/stocks/stock/${node.ticker}`)}
              >
                <rect
                  x={node.x} y={node.y} width={node.w} height={node.h}
                  rx={3}
                  fill={`${sig.bg}${isH ? 0.55 : 0.25})`}
                  stroke={sig.fill}
                  strokeWidth={isH ? 1.5 : 0.5}
                />
                {/* Confidence bar at bottom */}
                <rect
                  x={node.x} y={node.y + node.h - 2}
                  width={node.w * conf} height={2}
                  fill={sig.fill} opacity={0.6} rx={1}
                />
                {showLabel && (
                  <>
                    <text x={node.x + node.w / 2} y={node.y + node.h / 2 - 3}
                      textAnchor="middle" dominantBaseline="middle"
                      fontSize={Math.min(11, Math.max(7, node.w / 6))}
                      fontWeight="700" fill={sig.fill}>
                      {node.ticker.split(".")[0].slice(0, 6)}
                    </text>
                    {node.h > 30 && (
                      <text x={node.x + node.w / 2} y={node.y + node.h / 2 + 9}
                        textAnchor="middle" dominantBaseline="middle"
                        fontSize={Math.min(9, Math.max(6, node.w / 8))}
                        fill={chg >= 0 ? "#22c55e" : "#ef4444"}>
                        {chg >= 0 ? "+" : ""}{chg.toFixed(1)}%
                      </text>
                    )}
                  </>
                )}
              </g>
            );
          })}
        </svg>

        {/* Hover tooltip */}
        {hovered && (
          <div
            className="pointer-events-none absolute z-20 bg-[#0f1117]/95 border border-border rounded-lg px-3 py-2 text-xs shadow-xl"
            style={{ left: Math.min(tooltip.x + 12, W - 160), top: Math.max(0, tooltip.y - 40) }}
          >
            <p className="font-bold text-slate-200">{hovered.ticker} <span className="text-slate-500 font-normal">{hovered.name?.slice(0, 24)}</span></p>
            <div className="flex gap-3 mt-1">
              <span className={SIG_COLOR[hovered.signal]?.label ?? "text-slate-400"}>{hovered.signal}</span>
              <span className="text-slate-400">{Math.round((hovered.confidence ?? 0) * 100)}% conf</span>
              <span className={(hovered.change_pct ?? 0) >= 0 ? "text-green-400" : "text-red-400"}>
                {(hovered.change_pct ?? 0) >= 0 ? "+" : ""}{(hovered.change_pct ?? 0).toFixed(2)}%
              </span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default function HeatmapPage() {
  const navigate = useNavigate();
  const [filter, setFilter] = useState("ALL");

  const { data: raw = [], isLoading, refetch } = useQuery({
    queryKey: ["heatmap"],
    queryFn:  () => axios.get("/api/market/heatmap?limit=400").then((r) => r.data),
    refetchInterval: 300_000,
  });

  const filtered = filter === "ALL" ? raw : raw.filter((d) => d.signal === filter);

  // Group by sector
  const bySector = {};
  for (const d of filtered) {
    const s = d.sector || "Other";
    (bySector[s] = bySector[s] || []).push(d);
  }
  const sectors = Object.entries(bySector).sort((a, b) => b[1].length - a[1].length);

  const buys  = raw.filter((d) => d.signal === "BUY").length;
  const sells = raw.filter((d) => d.signal === "SELL").length;

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold">Market Heatmap</h1>
          <p className="text-slate-500 text-sm">{raw.length} stocks · grouped by sector · sized by market cap · colored by signal</p>
        </div>
        <button onClick={() => refetch()} className="text-xs text-slate-500 hover:text-slate-300 border border-border px-3 py-1.5 rounded-lg transition-colors mt-1">
          Refresh
        </button>
      </div>

      {/* Commentary */}
      <MarketCommentary mode="stocks" />

      {/* Summary bar */}
      <div className="flex items-center gap-4 text-sm">
        {[["ALL", "All"], ["BUY", "BUY"], ["SELL", "SELL"], ["HOLD", "HOLD"]].map(([val, label]) => (
          <button
            key={val}
            onClick={() => setFilter(val)}
            className={`px-3 py-1 rounded-lg text-xs transition-colors border ${
              filter === val
                ? val === "BUY"  ? "bg-green-500/20 text-green-400 border-green-500/30"
                : val === "SELL" ? "bg-red-500/20 text-red-400 border-red-500/30"
                : "bg-accent/20 text-accent border-accent/30"
                : "text-slate-500 border-transparent hover:text-slate-300"
            }`}
          >
            {label} {val !== "ALL" && `(${val === "BUY" ? buys : val === "SELL" ? sells : raw.length - buys - sells})`}
          </button>
        ))}
        <div className="ml-auto flex gap-3 text-[10px] text-slate-500">
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-green-500 inline-block"/>BUY</span>
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-red-500 inline-block"/>SELL</span>
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-slate-500 inline-block"/>HOLD</span>
          <span className="text-slate-600">Bar = confidence</span>
        </div>
      </div>

      {isLoading ? (
        <div className="text-center py-20 text-slate-600">Building heatmap…</div>
      ) : sectors.length === 0 ? (
        <div className="text-center py-20 text-slate-600">No signal data — run signal generation first.</div>
      ) : (
        <div className="space-y-3">
          {sectors.map(([sector, items]) => (
            <SectorBlock key={sector} sector={sector} items={items} navigate={navigate} />
          ))}
        </div>
      )}
    </div>
  );
}
