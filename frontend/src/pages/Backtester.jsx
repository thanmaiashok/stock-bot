import { useState, useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import axios from "axios";
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, ReferenceLine,
} from "recharts";
import { FlaskConical, TrendingUp, TrendingDown, Target, AlertTriangle, Loader2, Shield, Zap, BarChart2 } from "lucide-react";

const api = (url) => axios.get(url).then(r => r.data);

function StatBox({ label, value, sub, color = "text-white", icon: Icon }) {
  return (
    <div className="bg-card border border-border rounded-xl p-4">
      <div className="flex items-center justify-between mb-1">
        <span className="text-[10px] text-slate-500 uppercase tracking-wider">{label}</span>
        {Icon && <Icon size={14} className="text-slate-600" />}
      </div>
      <p className={`text-2xl font-bold font-mono ${color}`}>{value}</p>
      {sub && <p className="text-[10px] text-slate-500 mt-0.5">{sub}</p>}
    </div>
  );
}

const DAY_OPTIONS = [30, 60, 90, 180, 365];
const DEBOUNCE_MS = 600;

export default function Backtester() {
  const [input, setInput] = useState("");
  const [ticker, setTicker] = useState("");
  const [days, setDays]     = useState(90);
  const debounceRef = useRef(null);

  // Debounce ticker input → auto-trigger
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    const t = input.trim().toUpperCase();
    if (t.length >= 1) {
      debounceRef.current = setTimeout(() => setTicker(t), DEBOUNCE_MS);
    } else {
      setTicker("");
    }
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
  }, [input]);

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["backtest", ticker, days],
    queryFn: () => api(`/api/backtest?ticker=${ticker}&days=${days}`),
    enabled: ticker.length >= 1,
    retry: false,
    staleTime: 60_000,
  });

  const ret = data?.total_return_pct ?? 0;
  const retColor = ret >= 0 ? "text-green-400" : "text-red-400";

  return (
    <div className="p-6 space-y-5 max-w-5xl">
      <div className="flex items-center gap-3">
        <FlaskConical size={22} className="text-accent" />
        <div>
          <h1 className="text-2xl font-bold">Signal Backtester</h1>
          <p className="text-slate-500 text-sm">Simulate RSI + EMA + Momentum strategy on historical closes · $10,000 start</p>
        </div>
      </div>

      {/* Controls — auto-triggers */}
      <div className="flex items-center gap-3 flex-wrap">
        <div className="relative">
          <input
            value={input}
            onChange={e => setInput(e.target.value.toUpperCase())}
            placeholder="AAPL"
            className="bg-card border border-border rounded-lg px-3 py-2 text-sm font-mono w-32 focus:outline-none focus:border-accent pr-8"
          />
          {isLoading && ticker && (
            <Loader2 size={12} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-500 animate-spin" />
          )}
        </div>

        <div className="flex items-center gap-1">
          {DAY_OPTIONS.map(d => (
            <button
              key={d}
              onClick={() => setDays(d)}
              className={`px-3 py-1.5 rounded-lg text-xs border transition-colors ${
                days === d
                  ? "bg-accent/20 text-accent border-accent/30"
                  : "text-slate-500 border-transparent hover:border-border hover:text-slate-300"
              }`}
            >{d}d</button>
          ))}
        </div>

        <div className="flex gap-3 text-[10px] text-slate-600 ml-2">
          <span>Entry: score ≥ 2 → BUY</span>
          <span>Exit: score ≤ −2 → SELL</span>
          <span>No slippage</span>
        </div>
      </div>

      {isError && (
        <div className="flex items-center gap-2 text-red-400 text-sm bg-red-500/10 border border-red-500/20 rounded-xl px-4 py-3">
          <AlertTriangle size={14} />
          {error?.response?.data?.detail ?? "No price data found. Try a different ticker or wait for history to build."}
        </div>
      )}

      {data && (
        <>
          {/* Primary stats row */}
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
            <StatBox
              label="Total Return"
              value={`${ret >= 0 ? "+" : ""}${ret.toFixed(1)}%`}
              color={retColor}
              icon={ret >= 0 ? TrendingUp : TrendingDown}
            />
            <StatBox
              label="Final Value"
              value={`$${data.final_value.toLocaleString()}`}
              sub="started $10,000"
            />
            <StatBox
              label="Win Rate"
              value={`${typeof data.win_rate === "number" ? (data.win_rate <= 1 ? (data.win_rate * 100).toFixed(0) : data.win_rate.toFixed(0)) : 0}%`}
              color={data.win_rate >= 0.5 || data.win_rate >= 50 ? "text-green-400" : "text-red-400"}
              icon={Target}
            />
            <StatBox
              label="Trades"
              value={data.total_trades}
              sub={`W:${data.num_wins ?? "?"} / L:${data.num_losses ?? "?"}`}
            />
            <StatBox
              label="Max Drawdown"
              value={`${Math.abs(data.max_drawdown_pct ?? 0).toFixed(1)}%`}
              color={Math.abs(data.max_drawdown_pct ?? 0) > 20 ? "text-red-400" : "text-yellow-400"}
              icon={AlertTriangle}
            />
            <StatBox label="Period" value={`${data.days}d`} sub={data.ticker} />
          </div>

          {/* QuantStats-inspired risk metrics */}
          <div className="bg-card border border-border rounded-xl p-4 space-y-3">
            <div className="flex items-center gap-2 mb-1">
              <BarChart2 size={14} className="text-accent" />
              <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Risk-Adjusted Performance</span>
              <span className="text-[9px] text-slate-600 ml-1">inspired by QuantStats</span>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
              <StatBox
                label="Sharpe"
                value={data.sharpe != null ? data.sharpe.toFixed(2) : "—"}
                color={data.sharpe >= 1 ? "text-green-400" : data.sharpe >= 0 ? "text-yellow-400" : "text-red-400"}
                icon={Zap}
                sub="risk-adjusted return"
              />
              <StatBox
                label="Sortino"
                value={data.sortino != null ? (data.sortino === Infinity ? "∞" : data.sortino.toFixed(2)) : "—"}
                color={data.sortino >= 1 ? "text-green-400" : "text-yellow-400"}
                sub="downside-adj"
              />
              <StatBox
                label="Calmar"
                value={data.calmar != null ? data.calmar.toFixed(2) : "—"}
                color={data.calmar >= 0.5 ? "text-green-400" : "text-yellow-400"}
                sub="CAGR / MaxDD"
              />
              <StatBox
                label="Profit Factor"
                value={data.profit_factor != null ? data.profit_factor.toFixed(2) : "—"}
                color={data.profit_factor >= 1.5 ? "text-green-400" : data.profit_factor >= 1.0 ? "text-yellow-400" : "text-red-400"}
                sub="gross profit / loss"
              />
              <StatBox
                label="VaR 95%"
                value={data.var_95_pct != null ? `${data.var_95_pct.toFixed(2)}%` : "—"}
                color="text-orange-400"
                icon={Shield}
                sub="daily worst 5%"
              />
              <StatBox
                label="Ann. Volatility"
                value={data.volatility_ann_pct != null ? `${data.volatility_ann_pct.toFixed(1)}%` : "—"}
                sub="annualised σ"
              />
            </div>
            {data.avg_win_loss_ratio != null && (
              <div className="flex flex-wrap gap-4 pt-1 text-xs text-slate-500 border-t border-border">
                <span>Avg W/L Ratio: <span className="text-slate-300 font-mono">{data.avg_win_loss_ratio.toFixed(2)}x</span></span>
                <span>Avg Trade: <span className="text-slate-300 font-mono">{data.avg_trade_pct >= 0 ? "+" : ""}{(data.avg_trade_pct ?? 0).toFixed(2)}%</span></span>
                {data.stats?.omega_ratio != null && (
                  <span>Omega: <span className="text-slate-300 font-mono">{data.stats.omega_ratio.toFixed(2)}</span></span>
                )}
                {data.stats?.cvar_95_pct != null && (
                  <span>CVaR 95%: <span className="text-slate-300 font-mono">{data.stats.cvar_95_pct.toFixed(2)}%</span></span>
                )}
              </div>
            )}
          </div>

          <div className="bg-card border border-border rounded-xl p-4">
            <h2 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">
              Equity Curve — {data.ticker}
            </h2>
            <ResponsiveContainer width="100%" height={240}>
              <LineChart data={data.equity_curve} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                <XAxis dataKey="date" tick={{ fontSize: 9, fill: "#475569" }} tickLine={false}
                  tickFormatter={v => v?.slice(5)} interval="preserveStartEnd" />
                <YAxis tick={{ fontSize: 9, fill: "#475569" }} tickLine={false} axisLine={false}
                  tickFormatter={v => `$${(v/1000).toFixed(1)}k`} domain={["auto", "auto"]} />
                <Tooltip
                  contentStyle={{ background: "#0f1117", border: "1px solid #1e293b", borderRadius: 8 }}
                  labelStyle={{ color: "#94a3b8", fontSize: 10 }}
                  formatter={v => [`$${v.toLocaleString()}`, "Portfolio"]}
                />
                <ReferenceLine y={10000} stroke="#475569" strokeDasharray="4 2" />
                <Line type="monotone" dataKey="value" dot={false} strokeWidth={2}
                  stroke={ret >= 0 ? "#22c55e" : "#ef4444"} />
              </LineChart>
            </ResponsiveContainer>
          </div>

          {data.recent_trades?.length > 0 && (
            <div className="bg-card border border-border rounded-xl p-4">
              <h2 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">
                Recent Trades (last {data.recent_trades.length})
              </h2>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-border text-slate-500">
                      <th className="text-left pb-2 font-normal">#</th>
                      <th className="text-right pb-2 font-normal">Entry</th>
                      <th className="text-right pb-2 font-normal">Exit</th>
                      <th className="text-right pb-2 font-normal">P&L</th>
                      <th className="text-right pb-2 font-normal">Result</th>
                    </tr>
                  </thead>
                  <tbody>
                    {[...data.recent_trades].reverse().map((t, i) => (
                      <tr key={i} className="border-b border-white/5">
                        <td className="py-1.5 text-slate-600">{data.recent_trades.length - i}</td>
                        <td className="py-1.5 text-right font-mono">${t.entry}</td>
                        <td className="py-1.5 text-right font-mono">${t.exit}</td>
                        <td className={`py-1.5 text-right font-mono font-bold ${t.win ? "text-green-400" : "text-red-400"}`}>
                          {t.pnl_pct >= 0 ? "+" : ""}{t.pnl_pct}%
                        </td>
                        <td className="py-1.5 text-right">
                          <span className={`px-1.5 py-0.5 rounded-full text-[9px] font-bold ${
                            t.win ? "bg-green-500/20 text-green-400" : "bg-red-500/20 text-red-400"
                          }`}>
                            {t.win ? "WIN" : "LOSS"}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}

      {!data && !isLoading && !isError && (
        <div className="text-center py-16 text-slate-600">
          <FlaskConical size={40} className="mx-auto mb-3 opacity-30" />
          <p>Type a ticker above — backtest runs automatically</p>
        </div>
      )}
    </div>
  );
}
