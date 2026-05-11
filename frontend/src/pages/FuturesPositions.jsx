import { useState } from "react";
import { useOutletContext } from "react-router-dom";
import axios from "axios";
import { X, Layers } from "lucide-react";
import { fmt } from "./FuturesShell";

function PositionsTable({ portfolio, onClose }) {
  const [closing, setClosing] = useState(null);

  async function handleClose(symbol) {
    setClosing(symbol);
    try {
      await axios.delete(`/api/futures/position/${symbol}`);
      onClose();
    } catch (err) {
      alert(err.response?.data?.detail || "Close failed");
    } finally {
      setClosing(null);
    }
  }

  if (!portfolio?.positions?.length) {
    return (
      <div className="flex flex-col items-center justify-center h-64 text-slate-500 gap-2">
        <Layers size={32} className="opacity-30" />
        <p className="text-sm">Bot has no open positions</p>
        <p className="text-xs text-slate-600">Auto-trader will open when signals fire</p>
      </div>
    );
  }

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
                <span className={`text-xs font-bold px-1.5 py-0.5 rounded ${
                  pos.direction === "long" ? "bg-buy/20 text-buy" : "bg-sell/20 text-sell"
                }`}>
                  {pos.direction.toUpperCase()}
                </span>
              </td>
              <td className="py-2 pr-3 text-right font-mono text-slate-400">
                {fmt(pos.entry_price, pos.entry_price > 100 ? 2 : 4)}
              </td>
              <td className="py-2 pr-3 text-right font-mono">
                {fmt(pos.current_price, pos.current_price > 100 ? 2 : 4)}
              </td>
              <td className={`py-2 pr-3 text-right font-mono font-bold ${pos.pnl >= 0 ? "text-buy" : "text-sell"}`}>
                {pos.pnl >= 0 ? "+" : ""}{fmt(pos.pnl)}
                <span className="text-[10px] ml-1 opacity-60">
                  ({pos.pnl_pct >= 0 ? "+" : ""}{pos.pnl_pct?.toFixed(1)}%)
                </span>
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

export default function FuturesPositions() {
  const { portfolio, perf, loadCore } = useOutletContext();
  const totalPnl   = portfolio?.total_pnl ?? 0;
  const openCount  = portfolio?.positions?.length ?? 0;

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="font-bold text-lg">Open Positions</h2>
        <span className="text-[10px] text-slate-500">{openCount} position{openCount !== 1 ? "s" : ""} open</span>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-4 gap-3">
        {[
          { label: "Cash",         val: `$${fmt(portfolio?.cash ?? 0)}` },
          { label: "Margin Used",  val: `$${fmt(portfolio?.margin_used ?? 0)}` },
          { label: "Open P&L",
            val: `${totalPnl >= 0 ? "+" : ""}$${fmt(totalPnl)}`,
            cls: totalPnl >= 0 ? "text-buy" : "text-sell" },
          { label: "Realized P&L",
            val: perf?.closed ? `${(perf.total_pnl ?? 0) >= 0 ? "+" : ""}$${fmt(perf.total_pnl)}` : "—",
            cls: (perf?.total_pnl ?? 0) >= 0 ? "text-buy" : "text-sell" },
        ].map((s) => (
          <div key={s.label} className="bg-card border border-border rounded-xl p-3">
            <p className="text-[10px] text-slate-500 mb-1">{s.label}</p>
            <p className={`font-bold font-mono ${s.cls ?? ""}`}>{s.val}</p>
          </div>
        ))}
      </div>

      <div className="bg-card border border-border rounded-xl p-4">
        <PositionsTable portfolio={portfolio} onClose={loadCore} />
      </div>
    </div>
  );
}
