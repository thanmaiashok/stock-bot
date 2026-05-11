import { useState, useEffect, useCallback } from "react";
import { Outlet, NavLink, useNavigate } from "react-router-dom";
import axios from "axios";
import Breadcrumb from "../components/Breadcrumb";
import { ArrowLeft, Flame, BarChart2, Layers, Clock, RefreshCw, Bot, Brain, GitBranch } from "lucide-react";

export const api = (path) => axios.get(`/api${path}`).then((r) => r.data);
export const REFRESH_MS   = 8000;
export const PRED_REFRESH = 60_000;

export function fmt(n, dec = 2) {
  if (n == null) return "—";
  return Number(n).toLocaleString("en-US", { minimumFractionDigits: dec, maximumFractionDigits: dec });
}
export function pct(n) {
  if (n == null) return "—";
  const v = Number(n);
  return `${v >= 0 ? "+" : ""}${v.toFixed(2)}%`;
}
export const CATEGORY_COLORS = {
  Energy:      "text-orange-400 bg-orange-400/10 border-orange-400/20",
  Metals:      "text-yellow-400 bg-yellow-400/10 border-yellow-400/20",
  Agriculture: "text-green-400  bg-green-400/10  border-green-400/20",
  Indices:     "text-blue-400   bg-blue-400/10   border-blue-400/20",
  Crypto:      "text-purple-400 bg-purple-400/10 border-purple-400/20",
};
export const SIG_COLORS = {
  LONG:    "bg-green-500/20 text-green-400 border border-green-500/30",
  SHORT:   "bg-red-500/20   text-red-400   border border-red-500/30",
  NEUTRAL: "bg-slate-700/60 text-slate-500",
};

const navItems = [
  { to: "",             icon: BarChart2,  label: "Markets",   end: true },
  { to: "ai",           icon: Brain,      label: "AI" },
  { to: "positions",    icon: Layers,     label: "Positions" },
  { to: "history",      icon: Clock,      label: "Trade Log" },
  { to: "analytics",    icon: GitBranch,  label: "Analytics" },
];

export default function FuturesShell() {
  const navigate = useNavigate();

  const [quotes,      setQuotes]      = useState([]);
  const [portfolio,   setPortfolio]   = useState(null);
  const [history,     setHistory]     = useState([]);
  const [perf,        setPerf]        = useState(null);
  const [predictions, setPredictions] = useState({});
  const [botStatus,   setBotStatus]   = useState(null);
  const [loading,     setLoading]     = useState(true);
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

  const totalPnl  = portfolio?.total_pnl ?? 0;
  const openCount = portfolio?.positions?.length ?? 0;

  return (
    <div className="flex h-screen bg-surface overflow-hidden">
      <aside className="w-56 bg-card border-r border-border flex flex-col shrink-0">
        <div className="p-4 border-b border-border">
          <button
            onClick={() => navigate("/")}
            className="flex items-center gap-1 text-xs text-slate-600 hover:text-slate-300 mb-3 transition-colors"
          >
            <ArrowLeft size={12} /> Markets
          </button>
          <div className="flex items-center gap-2">
            <Flame className="text-orange-400" size={22} />
            <span className="font-bold text-lg tracking-tight">Futures</span>
          </div>
          <p className="text-xs text-slate-500 mt-0.5">10× leverage · Automated</p>
        </div>

        <div className="mx-3 mt-3 flex items-center gap-2 bg-orange-500/10 border border-orange-500/20 rounded-lg px-3 py-2">
          <Bot size={12} className="text-orange-400" />
          <div className="flex-1 min-w-0">
            <p className="text-[10px] font-bold text-orange-400">BOT ACTIVE</p>
            <p className="text-[9px] text-slate-500 truncate">Scanning every 30s</p>
          </div>
          <span className="w-1.5 h-1.5 rounded-full bg-orange-400 animate-pulse shrink-0" />
        </div>

        <nav className="flex-1 p-3 space-y-1 mt-2">
          {navItems.map(({ to, icon: Icon, label, end }) => (
            <NavLink
              key={label}
              to={to}
              end={end}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
                  isActive
                    ? "bg-orange-500/20 text-orange-400"
                    : "text-slate-400 hover:text-white hover:bg-white/5"
                }`
              }
            >
              <Icon size={16} />
              {label}
              {label === "Positions" && openCount > 0 && (
                <span className="ml-auto text-[10px] bg-orange-500/20 text-orange-400 px-1.5 py-0.5 rounded-full font-bold">
                  {openCount}
                </span>
              )}
            </NavLink>
          ))}
        </nav>

        <div className="p-3 border-t border-border space-y-1">
          <div className="flex justify-between text-[10px]">
            <span className="text-slate-600">Cash</span>
            <span className="font-mono text-slate-400">${fmt(portfolio?.cash ?? 0)}</span>
          </div>
          <div className="flex justify-between text-[10px]">
            <span className="text-slate-600">Open P&L</span>
            <span className={`font-mono font-bold ${totalPnl >= 0 ? "text-buy" : "text-sell"}`}>
              {totalPnl >= 0 ? "+" : ""}{fmt(totalPnl)}
            </span>
          </div>
          <button
            onClick={loadCore}
            className="flex items-center gap-1 text-[10px] text-slate-600 hover:text-slate-400 mt-1 transition-colors"
          >
            <RefreshCw size={10} /> {lastUpdate ? lastUpdate.toLocaleTimeString() : "loading…"}
          </button>
          <p className="text-[9px] text-slate-700 mt-1">Paper trading only</p>
        </div>
      </aside>

      <main className="flex-1 overflow-hidden flex flex-col">
        <Breadcrumb />
        {loading ? (
          <div className="flex-1 flex items-center justify-center text-slate-500">Loading market data…</div>
        ) : (
          <div className="flex-1 min-h-0 overflow-y-auto">
            <Outlet context={{ quotes, portfolio, history, perf, predictions, botStatus, loadCore, lastUpdate }} />
          </div>
        )}
      </main>
    </div>
  );
}
