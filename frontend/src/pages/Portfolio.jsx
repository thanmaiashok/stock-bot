import { useQuery } from "@tanstack/react-query";
import axios from "axios";
import PortfolioTable from "../components/PortfolioTable";
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, ReferenceLine } from "recharts";
import clsx from "clsx";

const api = (path) => axios.get(path).then((r) => r.data);

function StatBadge({ label, value, color = "text-white" }) {
  return (
    <div className="bg-card border border-border rounded-xl p-4 text-center">
      <p className="text-xs text-slate-500 mb-1">{label}</p>
      <p className={`text-xl font-bold ${color}`}>{value}</p>
    </div>
  );
}

export default function Portfolio() {
  const { data: portfolio }       = useQuery({ queryKey: ["portfolio"],       queryFn: () => api("/api/portfolio"), refetchInterval: 30000 });
  const { data: history = [] }    = useQuery({ queryKey: ["trade-history"],   queryFn: () => api("/api/portfolio/history?limit=200") });
  const { data: stats }           = useQuery({ queryKey: ["portfolio-stats"], queryFn: () => api("/api/portfolio/stats") });
  const { data: equityCurve = [] }= useQuery({ queryKey: ["equity-curve"],   queryFn: () => api("/api/portfolio/equity-curve") });

  const pnl = portfolio?.unrealized_pnl ?? 0;

  // Cumulative P&L line from trade history
  let cumulative = 0;
  const pnlData = history
    .filter((t) => t.action === "SELL")
    .map((t) => {
      cumulative += t.pnl || 0;
      return { date: t.timestamp?.slice(0, 10), cumPnl: Math.round(cumulative * 100) / 100 };
    });

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-2xl font-bold">Portfolio</h1>

      {/* Summary stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatBadge label="Total Value" value={portfolio ? `$${portfolio.total_value?.toLocaleString()}` : "—"} />
        <StatBadge label="Cash" value={portfolio ? `$${portfolio.cash?.toLocaleString()}` : "—"} color="text-slate-300" />
        <StatBadge
          label="Unrealized P&L"
          value={portfolio ? `${pnl >= 0 ? "+" : ""}$${pnl?.toFixed(2)}` : "—"}
          color={pnl >= 0 ? "text-buy" : "text-sell"}
        />
        <StatBadge label="Open Positions" value={portfolio?.positions?.length ?? "—"} color="text-accent" />
      </div>

      {/* Performance stats */}
      {stats && stats.closed_positions > 0 && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatBadge label="Win Rate" value={`${Math.round(stats.win_rate * 100)}%`} color={stats.win_rate > 0.5 ? "text-buy" : "text-sell"} />
          <StatBadge label="Realized P&L" value={`$${stats.total_realized_pnl?.toFixed(2)}`} color={stats.total_realized_pnl >= 0 ? "text-buy" : "text-sell"} />
          <StatBadge label="Sharpe Ratio" value={stats.sharpe_ratio?.toFixed(2)} />
          <StatBadge label="Best Trade" value={`$${stats.best_trade?.toFixed(2)}`} color="text-buy" />
        </div>
      )}

      {/* Equity curve */}
      {equityCurve.length > 1 && (
        <div className="bg-card border border-border rounded-xl p-4">
          <p className="text-xs text-slate-500 uppercase tracking-wider mb-3">Equity Curve</p>
          <ResponsiveContainer width="100%" height={200}>
            <AreaChart data={equityCurve}>
              <defs>
                <linearGradient id="eqGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#6366f1" stopOpacity={0.25} />
                  <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#2a2d3e" vertical={false} />
              <XAxis dataKey="date" tick={{ fill: "#64748b", fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: "#64748b", fontSize: 11 }} axisLine={false} tickLine={false} tickFormatter={(v) => `$${v.toLocaleString()}`} domain={["auto", "auto"]} />
              <Tooltip contentStyle={{ background: "#1a1d27", border: "1px solid #2a2d3e", fontSize: 11 }} formatter={(v) => [`$${v.toLocaleString()}`, "Equity"]} />
              <ReferenceLine y={10000} stroke="#334155" strokeDasharray="4 2" label={{ value: "Start $10k", fill: "#475569", fontSize: 10 }} />
              <Area type="monotone" dataKey="equity" stroke="#6366f1" fill="url(#eqGrad)" strokeWidth={2} dot={false} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* P&L chart */}
      {pnlData.length > 0 && (
        <div className="bg-card border border-border rounded-xl p-4">
          <p className="text-xs text-slate-500 uppercase tracking-wider mb-3">Cumulative Realized P&L</p>
          <ResponsiveContainer width="100%" height={160}>
            <AreaChart data={pnlData}>
              <defs>
                <linearGradient id="pnlGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#22c55e" stopOpacity={0.2} />
                  <stop offset="95%" stopColor="#22c55e" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#2a2d3e" vertical={false} />
              <XAxis dataKey="date" tick={{ fill: "#64748b", fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: "#64748b", fontSize: 11 }} axisLine={false} tickLine={false} tickFormatter={(v) => `$${v}`} />
              <Tooltip contentStyle={{ background: "#1a1d27", border: "1px solid #2a2d3e", fontSize: 11 }} />
              <ReferenceLine y={0} stroke="#334155" strokeDasharray="4 2" />
              <Area type="monotone" dataKey="cumPnl" stroke="#22c55e" fill="url(#pnlGrad)" strokeWidth={2} dot={false} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Open positions */}
      <div className="bg-card border border-border rounded-xl p-4">
        <p className="text-xs text-slate-500 uppercase tracking-wider mb-4">Open Positions</p>
        <PortfolioTable positions={portfolio?.positions ?? []} />
      </div>

      {/* Trade history */}
      <div className="bg-card border border-border rounded-xl p-4">
        <p className="text-xs text-slate-500 uppercase tracking-wider mb-4">Trade History</p>
        {history.length === 0 ? (
          <p className="text-sm text-slate-600">No trades yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-xs text-slate-500 uppercase tracking-wider">
                  <th className="pb-2 pr-4">Ticker</th>
                  <th className="pb-2 pr-4">Action</th>
                  <th className="pb-2 pr-4 text-right">Qty</th>
                  <th className="pb-2 pr-4 text-right">Price</th>
                  <th className="pb-2 pr-4 text-right">P&L</th>
                  <th className="pb-2 text-right">Time</th>
                </tr>
              </thead>
              <tbody>
                {history.map((t, i) => (
                  <tr key={i} className="border-b border-border/30 hover:bg-white/3">
                    <td className="py-2 pr-4 font-medium">{t.ticker}</td>
                    <td className={clsx("py-2 pr-4 text-xs font-bold", t.action === "BUY" ? "text-buy" : "text-sell")}>
                      {t.action}
                    </td>
                    <td className="py-2 pr-4 text-right text-slate-400">{t.quantity?.toFixed(4)}</td>
                    <td className="py-2 pr-4 text-right text-slate-400">${t.price?.toFixed(2)}</td>
                    <td className={clsx("py-2 pr-4 text-right font-medium", (t.pnl || 0) >= 0 ? "text-buy" : "text-sell")}>
                      {t.pnl ? `${t.pnl >= 0 ? "+" : ""}$${t.pnl.toFixed(2)}` : "—"}
                    </td>
                    <td className="py-2 text-right text-xs text-slate-500">{t.timestamp?.slice(0, 16)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
