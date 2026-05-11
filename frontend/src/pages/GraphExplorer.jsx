import { useState, useEffect, useCallback, useRef } from "react";
import axios from "axios";
import { useNavigate } from "react-router-dom";
import ForceGraph2D from "react-force-graph-2d";
import { RefreshCw } from "lucide-react";

const NODE_COLORS = {
  stock:  { center: "#a855f7", buy: "#22c55e", sell: "#ef4444", hold: "#64748b" },
  sector: { fill: "#0ea5e9" },
  news:   { fill: "#f59e0b" },
};

const LINK_COLORS = {
  CORRELATES_WITH: "#1e293b",
  BELONGS_TO:      "#0ea5e9",
  MENTIONS:        "#d97706",
};

function stockColor(node) {
  if (node.isCenter) return NODE_COLORS.stock.center;
  if (node.signal === "BUY")  return NODE_COLORS.stock.buy;
  if (node.signal === "SELL") return NODE_COLORS.stock.sell;
  return NODE_COLORS.stock.hold;
}

export default function GraphExplorer() {
  const nav = useNavigate();
  const [ticker, setTicker]         = useState(null);
  const [input, setInput]           = useState("");
  const [graphData, setGraphData]   = useState({ nodes: [], links: [] });
  const [loading, setLoading]       = useState(false);
  const [selected, setSelected]     = useState(null);
  const [mode, setMode]             = useState("market");
  const [showDrop, setShowDrop]     = useState(false);
  const [dimensions, setDimensions] = useState({ w: 900, h: 580 });
  const containerRef = useRef(null);
  const fgRef        = useRef(null);
  const searchRef    = useRef(null);

  useEffect(() => {
    if (!containerRef.current) return;
    const ro = new ResizeObserver(([e]) => {
      setDimensions({ w: e.contentRect.width, h: 520 });
    });
    ro.observe(containerRef.current);
    return () => ro.disconnect();
  }, []);

  const loadMarket = useCallback(async () => {
    setLoading(true);
    setSelected(null);
    setMode("market");
    try {
      const { data } = await axios.get("/api/graph/market");
      setGraphData({ nodes: data.nodes, links: data.links });
    } catch {
      setGraphData({ nodes: [], links: [] });
    }
    setLoading(false);
  }, []);

  const loadStock = useCallback(async (t) => {
    setLoading(true);
    setSelected(null);
    setMode("stock");
    try {
      const { data } = await axios.get(`/api/graph/knowledge/${t}`);
      setGraphData({ nodes: data.nodes, links: data.links });
    } catch {
      setGraphData({ nodes: [{ id: t, type: "stock", label: t, isCenter: true }], links: [] });
    }
    setLoading(false);
  }, []);

  // Default: load full market on mount
  useEffect(() => { loadMarket(); }, [loadMarket]);

  const handleSearch = () => {
    if (!input.trim()) { loadMarket(); setTicker(null); return; }
    setTicker(input.trim());
    loadStock(input.trim());
  };

  useEffect(() => {
    if (!fgRef.current || !graphData.nodes.length) return;
    // Market view needs stronger repulsion — many nodes
    const charge = mode === "market" ? -180 : -350;
    const dist   = mode === "market" ? 60   : 90;
    fgRef.current.d3Force("charge").strength(charge);
    fgRef.current.d3Force("link").distance(dist);
    fgRef.current.d3ReheatSimulation();
  }, [graphData, mode]);

  const handleNodeClick = useCallback((node) => {
    if (node.type === "stock") {
      setSelected(prev => prev?.id === node.id ? null : node);
    } else if (node.type === "news") {
      setSelected(prev => prev?.id === node.id ? null : node);
    } else {
      setSelected(null);
    }
  }, []);

  const paintNode = useCallback((node, ctx, globalScale) => {
    const x = node.x, y = node.y;
    const isSelected = node.__selected;

    if (node.type === "sector") {
      const s = 6;
      ctx.beginPath();
      ctx.moveTo(x, y - s); ctx.lineTo(x + s, y);
      ctx.lineTo(x, y + s); ctx.lineTo(x - s, y);
      ctx.closePath();
      ctx.fillStyle = NODE_COLORS.sector.fill;
      ctx.fill();
      const fs = Math.max(6, 10 / globalScale);
      ctx.font = `${fs}px Sans-Serif`;
      ctx.fillStyle = "#7dd3fc";
      ctx.textAlign = "center";
      ctx.textBaseline = "top";
      ctx.fillText(node.label, x, y + 8);

    } else if (node.type === "news") {
      const s = isSelected ? 6 : 3;
      ctx.fillStyle = NODE_COLORS.news.fill;
      ctx.beginPath();
      ctx.arc(x, y, s, 0, 2 * Math.PI);
      ctx.fill();

    } else {
      // Stock
      const r = node.isCenter ? 11 : isSelected ? 9 : 5 + (node.confidence || 0) * 3;
      ctx.beginPath();
      ctx.arc(x, y, r, 0, 2 * Math.PI);
      ctx.fillStyle = stockColor(node);
      ctx.fill();

      if (node.isCenter || isSelected) {
        ctx.strokeStyle = "#ffffff";
        ctx.lineWidth = isSelected ? 2.5 : 2;
        ctx.stroke();
      }

      // Always draw ticker label
      const fs = Math.max(6, (node.isCenter ? 12 : 9) / globalScale);
      ctx.font = `${node.isCenter || isSelected ? "bold " : ""}${fs}px Sans-Serif`;
      ctx.fillStyle = "#f1f5f9";
      ctx.textAlign = "center";
      ctx.textBaseline = "top";
      ctx.fillText(node.label, x, y + r + 1);
    }
  }, []);

  // Inject __selected flag into nodes so paintNode can read it
  const paintableNodes = graphData.nodes.map(n => ({
    ...n,
    __selected: selected?.id === n.id,
  }));
  const paintableGraph = { nodes: paintableNodes, links: graphData.links };

  const stockNodes  = graphData.nodes.filter(n => n.type === "stock" && !n.isCenter);
  const newsNodes   = graphData.nodes.filter(n => n.type === "news");
  const sectorNodes = graphData.nodes.filter(n => n.type === "sector");

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold">
            {mode === "market" ? "Market Intelligence Map" : `${ticker} · Network`}
          </h1>
          <p className="text-slate-500 text-sm">
            {mode === "market"
              ? `${graphData.nodes.length} stocks · ${graphData.links.length} correlations — search a ticker to focus`
              : "Ego-network · correlations, sector, news"}
          </p>
        </div>
        {mode === "stock" && (
          <button onClick={loadMarket}
            className="text-xs text-slate-400 hover:text-white border border-border px-3 py-1.5 rounded-lg transition-colors mt-1">
            ← All Markets
          </button>
        )}
      </div>

      {/* Search + legend */}
      <div className="flex gap-3 items-center flex-wrap">
        {/* Autocomplete search */}
        <div className="relative" ref={searchRef}>
          <input
            className="bg-card border border-border rounded-lg px-4 py-2 text-sm outline-none focus:border-accent w-44"
            value={input}
            onChange={(e) => { setInput(e.target.value.toUpperCase()); setShowDrop(true); }}
            onFocus={() => setShowDrop(true)}
            onBlur={() => setTimeout(() => setShowDrop(false), 150)}
            onKeyDown={(e) => { if (e.key === "Enter") { handleSearch(); setShowDrop(false); } if (e.key === "Escape") setShowDrop(false); }}
            placeholder="Search ticker…"
          />
          {showDrop && (() => {
            const allStocks = graphData.nodes
              .filter((n) => n.type === "stock")
              .sort((a, b) => (b.confidence ?? 0) - (a.confidence ?? 0));
            const filtered = input
              ? allStocks.filter((n) => n.id.includes(input) || (n.name || "").toUpperCase().includes(input))
              : allStocks.slice(0, 8);
            if (!filtered.length) return null;
            return (
              <div className="absolute top-full left-0 mt-1 w-56 bg-card border border-border rounded-lg shadow-xl z-50 max-h-52 overflow-y-auto">
                {!input && <div className="px-3 py-1.5 text-[10px] text-slate-600 uppercase tracking-wider border-b border-border">Top by confidence</div>}
                {filtered.map((n) => (
                  <button
                    key={n.id}
                    onMouseDown={() => {
                      setInput(n.id);
                      setTicker(n.id);
                      loadStock(n.id);
                      setShowDrop(false);
                    }}
                    className="w-full flex items-center justify-between px-3 py-2 text-xs hover:bg-surface transition-colors text-left"
                  >
                    <span className="flex items-center gap-2">
                      <span
                        className="w-1.5 h-1.5 rounded-full shrink-0"
                        style={{ background: n.signal === "BUY" ? "#22c55e" : n.signal === "SELL" ? "#ef4444" : "#64748b" }}
                      />
                      <span className="font-mono font-bold">{n.id}</span>
                      <span className="text-slate-500 truncate max-w-[90px]">{n.name}</span>
                    </span>
                    <span
                      className="text-[10px] font-bold shrink-0"
                      style={{ color: n.signal === "BUY" ? "#22c55e" : n.signal === "SELL" ? "#ef4444" : "#64748b" }}
                    >
                      {n.signal}
                    </span>
                  </button>
                ))}
              </div>
            );
          })()}
        </div>
        <button
          onClick={handleSearch}
          className="bg-accent text-white px-4 py-2 rounded-lg text-sm hover:bg-accent/80 transition-colors"
        >
          {loading ? "Loading…" : "Focus"}
        </button>
        <button
          onClick={() => { mode === "market" ? loadMarket() : loadStock(ticker); }}
          disabled={loading}
          className="flex items-center gap-1.5 text-sm border border-border text-slate-400 hover:text-white hover:border-slate-500 px-3 py-2 rounded-lg transition-colors disabled:opacity-40"
          title="Refresh graph"
        >
          <RefreshCw size={13} className={loading ? "animate-spin" : ""} />
          Refresh
        </button>
        <div className="flex gap-3 ml-auto text-xs text-slate-400">
          {[["#22c55e","BUY"],["#ef4444","SELL"],["#64748b","HOLD"],["#0ea5e9","Sector"],["#f59e0b","News"]].map(([c,l]) => (
            <span key={l} className="flex items-center gap-1">
              <span className="w-2.5 h-2.5 rounded-full inline-block" style={{background:c}} />{l}
            </span>
          ))}
        </div>
      </div>

      {/* Graph + info card overlay */}
      <div ref={containerRef} className="relative bg-card border border-border rounded-xl overflow-hidden">
        {graphData.nodes.length === 0 ? (
          <div className="h-64 flex items-center justify-center text-slate-600 text-sm">
            {loading ? "Building graph…" : "Enter ticker and click Explore."}
          </div>
        ) : (
          <ForceGraph2D
            ref={fgRef}
            graphData={paintableGraph}
            width={dimensions.w}
            height={dimensions.h}
            backgroundColor="#0f1117"
            nodeLabel={(n) => {
              if (n.type === "news") return n.label;
              if (n.type === "sector") return `Sector: ${n.label}`;
              return `${n.id} · ${n.name || ""} · ${n.signal} ${((n.confidence||0)*100).toFixed(0)}%`;
            }}
            nodeCanvasObject={paintNode}
            nodeCanvasObjectMode={() => "replace"}
            linkColor={(l) => LINK_COLORS[l.type] || "#1e293b"}
            linkWidth={(l) => l.type === "CORRELATES_WITH" ? Math.max(0.5, (l.weight||0.5)*2) : 1}
            linkDirectionalArrowLength={(l) => l.type === "BELONGS_TO" ? 4 : 0}
            linkDirectionalArrowRelPos={1}
            onNodeClick={handleNodeClick}
            onBackgroundClick={() => setSelected(null)}
            cooldownTicks={120}
            d3AlphaDecay={0.02}
            d3VelocityDecay={0.3}
          />
        )}

        {/* Info card — slides in top-right when node selected */}
        {selected && (
          <div className="absolute top-3 right-3 w-56 bg-[#0f1117]/95 border border-border rounded-xl p-4 shadow-xl backdrop-blur-sm">
            <button
              onClick={() => setSelected(null)}
              className="absolute top-2 right-3 text-slate-500 hover:text-white text-lg leading-none"
            >×</button>

            {selected.type === "stock" ? (
              <>
                <p className="text-lg font-bold mb-0.5">{selected.id}</p>
                <p className="text-xs text-slate-400 mb-3 leading-tight">{selected.name}</p>
                <div className="flex items-center gap-2 mb-3">
                  <span className="text-xs font-bold px-2 py-0.5 rounded-full border"
                    style={{
                      color: selected.signal==="BUY"?"#22c55e":selected.signal==="SELL"?"#ef4444":"#64748b",
                      borderColor: selected.signal==="BUY"?"#22c55e":selected.signal==="SELL"?"#ef4444":"#64748b",
                    }}>
                    {selected.signal}
                  </span>
                  <span className="text-xs text-slate-400">{((selected.confidence||0)*100).toFixed(0)}% conf</span>
                </div>
                {selected.exchange && (
                  <p className="text-xs text-slate-500 mb-3">{selected.exchange}</p>
                )}
                <div className="flex gap-2">
                  <button
                    onClick={() => nav(`/stocks/stock/${selected.id}`)}
                    className="flex-1 text-xs bg-accent text-white py-1.5 rounded-lg hover:bg-accent/80 transition-colors"
                  >
                    View Details
                  </button>
                  <button
                    onClick={() => { setInput(selected.id); setTicker(selected.id); loadStock(selected.id); }}
                    className="flex-1 text-xs bg-surface border border-border py-1.5 rounded-lg hover:border-accent transition-colors"
                  >
                    Focus
                  </button>
                </div>
              </>
            ) : (
              <>
                <p className="text-xs text-amber-400 font-medium mb-1">News</p>
                <p className="text-xs text-slate-300 leading-relaxed">{selected.label}</p>
                {selected.published_at && (
                  <p className="text-xs text-slate-600 mt-2">{selected.published_at?.slice(0,10)}</p>
                )}
              </>
            )}
          </div>
        )}
      </div>

      {/* Bottom panels */}
      {graphData.nodes.length > 1 && (
        <div className="grid grid-cols-3 gap-3">
          <div className="bg-card border border-border rounded-xl p-4">
            <p className="text-xs text-slate-500 uppercase tracking-wider mb-2">Peers ({stockNodes.length})</p>
            <div className="space-y-1 max-h-40 overflow-y-auto">
              {stockNodes.slice(0,12).map(n => (
                <button key={n.id}
                  onClick={() => { setInput(n.id); setTicker(n.id); loadStock(n.id); }}
                  className="w-full flex justify-between text-xs px-2 py-1 rounded hover:bg-surface transition-colors"
                >
                  <span className="font-medium">{n.id}</span>
                  <span style={{color:n.signal==="BUY"?"#22c55e":n.signal==="SELL"?"#ef4444":"#64748b"}}>{n.signal}</span>
                </button>
              ))}
            </div>
          </div>
          <div className="bg-card border border-border rounded-xl p-4">
            <p className="text-xs text-slate-500 uppercase tracking-wider mb-2">Sectors ({sectorNodes.length})</p>
            <div className="space-y-1">
              {sectorNodes.map(n => (
                <div key={n.id} className="text-xs px-2 py-1 rounded bg-surface text-sky-400">{n.label}</div>
              ))}
              {sectorNodes.length === 0 && <p className="text-xs text-slate-600">Run fundamentals fetch to populate</p>}
            </div>
          </div>
          <div className="bg-card border border-border rounded-xl p-4">
            <p className="text-xs text-slate-500 uppercase tracking-wider mb-2">News ({newsNodes.length})</p>
            <div className="space-y-1 max-h-40 overflow-y-auto">
              {newsNodes.map(n => (
                <button key={n.id} onClick={() => setSelected(n)}
                  className="w-full text-left text-xs text-slate-400 truncate px-1 py-0.5 hover:text-white transition-colors">
                  {n.label}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
