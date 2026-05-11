import { useState, useRef } from "react";
import { useOutletContext } from "react-router-dom";
import MarketCommentary from "../components/MarketCommentary";

const SIG_COLOR = {
  LONG:    { fill: "#22c55e", bg: "rgba(34,197,94,",  label: "text-green-400"  },
  SHORT:   { fill: "#ef4444", bg: "rgba(239,68,68,",   label: "text-red-400"    },
  NEUTRAL: { fill: "#475569", bg: "rgba(71,85,105,",   label: "text-slate-400"  },
};
const CAT_COLORS = {
  Energy:      "#f97316", Metals: "#eab308", Agriculture: "#22c55e",
  Indices:     "#3b82f6", Bonds:  "#8b5cf6", FX:          "#06b6d4",
  Crypto:      "#a855f7",
};

function treemapLayout(items, x, y, w, h) {
  if (!items.length) return [];
  if (items.length === 1) return [{ ...items[0], x, y, w, h }];
  const total = items.reduce((s, i) => s + (i._val || 1), 0);
  let sum = 0, split = 0;
  for (let i = 0; i < items.length; i++) {
    sum += items[i]._val || 1;
    if (sum >= total / 2) { split = i + 1; break; }
  }
  const left = items.slice(0, split), right = items.slice(split);
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

function CategoryBlock({ category, items, color }) {
  const [hovered, setHovered] = useState(null);
  const [tooltip, setTooltip] = useState({ x: 0, y: 0 });
  const svgRef = useRef(null);

  const W = 700;
  const H = Math.max(100, Math.min(260, items.length * 32));

  const sorted = [...items].sort((a, b) => (b.confidence ?? 0) - (a.confidence ?? 0));
  const withVal = sorted.map((d) => ({ ...d, _val: Math.max(d.confidence ?? 0.01, 0.05) }));
  const laid = treemapLayout(withVal, GAP, GAP, W - GAP * 2, H - GAP * 2);

  return (
    <div className="bg-card border border-border rounded-xl overflow-hidden">
      <div className="px-3 py-2 border-b border-border flex items-center justify-between" style={{ borderLeftColor: color, borderLeftWidth: 3 }}>
        <span className="text-xs font-semibold" style={{ color }}>{category}</span>
        <div className="flex gap-3 text-[10px]">
          {["LONG","SHORT","NEUTRAL"].map((s) => {
            const n = items.filter((i) => i.signal === s).length;
            if (!n) return null;
            return <span key={s} className={SIG_COLOR[s]?.label}>{s} {n}</span>;
          })}
        </div>
      </div>
      <div className="relative" style={{ height: H }}>
        <svg
          ref={svgRef}
          width="100%" height={H}
          viewBox={`0 0 ${W} ${H}`}
          className="block"
          onMouseLeave={() => setHovered(null)}
        >
          {laid.map((node) => {
            const sig = SIG_COLOR[node.signal] ?? SIG_COLOR.NEUTRAL;
            const isH = hovered?.symbol === node.symbol;
            const showLabel = node.w > 35 && node.h > 16;
            const chg = node.change_pct ?? 0;
            return (
              <g key={node.symbol}
                style={{ cursor: "default" }}
                onMouseEnter={(e) => {
                  setHovered(node);
                  const rect = svgRef.current?.getBoundingClientRect();
                  setTooltip({ x: e.clientX - (rect?.left ?? 0), y: e.clientY - (rect?.top ?? 0) });
                }}
              >
                <rect
                  x={node.x} y={node.y} width={node.w} height={node.h}
                  rx={3}
                  fill={`${sig.bg}${isH ? 0.55 : 0.22})`}
                  stroke={sig.fill}
                  strokeWidth={isH ? 1.5 : 0.5}
                />
                {/* Confidence fill bar */}
                <rect
                  x={node.x} y={node.y + node.h - 2}
                  width={node.w * (node.confidence ?? 0)} height={2}
                  fill={sig.fill} opacity={0.7} rx={1}
                />
                {showLabel && (
                  <>
                    <text x={node.x + node.w / 2} y={node.y + node.h / 2 - 3}
                      textAnchor="middle" dominantBaseline="middle"
                      fontSize={Math.min(11, Math.max(7, node.w / 5))}
                      fontWeight="700" fill={sig.fill}>
                      {(node.name || node.symbol).split(" ")[0].slice(0, 8)}
                    </text>
                    {node.h > 28 && (
                      <text x={node.x + node.w / 2} y={node.y + node.h / 2 + 9}
                        textAnchor="middle" dominantBaseline="middle"
                        fontSize={Math.min(9, Math.max(6, node.w / 8))}
                        fill={chg >= 0 ? "#22c55e" : "#ef4444"}>
                        {chg >= 0 ? "+" : ""}{chg.toFixed(2)}%
                      </text>
                    )}
                  </>
                )}
              </g>
            );
          })}
        </svg>

        {hovered && (
          <div
            className="pointer-events-none absolute z-20 bg-[#0f1117]/95 border border-border rounded-lg px-3 py-2 text-xs shadow-xl"
            style={{ left: Math.min(tooltip.x + 12, W - 200), top: Math.max(0, tooltip.y - 50) }}
          >
            <p className="font-bold text-slate-200">{hovered.name} <span className="text-slate-500 font-mono font-normal">{hovered.symbol}</span></p>
            <div className="flex gap-3 mt-1">
              <span className={SIG_COLOR[hovered.signal]?.label ?? "text-slate-400"}>{hovered.signal}</span>
              <span className="text-slate-400">{Math.round((hovered.confidence ?? 0) * 100)}% conf</span>
              <span className={(hovered.change_pct ?? 0) >= 0 ? "text-green-400" : "text-red-400"}>
                {(hovered.change_pct ?? 0) >= 0 ? "+" : ""}{(hovered.change_pct ?? 0).toFixed(2)}%
              </span>
            </div>
            {hovered.signal_reason && (
              <p className="text-[10px] text-slate-600 mt-1 max-w-[200px]">{hovered.signal_reason}</p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default function FuturesHeatmap() {
  const { quotes } = useOutletContext();
  const [filter, setFilter] = useState("ALL");

  const filtered = filter === "ALL" ? quotes : quotes.filter((q) => q.signal === filter);

  const bySector = {};
  for (const q of filtered) {
    const cat = q.category || "Other";
    (bySector[cat] = bySector[cat] || []).push(q);
  }
  const categories = Object.entries(bySector).sort((a, b) => b[1].length - a[1].length);

  const longs  = quotes.filter((q) => q.signal === "LONG").length;
  const shorts = quotes.filter((q) => q.signal === "SHORT").length;
  const neutral = quotes.length - longs - shorts;

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold">Futures Heatmap</h1>
          <p className="text-slate-500 text-sm">
            {quotes.length} instruments · grouped by category · sized by confidence · colored by signal
          </p>
        </div>
      </div>

      {/* Commentary */}
      <MarketCommentary mode="futures" />

      {/* Filter bar */}
      <div className="flex items-center gap-3 flex-wrap">
        {[["ALL", "All", null], ["LONG", "LONG", longs], ["SHORT", "SHORT", shorts], ["NEUTRAL", "NEUTRAL", neutral]].map(([val, label, count]) => (
          <button
            key={val}
            onClick={() => setFilter(val)}
            className={`px-3 py-1 rounded-lg text-xs transition-colors border ${
              filter === val
                ? val === "LONG"    ? "bg-green-500/20 text-green-400 border-green-500/30"
                : val === "SHORT"   ? "bg-red-500/20 text-red-400 border-red-500/30"
                : val === "NEUTRAL" ? "bg-slate-500/20 text-slate-400 border-slate-500/30"
                : "bg-orange-500/20 text-orange-400 border-orange-500/30"
                : "text-slate-500 border-transparent hover:text-slate-300"
            }`}
          >
            {label} {count !== null && `(${count})`}
          </button>
        ))}
        <div className="ml-auto flex gap-3 text-[10px] text-slate-500">
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-green-500 inline-block"/>LONG</span>
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-red-500 inline-block"/>SHORT</span>
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-slate-500 inline-block"/>NEUTRAL</span>
          <span className="text-slate-600">Bar = confidence</span>
        </div>
      </div>

      {quotes.length === 0 ? (
        <div className="text-center py-20 text-slate-600">Loading market data…</div>
      ) : categories.length === 0 ? (
        <div className="text-center py-20 text-slate-600">No instruments match filter.</div>
      ) : (
        <div className="space-y-3">
          {categories.map(([cat, items]) => (
            <CategoryBlock key={cat} category={cat} items={items} color={CAT_COLORS[cat] ?? "#94a3b8"} />
          ))}
        </div>
      )}
    </div>
  );
}
