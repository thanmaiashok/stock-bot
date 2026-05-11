import { useOutletContext } from "react-router-dom";
import { Clock } from "lucide-react";
import { fmt } from "./FuturesShell";

function TradeLog({ history }) {
  if (!history?.length) {
    return (
      <div className="flex flex-col items-center justify-center h-64 text-slate-500 gap-2">
        <Clock size={32} className="opacity-30" />
        <p className="text-sm">No trades yet</p>
        <p className="text-xs text-slate-600">Bot will log trades here as they execute</p>
      </div>
    );
  }

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
                {new Date(t.timestamp).toLocaleString("en-US", {
                  month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
                })}
              </td>
              <td className="py-2 pr-3 font-mono text-xs">{t.symbol}</td>
              <td className="py-2 pr-3">
                <span className={`text-[10px] font-bold ${t.direction === "long" ? "text-buy" : "text-sell"}`}>
                  {t.direction?.toUpperCase()}
                </span>
              </td>
              <td className="py-2 pr-3">
                <span className={`text-[10px] px-1.5 py-0.5 rounded ${
                  t.action === "OPEN" ? "bg-slate-700 text-slate-300" : "bg-accent/20 text-accent"
                }`}>
                  {t.action}
                </span>
              </td>
              <td className="py-2 pr-3 text-right font-mono text-xs">{t.units}</td>
              <td className="py-2 pr-3 text-right font-mono text-xs">{fmt(t.price, t.price > 100 ? 2 : 4)}</td>
              <td className={`py-2 pr-3 text-right font-mono text-xs font-bold ${
                t.pnl == null ? "text-slate-500" : t.pnl >= 0 ? "text-buy" : "text-sell"
              }`}>
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

export default function FuturesHistory() {
  const { history, perf } = useOutletContext();

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="font-bold text-lg">Trade Log</h2>
        <span className="text-[10px] text-slate-500">{history.length} trade{history.length !== 1 ? "s" : ""}</span>
      </div>

      {/* Performance summary */}
      {perf?.closed > 0 && (
        <div className="grid grid-cols-4 gap-3">
          {[
            { label: "Closed Trades",  val: String(perf.closed) },
            { label: "Win Rate",       val: `${(perf.win_rate * 100).toFixed(0)}%` },
            { label: "Avg Win",        val: `$${(perf.avg_win ?? 0).toFixed(2)}`,  cls: "text-buy" },
            { label: "Avg Loss",       val: `$${(perf.avg_loss ?? 0).toFixed(2)}`, cls: "text-sell" },
          ].map((s) => (
            <div key={s.label} className="bg-card border border-border rounded-xl p-3">
              <p className="text-[10px] text-slate-500 mb-1">{s.label}</p>
              <p className={`font-bold font-mono ${s.cls ?? ""}`}>{s.val}</p>
            </div>
          ))}
        </div>
      )}

      <div className="bg-card border border-border rounded-xl p-4">
        <TradeLog history={history} />
      </div>
    </div>
  );
}
