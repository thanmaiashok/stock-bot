import { useState, useEffect, useCallback, useRef } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import {
  ArrowLeft, Flame, RefreshCw, X, ChevronUp, ChevronDown,
  Bot, ArrowUpRight, ArrowDownRight, Minus, Zap, TrendingUp,
} from "lucide-react";

const api          = (path) => axios.get(`/api${path}`).then((r) => r.data);
const REFRESH_MS   = 8000;
const PRED_REFRESH = 60_000;

const CATEGORY_COLORS = {
  Energy:      "text-orange-400 bg-orange-400/10 border-orange-400/20",
  Metals:      "text-yellow-400 bg-yellow-400/10 border-yellow-400/20",
  Agriculture: "text-green-400  bg-green-400/10  border-green-400/20",
  Indices:     "text-blue-400   bg-blue-400/10   border-blue-400/20",
  Crypto:      "text-purple-400 bg-purple-400/10 border-purple-400/20",
};

const SIG_COLORS = {
  LONG:    "bg-green-500/20 text-green-400 border border-green-500/30",
  SHORT:   "bg-red-500/20   text-red-400   border border-red-500/30",
  NEUTRAL: "bg-slate-700/60 text-slate-500",
};

function fmt(n, dec = 2) {
  if (n == null) return "—";
  return Number(n).toLocaleString("en-US", { minimumFractionDigits: dec, maximumFractionDigits: dec });
}
function pct(n) {
  if (n == null) return "—";
  const v = Number(n);
  return `${v >= 0 ? "+" : ""}${v.toFixed(2)}%`;
}

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
    <div ref={ref} className="overflow-hidden whitespace-nowrap border-b border-border bg-card/50 py-2 px-3 text-xs select-none" style={{ scrollBehavior: "auto" }}>
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
// Instrument card
// ---------------------------------------------------------------------------
function QuoteCard({ q, pred, onSelect, selected }) {
  const catCls    = CATEGORY_COLORS[q.category] || "text-slate-400 bg-slate-700/20 border-slate-600";
  const p         = pred?.[q.symbol];
  const trend1h   = p?.change_1h ?? 0;
  const isSelected = selected?.symbol === q.symbol;

  return (
    <button
      onClick={() => onSelect(isSelected ? null : q)}
      className={`text-left w-full rounded-xl border p-3 transition-all cursor-pointer ${
        isSelected
          ? "border-orange-500 bg-orange-500/5 ring-1 ring-orange-500/30"
          : "border-border bg-card hover:border-orange-400/50 hover:bg-card/80"
      }`}
    >
      <div className="flex items-start justify-between mb-1.5">
        <div>
          <p className="text-[10px] text-slate-500 font-mono">{q.symbol}</p>
          <p className="text-sm font-semibold leading-tight">{q.name}</p>
        </div>
        <span className={`text-[10px] px-1.5 py-0.5 rounded border ${catCls}`}>{q.category}</span>
      </div>

      <div className="flex items-end justify-between mt-2">
        <div>
          <p className="text-lg font-bold font-mono leading-none">{fmt(q.price, q.price > 100 ? 2 : 4)}</p>
          <p className="text-[10px] mt-0.5 text-slate-500">{q.unit}</p>
        </div>
        <div className="text-right">
          <p className={`text-sm font-medium ${q.change_pct >= 0 ? "text-buy" : "text-sell"}`}>{pct(q.change_pct)}</p>
          <span className={`text-[10px] px-1.5 py-0.5 rounded font-semibold ${SIG_COLORS[q.signal] || SIG_COLORS.NEUTRAL}`}>
            {q.signal}
          </span>
        </div>
      </div>

      {q.confidence > 0 && (
        <div className="mt-2 h-0.5 bg-surface rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full transition-all ${q.signal === "LONG" ? "bg-buy" : q.signal === "SHORT" ? "bg-sell" : "bg-slate-600"}`}
            style={{ width: `${Math.round(q.confidence * 100)}%` }}
          />
        </div>
      )}

      {p && (
        <div className="mt-1.5 flex items-center gap-1 text-[10px] text-slate-500">
          {trend1h > 0 ? <ArrowUpRight size={10} className="text-buy" /> : trend1h < 0 ? <ArrowDownRight size={10} className="text-sell" /> : <Minus size={10} />}
          <span>1h: <span className={trend1h >= 0 ? "text-buy" : "text-sell"}>{pct(trend1h)}</span></span>
          {p.volatility != null && <span className="ml-1 text-slate-600">vol {p.volatility?.toFixed(2)}%</span>}
        </div>
      )}
    </button>
  );
}

// ---------------------------------------------------------------------------
// Instrument detail panel (shown when card clicked)
// ---------------------------------------------------------------------------
function InstrumentDetail({ q, pred, position, onClose }) {
  const p = pred?.[q.symbol];
  if (!q) return null;

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

      {/* Price + signal */}
      <div className="grid grid-cols-3 gap-2">
        <div className="bg-surface rounded-lg p-2.5">
          <p className="text-[10px] text-slate-500 mb-0.5">Price</p>
          <p className="font-bold font-mono text-sm">{fmt(q.price, q.price > 100 ? 2 : 4)}</p>
          <p className={`text-[10px] ${q.change_pct >= 0 ? "text-buy" : "text-sell"}`}>{pct(q.change_pct)} today</p>
        </div>
        <div className="bg-surface rounded-lg p-2.5">
          <p className="text-[10px] text-slate-500 mb-0.5">Signal</p>
          <p className={`font-bold text-sm ${SIG_COLORS[q.signal]?.includes("green") ? "text-buy" : SIG_COLORS[q.signal]?.includes("red") ? "text-sell" : "text-slate-400"}`}>
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
            <p className="text-[10px] text-slate-500 mt-1">No open position</p>
          )}
        </div>
      </div>

      {/* Signal reason */}
      {q.signal_reason && (
        <div className="bg-surface rounded-lg px-3 py-2 text-[10px] text-slate-400">
          <span className="text-slate-600">Signal reason: </span>{q.signal_reason}
        </div>
      )}

      {/* OHLC */}
      <div className="grid grid-cols-4 gap-2 text-center text-[10px]">
        {[["Open", q.day_open], ["High", q.day_high], ["Low", q.day_low], ["Prev", q.prev_close]].map(([label, val]) => (
          <div key={label} className="bg-surface rounded-lg py-1.5">
            <p className="text-slate-600 mb-0.5">{label}</p>
            <p className="font-mono font-semibold">{fmt(val, val > 100 ? 2 : 4)}</p>
          </div>
        ))}
      </div>

      {/* Predictions */}
      {p && (
        <div>
          <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-1.5">Bot Forecast (linear regression)</p>
          <div className="grid grid-cols-3 gap-2">
            {[["1 Hour", p.pred_1h, p.change_1h], ["4 Hours", p.pred_4h, p.change_4h], ["1 Day", p.pred_1d, p.change_1d]].map(([label, price, chg]) => (
              <div key={label} className="bg-surface rounded-lg p-2 text-center">
                <p className="text-[10px] text-slate-600 mb-0.5">{label}</p>
                <p className="font-mono text-xs font-bold">{fmt(price, price > 100 ? 2 : 4)}</p>
                <p className={`text-[10px] font-semibold ${chg >= 0 ? "text-buy" : "text-sell"}`}>{pct(chg)}</p>
              </div>
            ))}
          </div>
          <p className="text-[10px] text-slate-600 mt-1.5">
            Trend: <span className={p.trend === "up" ? "text-buy" : "text-sell"}>{p.trend === "up" ? "↑ Upward" : "↓ Downward"}</span>
            {" · "}Volatility: {p.volatility?.toFixed(2)}%/hr
            {" · "}R²: {(p.r2 * 100).toFixed(0)}%
          </p>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Bot status (read-only — always active)
// ---------------------------------------------------------------------------
function BotStatus({ botStatus }) {
  const weights = [
    { label: "Momentum",    pct: 35, color: "bg-orange-400" },
    { label: "EMA Cross",   pct: 30, color: "bg-yellow-400" },
    { label: "RSI",         pct: 20, color: "bg-blue-400"   },
    { label: "Consistency", pct: 15, color: "bg-purple-400" },
  ];

  return (
    <div className="rounded-xl border border-orange-500/40 bg-orange-500/5 p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Bot size={16} className="text-orange-400" />
          <div>
            <p className="font-bold text-sm">Auto-Trader Bot</p>
            <p className="text-[10px] text-slate-400">Always active · Scanning every 30s</p>
          </div>
        </div>
        <span className="text-[10px] bg-orange-500/20 text-orange-400 border border-orange-500/30 px-2 py-1 rounded font-bold animate-pulse">
          LIVE
        </span>
      </div>

      {/* Decision weights */}
      <div className="space-y-1.5 mb-3">
        <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-2">Decision Engine Weights</p>
        {weights.map((w) => (
          <div key={w.label} className="flex items-center gap-2">
            <span className="text-[10px] text-slate-400 w-20 shrink-0">{w.label}</span>
            <div className="flex-1 h-1.5 bg-surface rounded-full overflow-hidden">
              <div className={`h-full ${w.color} rounded-full`} style={{ width: `${w.pct}%` }} />
            </div>
            <span className="text-[10px] text-slate-400 w-6 text-right">{w.pct}%</span>
          </div>
        ))}
      </div>

      {/* Strategy stats */}
      <div className="grid grid-cols-4 gap-2 text-center">
        {[
          ["Threshold", `${Math.round((botStatus?.confidence_threshold ?? 0.52) * 100)}%`],
          ["Leverage",  "10×"],
          ["SL",        "2%"],
          ["TP",        "4%"],
        ].map(([label, val]) => (
          <div key={label} className="bg-surface/60 rounded-lg py-1.5">
            <p className="text-[9px] text-slate-600 mb-0.5">{label}</p>
            <p className="text-xs font-bold font-mono">{val}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Live opportunities
// ---------------------------------------------------------------------------
function LiveOpportunities({ quotes, config, openSymbols }) {
  const threshold = config?.confidence_threshold ?? 0.55;
  const opportunities = quotes
    .filter((q) => q.signal !== "NEUTRAL" && q.confidence >= threshold)
    .sort((a, b) => b.confidence - a.confidence);

  if (!opportunities.length) {
    return (
      <div className="bg-card border border-border rounded-xl p-4">
        <div className="flex items-center gap-2 mb-2">
          <Zap size={14} className="text-slate-500" />
          <p className="text-sm font-semibold">Live Opportunities</p>
        </div>
        <p className="text-xs text-slate-500">No signals above {Math.round(threshold * 100)}% confidence right now. Bot is watching…</p>
      </div>
    );
  }

  return (
    <div className="bg-card border border-border rounded-xl p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Zap size={14} className="text-orange-400" />
          <p className="text-sm font-semibold">Live Opportunities</p>
        </div>
        <span className="text-[10px] text-slate-500">{opportunities.length} signal{opportunities.length !== 1 ? "s" : ""} above threshold</span>
      </div>

      <div className="space-y-2">
        {opportunities.slice(0, 6).map((q) => {
          const alreadyOpen = openSymbols.has(q.symbol);
          return (
            <div key={q.symbol} className={`flex items-center justify-between rounded-lg px-3 py-2 ${
              q.signal === "LONG" ? "bg-buy/5 border border-buy/20" : "bg-sell/5 border border-sell/20"
            }`}>
              <div className="flex items-center gap-2">
                {q.signal === "LONG"
                  ? <ChevronUp size={14} className="text-buy" />
                  : <ChevronDown size={14} className="text-sell" />}
                <div>
                  <span className="text-sm font-semibold">{q.name.split(" ")[0]}</span>
                  <span className="text-[10px] text-slate-500 ml-1 font-mono">{q.symbol}</span>
                </div>
              </div>

              <div className="flex items-center gap-3 text-right">
                <div>
                  <p className="text-xs font-mono font-bold">{fmt(q.price, q.price > 100 ? 2 : 4)}</p>
                  <p className={`text-[10px] ${q.change_pct >= 0 ? "text-buy" : "text-sell"}`}>{pct(q.change_pct)}</p>
                </div>
                <div className="text-right">
                  <p className={`text-xs font-bold ${q.signal === "LONG" ? "text-buy" : "text-sell"}`}>
                    {q.signal} {Math.round(q.confidence * 100)}%
                  </p>
                  {alreadyOpen
                    ? <span className="text-[10px] text-orange-400">● IN TRADE</span>
                    : <span className="text-[10px] text-slate-500">● Watching</span>}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Positions table
// ---------------------------------------------------------------------------
function PositionsTable({ portfolio, onClose }) {
  const [closing, setClosing] = useState(null);

  async function handleClose(symbol) {
    setClosing(symbol);
    try {
      await axios.delete(`/api/futures/position/${symbol}`);
      onClose();
    } catch (err) { alert(err.response?.data?.detail || "Close failed"); }
    finally { setClosing(null); }
  }

  if (!portfolio?.positions?.length)
    return <div className="text-center py-8 text-slate-500 text-sm">Bot has no open positions</div>;

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-slate-500 text-xs border-b border-border">
            <th className="text-left py-2 pr-3">Instrument</th>
            <th className="text-left py-2 pr-3">Dir</th>
            <th className="text-right py-2 pr-3">Entry</th>
            <th className="text-right py-2 pr-3">Current</th>
            <th className="text-right py-2 pr-3">P&amp;L</th>
            <th className="text-right py-2 pr-3">SL / TP</th>
            <th className="text-right py-2 pr-3">Margin</th>
            <th className="text-right py-2">Force Close</th>
          </tr>
        </thead>
        <tbody>
          {portfolio.positions.map((pos) => (
            <tr key={pos.symbol} className="border-b border-border/50 hover:bg-white/2">
              <td className="py-2 pr-3">
                <p className="font-medium">{pos.name}</p>
                <p className="text-[10px] text-slate-500 font-mono">{pos.symbol}</p>
              </td>
              <td className="py-2 pr-3">
                <span className={`text-xs font-bold px-1.5 py-0.5 rounded ${pos.direction === "long" ? "bg-buy/20 text-buy" : "bg-sell/20 text-sell"}`}>
                  {pos.direction.toUpperCase()}
                </span>
              </td>
              <td className="py-2 pr-3 text-right font-mono text-slate-400">{fmt(pos.entry_price, pos.entry_price > 100 ? 2 : 4)}</td>
              <td className="py-2 pr-3 text-right font-mono">{fmt(pos.current_price, pos.current_price > 100 ? 2 : 4)}</td>
              <td className={`py-2 pr-3 text-right font-mono font-bold ${pos.pnl >= 0 ? "text-buy" : "text-sell"}`}>
                {pos.pnl >= 0 ? "+" : ""}{fmt(pos.pnl)}
                <span className="text-[10px] ml-1 opacity-60">({pos.pnl_pct >= 0 ? "+" : ""}{pos.pnl_pct?.toFixed(1)}%)</span>
              </td>
              <td className="py-2 pr-3 text-right font-mono text-[10px] text-slate-500">
                <span className="text-sell">{fmt(pos.stop_loss, 2)}</span>
                {" / "}
                <span className="text-buy">{fmt(pos.take_profit, 2)}</span>
              </td>
              <td className="py-2 pr-3 text-right font-mono text-slate-400">${fmt(pos.margin_used)}</td>
              <td className="py-2 text-right">
                <button
                  onClick={() => handleClose(pos.symbol)}
                  disabled={closing === pos.symbol}
                  className="text-xs px-2 py-1 border border-border rounded hover:border-sell hover:text-sell transition-colors disabled:opacity-40"
                  title="Force close this position"
                >
                  {closing === pos.symbol ? "…" : <X size={12} />}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Trade log
// ---------------------------------------------------------------------------
function TradeLog({ history }) {
  if (!history?.length)
    return <div className="text-center py-8 text-slate-500 text-sm">No trades yet</div>;

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-slate-500 text-xs border-b border-border">
            <th className="text-left py-2 pr-3">Time</th>
            <th className="text-left py-2 pr-3">Symbol</th>
            <th className="text-left py-2 pr-3">Dir</th>
            <th className="text-left py-2 pr-3">Action</th>
            <th className="text-right py-2 pr-3">Units</th>
            <th className="text-right py-2 pr-3">Price</th>
            <th className="text-right py-2 pr-3">P&amp;L</th>
            <th className="text-left py-2">Reason</th>
          </tr>
        </thead>
        <tbody>
          {history.map((t) => (
            <tr key={t.id} className="border-b border-border/50 hover:bg-white/2">
              <td className="py-2 pr-3 text-[10px] text-slate-500 whitespace-nowrap">
                {new Date(t.timestamp).toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}
              </td>
              <td className="py-2 pr-3 font-mono text-xs">{t.symbol}</td>
              <td className="py-2 pr-3">
                <span className={`text-[10px] font-bold ${t.direction === "long" ? "text-buy" : "text-sell"}`}>
                  {t.direction?.toUpperCase()}
                </span>
              </td>
              <td className="py-2 pr-3">
                <span className={`text-[10px] px-1.5 py-0.5 rounded ${t.action === "OPEN" ? "bg-slate-700 text-slate-300" : "bg-accent/20 text-accent"}`}>
                  {t.action}
                </span>
              </td>
              <td className="py-2 pr-3 text-right font-mono text-xs">{t.units}</td>
              <td className="py-2 pr-3 text-right font-mono text-xs">{fmt(t.price, t.price > 100 ? 2 : 4)}</td>
              <td className={`py-2 pr-3 text-right font-mono text-xs font-bold ${t.pnl == null ? "text-slate-500" : t.pnl >= 0 ? "text-buy" : "text-sell"}`}>
                {t.pnl == null ? "—" : `${t.pnl >= 0 ? "+" : ""}${fmt(t.pnl)}`}
              </td>
              <td className="py-2 text-[10px] text-slate-500 max-w-[140px] truncate">{t.reason || "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Predictions panel
// ---------------------------------------------------------------------------
function PredictionsPanel({ predictions, quotes }) {
  if (!predictions || !Object.keys(predictions).length)
    return <div className="text-center py-8 text-slate-500 text-sm">Loading predictions… (first run ~30s)</div>;

  const qmap = Object.fromEntries((quotes || []).map((q) => [q.symbol, q]));
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-slate-500 text-xs border-b border-border">
            <th className="text-left py-2 pr-3">Instrument</th>
            <th className="text-right py-2 pr-3">Current</th>
            <th className="text-right py-2 pr-3">Pred +1h</th>
            <th className="text-right py-2 pr-3">Pred +4h</th>
            <th className="text-right py-2 pr-3">Pred +1d</th>
            <th className="text-right py-2 pr-3">Trend</th>
            <th className="text-right py-2 pr-3">Volatility</th>
            <th className="text-right py-2">R²</th>
          </tr>
        </thead>
        <tbody>
          {Object.entries(predictions).map(([sym, p]) => {
            const q = qmap[sym];
            return (
              <tr key={sym} className="border-b border-border/50 hover:bg-white/2">
                <td className="py-2 pr-3">
                  <p className="font-medium text-sm">{q?.name || sym}</p>
                  <p className="text-[10px] text-slate-500 font-mono">{sym}</p>
                </td>
                <td className="py-2 pr-3 text-right font-mono">{fmt(p.current, p.current > 100 ? 2 : 4)}</td>
                <td className={`py-2 pr-3 text-right font-mono font-semibold ${p.change_1h >= 0 ? "text-buy" : "text-sell"}`}>
                  {fmt(p.pred_1h, p.pred_1h > 100 ? 2 : 4)}
                  <span className="text-[10px] ml-1 opacity-70">({pct(p.change_1h)})</span>
                </td>
                <td className={`py-2 pr-3 text-right font-mono text-xs ${p.change_4h >= 0 ? "text-buy" : "text-sell"}`}>{pct(p.change_4h)}</td>
                <td className={`py-2 pr-3 text-right font-mono text-xs ${p.change_1d >= 0 ? "text-buy" : "text-sell"}`}>{pct(p.change_1d)}</td>
                <td className="py-2 pr-3 text-right">
                  {p.trend === "up"
                    ? <span className="text-buy text-xs flex items-center justify-end gap-1"><TrendingUp size={10} />Up</span>
                    : <span className="text-sell text-xs">↓ Down</span>}
                </td>
                <td className="py-2 pr-3 text-right text-xs text-slate-400">{p.volatility?.toFixed(2)}%/hr</td>
                <td className="py-2 text-right text-xs text-slate-500">{(p.r2 * 100).toFixed(0)}%</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="text-[10px] text-slate-600 mt-2">Linear regression on 10d hourly closes · R² = fit quality · refreshes every 15 min</p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------
export default function FuturesApp() {
  const navigate = useNavigate();

  const [quotes,      setQuotes]      = useState([]);
  const [portfolio,   setPortfolio]   = useState(null);
  const [history,     setHistory]     = useState([]);
  const [perf,        setPerf]        = useState(null);
  const [predictions, setPredictions] = useState({});
  const [botStatus,   setBotStatus]   = useState(null);
  const [tab,         setTab]         = useState("positions");
  const [loading,     setLoading]     = useState(true);
  const [selected,    setSelected]    = useState(null);
  const [lastUpdate,  setLastUpdate]  = useState(null);

  const loadCore = useCallback(async () => {
    try {
      const [q, p, h, pf, bs] = await Promise.all([
        api("/futures/quotes"),
        api("/futures/portfolio"),
        api("/futures/history?limit=50"),
        api("/futures/performance"),
        api("/futures/bot/status"),
      ]);
      setQuotes(q);
      setPortfolio(p);
      setHistory(h);
      setPerf(pf);
      setBotStatus(bs);
      setLastUpdate(new Date());
      setLoading(false);
      // keep selected quote fresh on each refresh
      setSelected((prev) => prev ? (q.find((x) => x.symbol === prev.symbol) ?? prev) : null);
    } catch (err) {
      console.error("Futures load error:", err);
      setLoading(false);
    }
  }, []);

  const loadPredictions = useCallback(async () => {
    try { setPredictions(await api("/futures/predictions")); }
    catch (err) { console.error("Predictions error:", err); }
  }, []);

  useEffect(() => {
    loadCore();
    loadPredictions();
    const c1 = setInterval(loadCore, REFRESH_MS);
    const c2 = setInterval(loadPredictions, PRED_REFRESH);
    return () => { clearInterval(c1); clearInterval(c2); };
  }, [loadCore, loadPredictions]);

  const totalPnl   = portfolio?.total_pnl ?? 0;
  const openCount  = portfolio?.positions?.length ?? 0;
  const isAutoOn   = true;
  const openSymbols = new Set((portfolio?.positions ?? []).map((p) => p.symbol));
  const categories  = ["Energy", "Metals", "Agriculture", "Indices", "Crypto"];

  return (
    <div className="flex flex-col h-screen bg-surface overflow-hidden">
      {/* Header */}
      <header className="bg-card border-b border-border px-4 py-3 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-3">
          <button onClick={() => navigate("/")} className="flex items-center gap-1 text-xs text-slate-500 hover:text-slate-300 transition-colors mr-2">
            <ArrowLeft size={12} /> Markets
          </button>
          <Flame className="text-orange-400" size={18} />
          <span className="font-bold tracking-tight">Futures &amp; Commodities</span>
          <span className="text-[10px] text-slate-500 bg-surface px-2 py-0.5 rounded">10× leverage · Paper · Fully Automated</span>
          {isAutoOn && (
            <span className="text-[10px] bg-orange-500/20 text-orange-400 border border-orange-500/30 px-2 py-0.5 rounded font-bold animate-pulse">
              BOT ACTIVE
            </span>
          )}
        </div>
        <div className="flex items-center gap-4 text-sm">
          <div className="text-right">
            <p className="text-[10px] text-slate-500">Cash</p>
            <p className="font-bold font-mono">${fmt(portfolio?.cash ?? 0)}</p>
          </div>
          <div className="text-right">
            <p className="text-[10px] text-slate-500">Open P&amp;L</p>
            <p className={`font-bold font-mono ${totalPnl >= 0 ? "text-buy" : "text-sell"}`}>
              {totalPnl >= 0 ? "+" : ""}{fmt(totalPnl)}
            </p>
          </div>
          <div className="text-right">
            <p className="text-[10px] text-slate-500">Positions</p>
            <p className="font-bold">{openCount}</p>
          </div>
          <button onClick={loadCore} className="text-slate-500 hover:text-slate-300 transition-colors">
            <RefreshCw size={13} />
          </button>
        </div>
      </header>

      {/* Ticker */}
      <TickerStrip quotes={quotes} />

      {loading ? (
        <div className="flex-1 flex items-center justify-center text-slate-500">Loading market data…</div>
      ) : (
        <div className="flex-1 overflow-hidden flex">
          {/* Left: instruments */}
          <div className="w-[400px] border-r border-border overflow-y-auto p-3 shrink-0">
            <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-3">
              {quotes.length} instruments · {lastUpdate?.toLocaleTimeString()}
            </p>
            {categories.map((cat) => {
              const catQ = quotes.filter((q) => q.category === cat);
              if (!catQ.length) return null;
              return (
                <div key={cat} className="mb-4">
                  <p className={`text-[10px] font-bold uppercase tracking-wider mb-2 px-1 ${CATEGORY_COLORS[cat]?.split(" ")[0] ?? "text-slate-400"}`}>
                    {cat}
                  </p>
                  <div className="grid grid-cols-2 gap-2">
                    {catQ.map((q) => (
                      <QuoteCard
                        key={q.symbol}
                        q={q}
                        pred={predictions}
                        onSelect={setSelected}
                        selected={selected}
                      />
                    ))}
                  </div>
                </div>
              );
            })}
          </div>

          {/* Right: bot + data */}
          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            {/* Stats row */}
            <div className="grid grid-cols-4 gap-3">
              {[
                { label: "Equity",       val: `$${fmt(portfolio?.equity ?? portfolio?.cash ?? 0)}`, cls: "" },
                { label: "Margin Used",  val: `$${fmt(portfolio?.margin_used ?? 0)}`,               cls: "" },
                { label: "Win Rate",     val: perf?.closed ? `${(perf.win_rate * 100).toFixed(0)}%` : "—", cls: "" },
                { label: "Realized P&L", val: perf?.closed ? `${(perf.total_pnl ?? 0) >= 0 ? "+" : ""}$${fmt(perf.total_pnl)}` : "—",
                  cls: (perf?.total_pnl ?? 0) >= 0 ? "text-buy" : "text-sell" },
              ].map((s) => (
                <div key={s.label} className="bg-card border border-border rounded-xl p-3">
                  <p className="text-[10px] text-slate-500 mb-1">{s.label}</p>
                  <p className={`font-bold font-mono ${s.cls}`}>{s.val}</p>
                </div>
              ))}
            </div>

            {/* Instrument detail — shown on card click */}
            {selected && (
              <InstrumentDetail
                q={selected}
                pred={predictions}
                position={(portfolio?.positions ?? []).find((p) => p.symbol === selected.symbol)}
                onClose={() => setSelected(null)}
              />
            )}

            {/* Bot status */}
            <BotStatus botStatus={botStatus} />

            {/* Live opportunities */}
            <LiveOpportunities quotes={quotes} config={botStatus} openSymbols={openSymbols} />

            {/* Tabs */}
            <div>
              <div className="flex gap-1 border-b border-border mb-3">
                {[
                  { id: "positions",   label: `Positions (${openCount})` },
                  { id: "history",     label: `Trade Log (${history.length})` },
                  { id: "predictions", label: "Predictions" },
                ].map((t) => (
                  <button
                    key={t.id}
                    onClick={() => setTab(t.id)}
                    className={`px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px ${
                      tab === t.id ? "border-orange-500 text-orange-400" : "border-transparent text-slate-400 hover:text-slate-200"
                    }`}
                  >
                    {t.label}
                  </button>
                ))}
              </div>
              {tab === "positions"   && <PositionsTable portfolio={portfolio} onClose={loadCore} />}
              {tab === "history"     && <TradeLog history={history} />}
              {tab === "predictions" && <PredictionsPanel predictions={predictions} quotes={quotes} />}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
