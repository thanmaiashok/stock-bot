import { useState, useRef, useEffect } from "react";
import { useOutletContext, useNavigate } from "react-router-dom";
import axios from "axios";
import CandlestickChart from "../components/CandlestickChart";
import {
  ArrowUpRight, ArrowDownRight, Minus, Bot, Zap,
  ChevronUp, ChevronDown, Flame, TrendingUp, TrendingDown,
  BarChart2, X,
} from "lucide-react";
import { fmt, pct, CATEGORY_COLORS, SIG_COLORS } from "./FuturesShell";
import MarketCommentary from "../components/MarketCommentary";

// ---------------------------------------------------------------------------
// Ticker strip
// ---------------------------------------------------------------------------
function TickerStrip({ quotes }) {
  const ref = useRef(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    let pos = 0;
    const id = setInterval(() => {
      pos += 1;
      if (pos > el.scrollWidth / 2) pos = 0;
      el.scrollLeft = pos;
    }, 30);
    return () => clearInterval(id);
  }, [quotes]);

  if (!quotes.length) return null;
  const items = [...quotes, ...quotes];
  return (
    <div
      ref={ref}
      className="overflow-hidden whitespace-nowrap border-b border-border bg-card/50 py-2 px-3 text-xs select-none shrink-0"
      style={{ scrollBehavior: "auto" }}
    >
      {items.map((q, i) => (
        <span key={`${q.symbol}-${i}`} className="inline-flex items-center gap-1.5 mr-6">
          <span className="text-slate-300 font-medium">{q.name.split(" ")[0]}</span>
          <span className="font-mono">{fmt(q.price, q.price > 100 ? 2 : 4)}</span>
          <span className={q.change_pct >= 0 ? "text-buy" : "text-sell"}>{pct(q.change_pct)}</span>
          {q.signal !== "NEUTRAL" && (
            <span className={`text-[10px] font-bold ${q.signal === "LONG" ? "text-buy" : "text-sell"}`}>
              {q.signal === "LONG" ? "▲" : "▼"}
            </span>
          )}
        </span>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Signal card (futures flavour — mirrors stocks SignalCard)
// ---------------------------------------------------------------------------
function SignalCard({ q, pred, onSelect }) {
  const catCls     = CATEGORY_COLORS[q.category] || "text-slate-400 bg-slate-700/20 border-slate-600";
  const p          = pred?.[q.symbol];
  const trend1h    = p?.change_1h ?? 0;
  const sigColor   = q.signal === "LONG" ? "text-buy" : "text-sell";
  const sigBg      = q.signal === "LONG"
    ? "border-buy/30 bg-buy/5"
    : "border-sell/30 bg-sell/5";
  const confBar    = q.signal === "LONG" ? "bg-buy" : "bg-sell";

  return (
    <button
      onClick={() => onSelect && onSelect(q)}
      className={`text-left w-full rounded-xl border p-3.5 transition-all hover:scale-[1.01] ${sigBg}`}
    >
      {/* Top row */}
      <div className="flex items-start justify-between mb-2">
        <div className="flex-1 min-w-0 pr-2">
          <p className="text-[10px] font-mono text-slate-500">{q.symbol}</p>
          <p className="text-sm font-semibold leading-tight truncate">{q.name}</p>
        </div>
        <div className="text-right shrink-0">
          <p className={`text-base font-bold ${sigColor}`}>{q.signal}</p>
          <p className="text-[10px] text-slate-500">Conf {Math.round(q.confidence * 100)}%</p>
        </div>
      </div>

      {/* Confidence bar */}
      <div className="h-1 bg-surface rounded-full overflow-hidden mb-2">
        <div
          className={`h-full ${confBar} rounded-full`}
          style={{ width: `${Math.round(q.confidence * 100)}%` }}
        />
      </div>

      {/* Bottom row */}
      <div className="flex items-center justify-between text-[10px]">
        <span className={`px-1.5 py-0.5 rounded border ${catCls}`}>{q.category}</span>
        <div className="flex items-center gap-2 text-slate-500">
          <span className={q.change_pct >= 0 ? "text-buy" : "text-sell"}>{pct(q.change_pct)}</span>
          {p && (
            <span className="flex items-center gap-0.5">
              {trend1h > 0 ? <ArrowUpRight size={9} className="text-buy" /> : trend1h < 0 ? <ArrowDownRight size={9} className="text-sell" /> : <Minus size={9} />}
              1h {pct(trend1h)}
            </span>
          )}
        </div>
      </div>

      {/* Signal reason */}
      {q.signal_reason && (
        <p className="mt-1.5 text-[10px] text-slate-600 truncate">{q.signal_reason}</p>
      )}
    </button>
  );
}

// ---------------------------------------------------------------------------
// Instrument detail panel
// ---------------------------------------------------------------------------
function InstrumentDetail({ q, pred, position, onClose }) {
  const p = pred?.[q.symbol];
  const [chartData, setChartData] = useState([]);

  useEffect(() => {
    if (!q?.symbol) return;
    let alive = true;
    async function fetchChart() {
      try {
        const r = await axios.get(`/api/futures/chart/${q.symbol}?period=5d&interval=15m`);
        const mapped = (r.data ?? []).map(d => ({ date: d.t, open: d.o, high: d.h, low: d.l, close: d.c, volume: d.v }));
        if (alive) setChartData(mapped);
      } catch {}
    }
    fetchChart();
    const id = setInterval(fetchChart, 5000);
    return () => { alive = false; clearInterval(id); };
  }, [q?.symbol]);

  return (
    <div className="bg-card border border-orange-500/40 rounded-xl p-4 space-y-3">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-[10px] text-slate-500 font-mono">{q.symbol}</p>
          <p className="text-lg font-bold">{q.name}</p>
          <p className="text-[10px] text-slate-500">{q.unit}</p>
        </div>
        <button onClick={onClose} className="text-slate-500 hover:text-slate-300 mt-1">
          <X size={14} />
        </button>
      </div>

      <div className="grid grid-cols-3 gap-2">
        <div className="bg-surface rounded-lg p-2.5">
          <p className="text-[10px] text-slate-500 mb-0.5">Price</p>
          <p className="font-bold font-mono text-sm">{fmt(q.price, q.price > 100 ? 2 : 4)}</p>
          <p className={`text-[10px] ${q.change_pct >= 0 ? "text-buy" : "text-sell"}`}>{pct(q.change_pct)} today</p>
        </div>
        <div className="bg-surface rounded-lg p-2.5">
          <p className="text-[10px] text-slate-500 mb-0.5">Signal</p>
          <p className={`font-bold text-sm ${q.signal === "LONG" ? "text-buy" : q.signal === "SHORT" ? "text-sell" : "text-slate-400"}`}>
            {q.signal}
          </p>
          <p className="text-[10px] text-slate-500">conf {Math.round(q.confidence * 100)}%</p>
        </div>
        <div className="bg-surface rounded-lg p-2.5">
          <p className="text-[10px] text-slate-500 mb-0.5">Position</p>
          {position ? (
            <>
              <p className={`font-bold text-sm ${position.direction === "long" ? "text-buy" : "text-sell"}`}>
                {position.direction.toUpperCase()}
              </p>
              <p className={`text-[10px] font-semibold ${position.pnl >= 0 ? "text-buy" : "text-sell"}`}>
                P&L {position.pnl >= 0 ? "+" : ""}{fmt(position.pnl)}
              </p>
            </>
          ) : (
            <p className="text-[10px] text-slate-500 mt-1">No position</p>
          )}
        </div>
      </div>

      {q.signal_reason && (
        <div className="bg-surface rounded-lg px-3 py-2 text-[10px] text-slate-400">
          <span className="text-slate-600">Signal: </span>{q.signal_reason}
        </div>
      )}

      {/* Live chart — 15m candles, refreshes every 5s */}
      <div className="bg-surface rounded-xl p-3">
        <div className="flex items-center justify-between mb-2">
          <p className="text-[10px] text-slate-500 uppercase tracking-wider">Price (15m · 5d)</p>
          <span className="text-[10px] text-orange-400 animate-pulse">● LIVE</span>
        </div>
        <CandlestickChart data={chartData} height={200} />
      </div>

      <div className="grid grid-cols-4 gap-2 text-center text-[10px]">
        {[["Open", q.day_open], ["High", q.day_high], ["Low", q.day_low], ["Prev", q.prev_close]].map(([label, val]) => (
          <div key={label} className="bg-surface rounded-lg py-1.5">
            <p className="text-slate-600 mb-0.5">{label}</p>
            <p className="font-mono font-semibold">{fmt(val, val > 100 ? 2 : 4)}</p>
          </div>
        ))}
      </div>

      {p && (
        <div>
          <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-1.5">Bot Forecast</p>
          <div className="grid grid-cols-3 gap-2">
            {[["1h", p.pred_1h, p.change_1h], ["4h", p.pred_4h, p.change_4h], ["1d", p.pred_1d, p.change_1d]].map(([label, price, chg]) => (
              <div key={label} className="bg-surface rounded-lg p-2 text-center">
                <p className="text-[10px] text-slate-600 mb-0.5">+{label}</p>
                <p className="font-mono text-xs font-bold">{fmt(price, price > 100 ? 2 : 4)}</p>
                <p className={`text-[10px] font-semibold ${chg >= 0 ? "text-buy" : "text-sell"}`}>{pct(chg)}</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Markets Dashboard
// ---------------------------------------------------------------------------
const CATEGORIES = ["Energy", "Metals", "Agriculture", "Indices", "Crypto"];

export default function FuturesMarkets() {
  const { quotes, portfolio, predictions, botStatus, perf, lastUpdate } = useOutletContext();
  const [selected, setSelected] = useState(null);

  const threshold  = botStatus?.confidence_threshold ?? 0.52;
  const openSymbols = new Set((portfolio?.positions ?? []).map((p) => p.symbol));
  const totalPnl   = portfolio?.total_pnl ?? 0;
  const openCount  = portfolio?.positions?.length ?? 0;

  const longs  = quotes.filter((q) => q.signal === "LONG").sort((a, b) => b.confidence - a.confidence);
  const shorts = quotes.filter((q) => q.signal === "SHORT").sort((a, b) => b.confidence - a.confidence);
  const allSignals = quotes.filter((q) => q.signal !== "NEUTRAL");

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <TickerStrip quotes={quotes} />

      <div className="flex-1 overflow-y-auto p-6 space-y-6">

        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold flex items-center gap-2">
              <Flame className="text-orange-400" size={22} />
              Futures Dashboard
            </h1>
            <p className="text-slate-500 text-sm mt-0.5">
              {quotes.length} instruments · {allSignals.length} active signals · {lastUpdate?.toLocaleTimeString()}
            </p>
          </div>
          <div className="flex items-center gap-2 bg-orange-500/10 border border-orange-500/30 rounded-lg px-3 py-2">
            <Bot size={14} className="text-orange-400" />
            <div>
              <p className="text-[10px] font-bold text-orange-400">BOT LIVE</p>
              <p className="text-[9px] text-slate-500">Scanning every 30s</p>
            </div>
            <span className="w-1.5 h-1.5 rounded-full bg-orange-400 animate-pulse ml-1" />
          </div>
        </div>

        {/* AI Commentary */}
        <MarketCommentary mode="futures" />

        {/* Stats row */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <div className="bg-card border border-border rounded-xl p-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs text-slate-500 uppercase tracking-wider">Equity</span>
              <BarChart2 size={14} className="text-slate-600" />
            </div>
            <p className="text-2xl font-bold font-mono">${fmt(portfolio?.equity ?? portfolio?.cash ?? 0)}</p>
            <p className="text-xs text-slate-500 mt-1">Cash: ${fmt(portfolio?.cash ?? 0)}</p>
          </div>

          <div className="bg-card border border-border rounded-xl p-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs text-slate-500 uppercase tracking-wider">Open P&L</span>
              {totalPnl >= 0 ? <TrendingUp size={14} className="text-buy" /> : <TrendingDown size={14} className="text-sell" />}
            </div>
            <p className={`text-2xl font-bold font-mono ${totalPnl >= 0 ? "text-buy" : "text-sell"}`}>
              {totalPnl >= 0 ? "+" : ""}${fmt(totalPnl)}
            </p>
            <p className="text-xs text-slate-500 mt-1">Margin: ${fmt(portfolio?.margin_used ?? 0)}</p>
          </div>

          <div className="bg-card border border-border rounded-xl p-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs text-slate-500 uppercase tracking-wider">Open Positions</span>
              <Zap size={14} className="text-slate-600" />
            </div>
            <p className="text-2xl font-bold">{openCount}</p>
            <p className="text-xs text-slate-500 mt-1">
              {perf?.closed ? `Win rate: ${(perf.win_rate * 100).toFixed(0)}%` : "No closed trades yet"}
            </p>
          </div>

          <div className="bg-card border border-border rounded-xl p-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs text-slate-500 uppercase tracking-wider">Active Signals</span>
              <Flame size={14} className="text-orange-400" />
            </div>
            <p className="text-2xl font-bold">{allSignals.length}</p>
            <p className="text-xs text-slate-500 mt-1">
              LONG: {longs.length} · SHORT: {shorts.length}
            </p>
          </div>
        </div>

        {/* Instrument detail panel */}
        {selected && (
          <InstrumentDetail
            q={selected}
            pred={predictions}
            position={(portfolio?.positions ?? []).find((p) => p.symbol === selected.symbol)}
            onClose={() => setSelected(null)}
          />
        )}

        {/* Top LONG Signals */}
        <div>
          <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-wider mb-3 flex items-center gap-2">
            <ChevronUp size={14} className="text-buy" />
            Top LONG Signals
          </h2>
          {longs.length === 0 ? (
            <p className="text-slate-600 text-sm">No LONG signals above threshold. Bot is watching…</p>
          ) : (
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6 gap-3">
              {longs.slice(0, 6).map((q) => (
                <SignalCard key={q.symbol} q={q} pred={predictions} onSelect={setSelected} />
              ))}
            </div>
          )}
        </div>

        {/* Top SHORT Signals */}
        {shorts.length > 0 && (
          <div>
            <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-wider mb-3 flex items-center gap-2">
              <ChevronDown size={14} className="text-sell" />
              SHORT Signals
            </h2>
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6 gap-3">
              {shorts.slice(0, 6).map((q) => (
                <SignalCard key={q.symbol} q={q} pred={predictions} onSelect={setSelected} />
              ))}
            </div>
          </div>
        )}

        {/* Category breakdown */}
        <div className="bg-card border border-border rounded-xl p-4">
          <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-wider mb-4">
            Instrument Breakdown
          </h2>
          <div className="grid grid-cols-5 gap-4 text-center mb-4">
            {CATEGORIES.map((cat) => {
              const catQ    = quotes.filter((q) => q.category === cat);
              const lonCt   = catQ.filter((q) => q.signal === "LONG").length;
              const shoCt   = catQ.filter((q) => q.signal === "SHORT").length;
              const catCls  = CATEGORY_COLORS[cat]?.split(" ")[0] ?? "text-slate-400";
              return (
                <div key={cat}>
                  <p className={`text-2xl font-bold ${catCls}`}>{catQ.length}</p>
                  <p className="text-xs text-slate-500 mt-0.5">{cat}</p>
                  <p className="text-[10px] text-slate-600 mt-0.5">
                    <span className="text-buy">▲{lonCt}</span> · <span className="text-sell">▼{shoCt}</span>
                  </p>
                </div>
              );
            })}
          </div>

          {/* All instruments mini-table */}
          <div className="grid grid-cols-1 gap-0 border-t border-border pt-3">
            {CATEGORIES.map((cat) => {
              const catQ = quotes.filter((q) => q.category === cat);
              if (!catQ.length) return null;
              const catCls = CATEGORY_COLORS[cat]?.split(" ")[0] ?? "text-slate-400";
              return (
                <div key={cat} className="mb-2">
                  <p className={`text-[10px] font-bold uppercase tracking-wider mb-1 ${catCls}`}>{cat}</p>
                  <div className="flex flex-wrap gap-2">
                    {catQ.map((q) => {
                      const isOpen = openSymbols.has(q.symbol);
                      return (
                        <button
                          key={q.symbol}
                          onClick={() => setSelected(selected?.symbol === q.symbol ? null : q)}
                          className={`flex items-center gap-1.5 rounded-lg border px-2 py-1 text-[10px] transition-colors ${
                            selected?.symbol === q.symbol
                              ? "border-orange-500 bg-orange-500/10"
                              : "border-border bg-surface hover:border-slate-500"
                          }`}
                        >
                          <span className="font-mono text-slate-300">{q.symbol.replace("=F", "").replace("-USD", "")}</span>
                          <span className="font-bold font-mono">{fmt(q.price, q.price > 100 ? 2 : 4)}</span>
                          <span className={q.change_pct >= 0 ? "text-buy" : "text-sell"}>{pct(q.change_pct)}</span>
                          {q.signal !== "NEUTRAL" && (
                            <span className={`font-bold ${q.signal === "LONG" ? "text-buy" : "text-sell"}`}>
                              {q.signal === "LONG" ? "▲" : "▼"}{Math.round(q.confidence * 100)}%
                            </span>
                          )}
                          {isOpen && <span className="text-orange-400">●</span>}
                        </button>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Bot decision weights — compact */}
        <div className="bg-card border border-orange-500/20 rounded-xl p-4">
          <div className="flex items-center gap-2 mb-3">
            <Bot size={14} className="text-orange-400" />
            <p className="text-xs text-slate-500 uppercase tracking-wider">Auto-Trader Decision Engine</p>
            <span className="ml-auto text-[10px] text-orange-400 font-bold animate-pulse">LIVE</span>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {[
              { label: "Momentum",    pct: 35, color: "bg-orange-400" },
              { label: "EMA Cross",   pct: 30, color: "bg-yellow-400" },
              { label: "RSI",         pct: 20, color: "bg-blue-400"   },
              { label: "Consistency", pct: 15, color: "bg-purple-400" },
            ].map((w) => (
              <div key={w.label}>
                <div className="flex justify-between text-[10px] text-slate-400 mb-1">
                  <span>{w.label}</span><span>{w.pct}%</span>
                </div>
                <div className="h-1.5 bg-surface rounded-full overflow-hidden">
                  <div className={`h-full ${w.color} rounded-full`} style={{ width: `${w.pct}%` }} />
                </div>
              </div>
            ))}
          </div>
          <div className="grid grid-cols-4 gap-2 mt-3 text-center">
            {[
              ["Threshold", `${Math.round((botStatus?.confidence_threshold ?? 0.52) * 100)}%`],
              ["Leverage",  "10×"],
              ["Stop Loss", "2%"],
              ["Take Profit","4%"],
            ].map(([label, val]) => (
              <div key={label} className="bg-surface/60 rounded-lg py-1.5">
                <p className="text-[9px] text-slate-600 mb-0.5">{label}</p>
                <p className="text-xs font-bold font-mono">{val}</p>
              </div>
            ))}
          </div>
        </div>

      </div>
    </div>
  );
}
