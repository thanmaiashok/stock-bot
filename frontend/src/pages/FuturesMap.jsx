import { useState, useEffect, useCallback, useRef } from "react";
import { useOutletContext } from "react-router-dom";
import axios from "axios";
import ForceGraph2D from "react-force-graph-2d";
import { fmt, pct, CATEGORY_COLORS } from "./FuturesShell";
import { RefreshCw } from "lucide-react";

// ── colour constants ──────────────────────────────────────────────────────────
const SIG_COLOR = { LONG: "#22c55e", SHORT: "#ef4444", NEUTRAL: "#475569" };
const CAT_COLOR = {
  Energy:      "#f97316",
  Metals:      "#eab308",
  Agriculture: "#22c55e",
  Indices:     "#3b82f6",
  Bonds:       "#8b5cf6",
  FX:          "#06b6d4",
  Crypto:      "#a855f7",
};
const NEWS_COLOR = "#f59e0b";
const LINK_COLOR = {
  CORRELATES_WITH: "#1e293b",
  BELONGS_TO:      "#334155",
  MENTIONS:        "#92400e",
};

// Correlation threshold for drawing an edge
const CORR_THRESH = 0.65;

function instrumentColor(node) {
  return SIG_COLOR[node.signal] ?? SIG_COLOR.NEUTRAL;
}

// Ego-network for a single instrument: center + correlated peers + category + news
function buildEgoGraph(sym, quotes, corrData, newsImpact) {
  const nodes = [];
  const links = [];
  const nodeIds = new Set();

  const quoteMap = Object.fromEntries(quotes.map((q) => [q.symbol, q]));
  const center = quoteMap[sym];
  if (!center) return { nodes: [], links: [] };

  // Correlated peers
  const peerSyms = new Set([sym]);
  if (corrData?.symbols && corrData?.matrix) {
    const idx = corrData.symbols.indexOf(sym);
    if (idx >= 0) {
      corrData.symbols.forEach((s, j) => {
        const corr = corrData.matrix[idx]?.[j];
        if (corr != null && Math.abs(corr) >= CORR_THRESH && s !== sym) peerSyms.add(s);
      });
    }
  }

  // Add instrument nodes
  for (const s of peerSyms) {
    const q = quoteMap[s];
    if (!q) continue;
    nodes.push({
      id: s, type: "instrument",
      label:      q.name.split(" ")[0].slice(0, 7),
      name:       q.name, category: q.category,
      signal:     q.signal, confidence: q.confidence ?? 0,
      price:      q.price, change_pct: q.change_pct,
      unit:       q.unit, signal_reason: q.signal_reason,
      isCenter:   s === sym,
    });
    nodeIds.add(s);
  }

  // Correlation edges between included nodes
  if (corrData?.symbols && corrData?.matrix) {
    const syms = corrData.symbols;
    for (let i = 0; i < syms.length; i++) {
      if (!nodeIds.has(syms[i])) continue;
      for (let j = i + 1; j < syms.length; j++) {
        if (!nodeIds.has(syms[j])) continue;
        const corr = corrData.matrix[i]?.[j];
        if (corr != null && Math.abs(corr) >= CORR_THRESH) {
          links.push({ source: syms[i], target: syms[j], type: "CORRELATES_WITH", weight: Math.abs(corr), sign: corr >= 0 ? "positive" : "negative" });
        }
      }
    }
  }

  // Category node for center only
  const catId = `cat:${center.category}`;
  nodes.push({ id: catId, type: "category", label: center.category, category: center.category });
  nodeIds.add(catId);
  links.push({ source: sym, target: catId, type: "BELONGS_TO" });

  // News nodes for all included instruments
  if (newsImpact?.futures) {
    for (const item of newsImpact.futures) {
      if (!nodeIds.has(item.symbol)) continue;
      for (const hl of (item.headlines || []).slice(0, 3)) {
        const newsId = `news:${item.symbol}:${hl.headline.slice(0, 30)}`;
        if (nodeIds.has(newsId)) continue;
        nodes.push({ id: newsId, type: "news", label: hl.headline, sentiment: hl.sentiment ?? 0, url: hl.url, symbol: item.symbol });
        nodeIds.add(newsId);
        links.push({ source: newsId, target: item.symbol, type: "MENTIONS" });
      }
    }
  }

  return { nodes, links };
}

// Build full market graph from quotes + correlations + news
function buildGraph(quotes, corrData, newsImpact) {
  const nodes = [];
  const links = [];
  const nodeIds = new Set();

  // ── Instrument nodes ──────────────────────────────────────────────────────
  const quoteMap = {};
  for (const q of quotes) {
    quoteMap[q.symbol] = q;
    nodes.push({
      id:         q.symbol,
      type:       "instrument",
      label:      q.name.split(" ")[0].slice(0, 7),
      name:       q.name,
      category:   q.category,
      signal:     q.signal,
      confidence: q.confidence ?? 0,
      price:      q.price,
      change_pct: q.change_pct,
      unit:       q.unit,
      signal_reason: q.signal_reason,
    });
    nodeIds.add(q.symbol);
  }

  // ── Category nodes ────────────────────────────────────────────────────────
  const cats = [...new Set(quotes.map((q) => q.category))];
  for (const cat of cats) {
    const catId = `cat:${cat}`;
    nodes.push({ id: catId, type: "category", label: cat, category: cat });
    nodeIds.add(catId);
    // BELONGS_TO edges
    for (const q of quotes.filter((q2) => q2.category === cat)) {
      links.push({ source: q.symbol, target: catId, type: "BELONGS_TO" });
    }
  }

  // ── Correlation edges ─────────────────────────────────────────────────────
  if (corrData?.symbols && corrData?.matrix) {
    const syms = corrData.symbols;
    for (let i = 0; i < syms.length; i++) {
      for (let j = i + 1; j < syms.length; j++) {
        const corr = corrData.matrix[i]?.[j];
        if (corr != null && Math.abs(corr) >= CORR_THRESH) {
          links.push({
            source: syms[i],
            target: syms[j],
            type:   "CORRELATES_WITH",
            weight: Math.abs(corr),
            sign:   corr >= 0 ? "positive" : "negative",
          });
        }
      }
    }
  }

  // ── News nodes + MENTIONS edges ───────────────────────────────────────────
  if (newsImpact?.futures) {
    for (const item of newsImpact.futures.slice(0, 12)) {
      if (!nodeIds.has(item.symbol)) continue;
      // Show top 2 headlines as news nodes
      for (const hl of (item.headlines || []).slice(0, 2)) {
        const newsId = `news:${item.symbol}:${hl.headline.slice(0, 30)}`;
        if (nodeIds.has(newsId)) continue;
        nodes.push({
          id:        newsId,
          type:      "news",
          label:     hl.headline,
          sentiment: hl.sentiment ?? 0,
          url:       hl.url,
          symbol:    item.symbol,
        });
        nodeIds.add(newsId);
        links.push({ source: newsId, target: item.symbol, type: "MENTIONS" });
      }
    }
  }

  return { nodes, links };
}

export default function FuturesMap() {
  const { quotes } = useOutletContext();

  const [corrData,    setCorrData]    = useState(null);
  const [newsImpact,  setNewsImpact]  = useState(null);
  const [graphData,   setGraphData]   = useState({ nodes: [], links: [] });
  const [selected,    setSelected]    = useState(null);
  const [search,      setSearch]      = useState("");
  const [focusSym,    setFocusSym]    = useState(null);
  const [mode,        setMode]        = useState("market"); // "market" | "instrument"
  const [dimensions,  setDimensions]  = useState({ w: 900, h: 580 });
  const [corrLoading, setCorrLoading] = useState(true);

  const [showDrop,    setShowDrop]    = useState(false);

  const containerRef = useRef(null);
  const fgRef        = useRef(null);

  // Resize observer
  useEffect(() => {
    if (!containerRef.current) return;
    const ro = new ResizeObserver(([e]) => {
      setDimensions({ w: e.contentRect.width, h: 560 });
    });
    ro.observe(containerRef.current);
    return () => ro.disconnect();
  }, []);

  const fetchCorrNews = useCallback(() => {
    setCorrLoading(true);
    Promise.all([
      axios.get("/api/futures/correlations").then((r) => r.data).catch(() => null),
      axios.get("/api/news/impact?hours=48").then((r) => r.data).catch(() => null),
    ]).then(([corr, news]) => {
      setCorrData(corr);
      setNewsImpact(news);
      setCorrLoading(false);
    });
  }, []);

  // Fetch correlations + news once on mount
  useEffect(() => { fetchCorrNews(); }, [fetchCorrNews]);

  // Rebuild graph whenever inputs change
  useEffect(() => {
    if (!quotes.length) return;
    if (mode === "instrument" && focusSym) {
      setGraphData(buildEgoGraph(focusSym, quotes, corrData, newsImpact));
    } else {
      setGraphData(buildGraph(quotes, corrData, newsImpact));
    }
  }, [quotes, corrData, newsImpact, mode, focusSym]);

  // Tune physics after graph loads
  useEffect(() => {
    if (!fgRef.current || !graphData.nodes.length) return;
    const charge = mode === "instrument" ? -350 : -220;
    const linkDist = mode === "instrument"
      ? (l) => l.type === "BELONGS_TO" ? 120 : l.type === "MENTIONS" ? 80 : 90
      : (l) => l.type === "BELONGS_TO" ? 80 : l.type === "MENTIONS" ? 60 : 50;
    fgRef.current.d3Force("charge").strength(charge);
    fgRef.current.d3Force("link").distance(linkDist);
    fgRef.current.d3ReheatSimulation();
    // Fit to view after switching modes
    setTimeout(() => fgRef.current?.zoomToFit(400, 60), 800);
  }, [graphData, mode]);

  const handleSearch = () => {
    const sym = search.trim().toUpperCase();
    if (!sym) {
      setMode("market");
      setFocusSym(null);
      setSelected(null);
      return;
    }
    // Check symbol exists in quotes
    const q = quotes.find((q) => q.symbol === sym);
    if (!q) return; // unknown symbol — do nothing
    setFocusSym(sym);
    setMode("instrument");
    setSelected(null);
  };

  const resetToMarket = () => {
    setMode("market");
    setFocusSym(null);
    setSelected(null);
    setSearch("");
  };

  const handleNodeClick = useCallback((node) => {
    setSelected((prev) => (prev?.id === node.id ? null : node));
    if (node.x != null && fgRef.current) {
      fgRef.current.centerAt(node.x, node.y, 400);
    }
  }, []);

  const paintNode = useCallback((node, ctx, gs) => {
    const { x, y } = node;
    const isSel = selected?.id === node.id;

    if (node.type === "category") {
      const s = isSel ? 9 : 6;
      ctx.beginPath();
      ctx.moveTo(x, y - s); ctx.lineTo(x + s, y);
      ctx.lineTo(x, y + s); ctx.lineTo(x - s, y);
      ctx.closePath();
      ctx.fillStyle = CAT_COLOR[node.category] ?? "#0ea5e9";
      ctx.globalAlpha = 0.85;
      ctx.fill();
      ctx.globalAlpha = 1;
      const fs = Math.max(5, 9 / gs);
      ctx.font = `${fs}px Sans-Serif`;
      ctx.fillStyle = CAT_COLOR[node.category] ?? "#7dd3fc";
      ctx.textAlign = "center";
      ctx.textBaseline = "top";
      ctx.fillText(node.label, x, y + s + 2);

    } else if (node.type === "news") {
      const r = isSel ? 5 : 3;
      const sent = node.sentiment ?? 0;
      ctx.beginPath();
      ctx.arc(x, y, r, 0, 2 * Math.PI);
      ctx.fillStyle = sent > 0.05 ? "#22c55e" : sent < -0.05 ? "#ef4444" : NEWS_COLOR;
      ctx.globalAlpha = 0.8;
      ctx.fill();
      ctx.globalAlpha = 1;

    } else {
      // Instrument
      const isCenter = node.isCenter === true;
      const r = isCenter ? 13 : isSel ? 11 : Math.max(6, 6 + (node.confidence ?? 0) * 5);
      const color = instrumentColor(node);
      ctx.beginPath();
      ctx.arc(x, y, r, 0, 2 * Math.PI);
      ctx.fillStyle = color;
      ctx.globalAlpha = isCenter ? 0.45 : isSel ? 0.5 : 0.25;
      ctx.fill();
      ctx.globalAlpha = 1;
      ctx.strokeStyle = color;
      ctx.lineWidth = isCenter ? 3 : isSel ? 2.5 : 1.5;
      ctx.stroke();
      if (isCenter) {
        // White halo ring for center node
        ctx.beginPath();
        ctx.arc(x, y, r + 3, 0, 2 * Math.PI);
        ctx.strokeStyle = "#ffffff30";
        ctx.lineWidth = 2;
        ctx.stroke();
      }

      // Label
      const fs = Math.max(6, (isCenter || isSel ? 12 : 9) / gs);
      ctx.font = `${isCenter || isSel ? "bold " : ""}${fs}px Sans-Serif`;
      ctx.fillStyle = "#f1f5f9";
      ctx.textAlign = "center";
      ctx.textBaseline = "top";
      ctx.fillText(node.label, x, y + r + 1);
    }
  }, [selected]);

  const instrNodes = graphData.nodes.filter((n) => n.type === "instrument");
  const newsNodes  = graphData.nodes.filter((n) => n.type === "news");
  const corrEdges  = graphData.links.filter((l) => l.type === "CORRELATES_WITH");

  return (
    <div className="p-6 space-y-4">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h2 className="font-bold text-lg">
            {mode === "instrument" && focusSym
              ? `${quotes.find((q) => q.symbol === focusSym)?.name ?? focusSym} · Network`
              : "Futures Intelligence Map"}
          </h2>
          <p className="text-xs text-slate-500">
            {mode === "instrument"
              ? `Ego-network · correlated peers, category, news`
              : `${instrNodes.length} instruments · ${corrEdges.length} correlations · ${newsNodes.length} live news nodes`}
            {corrLoading && " · loading correlations…"}
          </p>
        </div>
        {mode === "instrument" && (
          <button
            onClick={resetToMarket}
            className="text-xs text-slate-400 hover:text-white border border-border px-3 py-1.5 rounded-lg transition-colors mt-1"
          >
            ← All Markets
          </button>
        )}
      </div>

      {/* Search + Legend */}
      <div className="flex gap-3 items-center flex-wrap">
        {/* Autocomplete search */}
        <div className="relative">
          <input
            className="bg-card border border-border rounded-lg px-4 py-2 text-sm outline-none focus:border-orange-500 w-48"
            value={search}
            onChange={(e) => { setSearch(e.target.value.toUpperCase()); setShowDrop(true); }}
            onFocus={() => setShowDrop(true)}
            onBlur={() => setTimeout(() => setShowDrop(false), 150)}
            onKeyDown={(e) => { if (e.key === "Enter") { handleSearch(); setShowDrop(false); } if (e.key === "Escape") setShowDrop(false); }}
            placeholder="Search symbol…"
          />
          {showDrop && (() => {
            const filtered = search
              ? quotes.filter((q) => q.symbol.includes(search) || q.name.toUpperCase().includes(search))
              : [...quotes].sort((a, b) => (b.confidence ?? 0) - (a.confidence ?? 0)).slice(0, 8);
            if (!filtered.length) return null;
            return (
              <div className="absolute top-full left-0 mt-1 w-64 bg-card border border-border rounded-lg shadow-xl z-50 max-h-56 overflow-y-auto">
                {!search && <div className="px-3 py-1.5 text-[10px] text-slate-600 uppercase tracking-wider border-b border-border">Top by confidence</div>}
                {filtered.map((q) => (
                  <button
                    key={q.symbol}
                    onMouseDown={() => {
                      setSearch(q.symbol);
                      setFocusSym(q.symbol);
                      setMode("instrument");
                      setSelected(null);
                      setShowDrop(false);
                    }}
                    className="w-full flex items-center justify-between px-3 py-2 text-xs hover:bg-surface transition-colors text-left"
                  >
                    <span className="flex items-center gap-2">
                      <span
                        className="w-1.5 h-1.5 rounded-full shrink-0"
                        style={{ background: q.signal === "LONG" ? "#22c55e" : q.signal === "SHORT" ? "#ef4444" : "#475569" }}
                      />
                      <span className="font-mono font-bold">{q.symbol}</span>
                      <span className="text-slate-500 truncate max-w-[100px]">{q.name}</span>
                    </span>
                    <span
                      className="text-[10px] font-bold shrink-0"
                      style={{ color: q.signal === "LONG" ? "#22c55e" : q.signal === "SHORT" ? "#ef4444" : "#475569" }}
                    >
                      {q.signal}
                    </span>
                  </button>
                ))}
              </div>
            );
          })()}
        </div>
        <button
          onClick={handleSearch}
          className="bg-orange-500 text-white px-4 py-2 rounded-lg text-sm hover:bg-orange-600 transition-colors"
        >
          Focus
        </button>
        {mode === "instrument" && (
          <button
            onClick={resetToMarket}
            className="text-xs text-slate-400 hover:text-white border border-border px-3 py-1.5 rounded-lg transition-colors"
          >
            ← All
          </button>
        )}
        <button
          onClick={fetchCorrNews}
          disabled={corrLoading}
          className="flex items-center gap-1.5 text-sm border border-border text-slate-400 hover:text-white hover:border-slate-500 px-3 py-2 rounded-lg transition-colors disabled:opacity-40"
          title="Refresh correlations + news"
        >
          <RefreshCw size={13} className={corrLoading ? "animate-spin" : ""} />
          Refresh
        </button>
        <div className="flex gap-3 ml-auto text-xs text-slate-400 flex-wrap">
          {[
            ["#22c55e", "LONG"],
            ["#ef4444", "SHORT"],
            ["#475569", "NEUTRAL"],
            ["#f97316", "Category"],
            ["#f59e0b", "News"],
          ].map(([c, l]) => (
            <span key={l} className="flex items-center gap-1">
              <span className="w-2.5 h-2.5 rounded-full inline-block" style={{ background: c }} />
              {l}
            </span>
          ))}
        </div>
      </div>

      {/* Graph */}
      <div ref={containerRef} className="relative bg-card border border-border rounded-xl overflow-hidden">
        {graphData.nodes.length === 0 ? (
          <div className="h-64 flex items-center justify-center text-slate-600 text-sm">
            Building graph…
          </div>
        ) : (
          <ForceGraph2D
            ref={fgRef}
            graphData={graphData}
            width={dimensions.w}
            height={dimensions.h}
            backgroundColor="#0f1117"
            nodeLabel={(n) => {
              if (n.type === "news")     return n.label;
              if (n.type === "category") return `Category: ${n.label}`;
              return `${n.id} · ${n.name} · ${n.signal} ${Math.round((n.confidence ?? 0) * 100)}% conf`;
            }}
            nodeCanvasObject={paintNode}
            nodeCanvasObjectMode={() => "replace"}
            linkColor={(l) => {
              if (l.type === "CORRELATES_WITH") {
                return l.sign === "negative" ? "#ef444430" : "#22c55e30";
              }
              return LINK_COLOR[l.type] ?? "#1e293b";
            }}
            linkWidth={(l) => {
              if (l.type === "CORRELATES_WITH") return Math.max(0.5, (l.weight ?? 0.5) * 2);
              if (l.type === "MENTIONS") return 1;
              return 0.5;
            }}
            linkDirectionalArrowLength={(l) => l.type === "BELONGS_TO" ? 3 : 0}
            linkDirectionalArrowRelPos={1}
            onNodeClick={handleNodeClick}
            onBackgroundClick={() => setSelected(null)}
            cooldownTicks={150}
            d3AlphaDecay={0.015}
            d3VelocityDecay={0.3}
          />
        )}

        {/* Info card */}
        {selected && (
          <div className="absolute top-3 right-3 w-60 bg-[#0f1117]/95 border border-border rounded-xl p-4 shadow-xl backdrop-blur-sm z-10">
            <button
              onClick={() => setSelected(null)}
              className="absolute top-2 right-3 text-slate-500 hover:text-white text-lg leading-none"
            >×</button>

            {selected.type === "instrument" ? (
              <>
                <p className="text-xs text-slate-500 mb-0.5 font-mono">{selected.id}</p>
                <p className="text-sm font-bold mb-1 leading-tight">{selected.name}</p>
                <div className="flex items-center gap-2 mb-3">
                  <span
                    className="text-xs font-bold px-2 py-0.5 rounded-full border"
                    style={{
                      color: SIG_COLOR[selected.signal],
                      borderColor: SIG_COLOR[selected.signal],
                    }}
                  >
                    {selected.signal}
                  </span>
                  <span className="text-xs text-slate-400">
                    {Math.round((selected.confidence ?? 0) * 100)}% conf
                  </span>
                </div>
                <div className="space-y-1 text-xs text-slate-400">
                  <div className="flex justify-between">
                    <span>Price</span>
                    <span className="font-mono text-slate-200">{fmt(selected.price)} {selected.unit}</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Change</span>
                    <span className={`font-mono font-bold ${(selected.change_pct ?? 0) >= 0 ? "text-green-400" : "text-red-400"}`}>
                      {pct(selected.change_pct)}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span>Category</span>
                    <span style={{ color: CAT_COLOR[selected.category] ?? "#94a3b8" }}>{selected.category}</span>
                  </div>
                </div>
                {selected.signal_reason && (
                  <p className="text-[10px] text-slate-600 mt-2 leading-tight">{selected.signal_reason}</p>
                )}
              </>
            ) : selected.type === "news" ? (
              <>
                <p className="text-xs text-amber-400 font-medium mb-1">News · {selected.symbol}</p>
                <p className="text-xs text-slate-300 leading-relaxed">{selected.label}</p>
                <div className="flex items-center gap-2 mt-2">
                  <span className={`text-[10px] font-mono ${(selected.sentiment ?? 0) > 0 ? "text-green-400" : (selected.sentiment ?? 0) < 0 ? "text-red-400" : "text-slate-500"}`}>
                    sentiment {(selected.sentiment ?? 0) > 0 ? "+" : ""}{(selected.sentiment ?? 0).toFixed(2)}
                  </span>
                </div>
              </>
            ) : (
              <>
                <p className="text-sm font-bold mb-1" style={{ color: CAT_COLOR[selected.category] ?? "#94a3b8" }}>
                  {selected.label}
                </p>
                <p className="text-xs text-slate-500">
                  {instrNodes.filter((n) => n.category === selected.category).length} instruments
                </p>
              </>
            )}
          </div>
        )}
      </div>

      {/* Category heatmap */}
      <div className="bg-card border border-border rounded-xl p-4">
        <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-3">Category Signals</p>
        <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-7 gap-2">
          {Object.entries(CAT_COLOR).map(([cat, color]) => {
            const catQ = quotes.filter((q) => q.category === cat);
            if (!catQ.length) return null;
            const longs  = catQ.filter((q) => q.signal === "LONG").length;
            const shorts = catQ.filter((q) => q.signal === "SHORT").length;
            const avgChg = catQ.reduce((a, q) => a + (q.change_pct ?? 0), 0) / catQ.length;
            return (
              <div key={cat} className="rounded-lg border p-2.5" style={{ borderColor: `${color}30`, background: `${color}08` }}>
                <p className="text-[10px] font-bold mb-1.5" style={{ color }}>{cat}</p>
                <div className="h-1 rounded-full bg-surface overflow-hidden flex mb-1.5">
                  <div className="bg-green-500 h-full" style={{ width: `${Math.round(longs / catQ.length * 100)}%` }} />
                  <div className="bg-red-500 h-full" style={{ width: `${Math.round(shorts / catQ.length * 100)}%` }} />
                </div>
                <div className="text-[9px] text-slate-500 flex justify-between">
                  <span className="text-green-400">▲{longs}</span>
                  <span className={avgChg >= 0 ? "text-green-400" : "text-red-400"}>{pct(avgChg)}</span>
                  <span className="text-red-400">▼{shorts}</span>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Signal leaderboard */}
      <div className="grid grid-cols-2 gap-4">
        {[
          { label: "Strongest LONG",  sig: "LONG",  cls: "text-green-400", border: "border-green-500/20" },
          { label: "Strongest SHORT", sig: "SHORT", cls: "text-red-400",   border: "border-red-500/20"   },
        ].map(({ label, sig, cls, border }) => {
          const list = quotes.filter((q) => q.signal === sig).sort((a, b) => b.confidence - a.confidence).slice(0, 5);
          return (
            <div key={sig} className={`bg-card border ${border} rounded-xl p-4`}>
              <p className={`text-xs font-semibold ${cls} mb-3`}>{label}</p>
              {list.length === 0 ? (
                <p className="text-[10px] text-slate-600">No {sig} signals</p>
              ) : (
                <div className="space-y-2">
                  {list.map((q) => (
                    <button
                      key={q.symbol}
                      onClick={() => {
                        const node = graphData.nodes.find((n) => n.id === q.symbol);
                        if (node) { handleNodeClick(node); setSearch(q.symbol); }
                      }}
                      className="w-full flex items-center justify-between hover:bg-surface/50 rounded px-1 py-0.5 transition-colors"
                    >
                      <div className="text-left">
                        <span className="text-xs font-medium">{q.name.split(" ")[0]}</span>
                        <span className="text-[10px] text-slate-500 ml-1.5 font-mono">{q.symbol}</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <div className="w-14 h-1 bg-surface rounded-full overflow-hidden">
                          <div
                            className={`h-full rounded-full ${sig === "LONG" ? "bg-green-500" : "bg-red-500"}`}
                            style={{ width: `${Math.round(q.confidence * 100)}%` }}
                          />
                        </div>
                        <span className={`text-[10px] font-bold ${cls}`}>{Math.round(q.confidence * 100)}%</span>
                        <span className={`text-[10px] font-mono ${(q.change_pct ?? 0) >= 0 ? "text-green-400" : "text-red-400"}`}>
                          {pct(q.change_pct)}
                        </span>
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
