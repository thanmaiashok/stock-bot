import { useOutletContext } from "react-router-dom";
import { TrendingUp } from "lucide-react";
import { fmt, pct } from "./FuturesShell";

function PredictionsPanel({ predictions, quotes }) {
  if (!predictions || !Object.keys(predictions).length) {
    return (
      <div className="flex flex-col items-center justify-center h-64 text-slate-500 gap-2">
        <TrendingUp size={32} className="opacity-30" />
        <p className="text-sm">Loading predictions…</p>
        <p className="text-xs text-slate-600">First run takes ~30s (linear regression on 10d hourly data)</p>
      </div>
    );
  }

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
                <td className="py-2 pr-3 text-right font-mono">
                  {fmt(p.current, p.current > 100 ? 2 : 4)}
                </td>
                <td className={`py-2 pr-3 text-right font-mono font-semibold ${p.change_1h >= 0 ? "text-buy" : "text-sell"}`}>
                  {fmt(p.pred_1h, p.pred_1h > 100 ? 2 : 4)}
                  <span className="text-[10px] ml-1 opacity-70">({pct(p.change_1h)})</span>
                </td>
                <td className={`py-2 pr-3 text-right font-mono text-xs ${p.change_4h >= 0 ? "text-buy" : "text-sell"}`}>
                  {pct(p.change_4h)}
                </td>
                <td className={`py-2 pr-3 text-right font-mono text-xs ${p.change_1d >= 0 ? "text-buy" : "text-sell"}`}>
                  {pct(p.change_1d)}
                </td>
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
      <p className="text-[10px] text-slate-600 mt-3">
        Linear regression on 10d hourly closes · R² = fit quality · refreshes every 15 min
      </p>
    </div>
  );
}

export default function FuturesPredictions() {
  const { predictions, quotes } = useOutletContext();

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="font-bold text-lg">Price Predictions</h2>
        <span className="text-[10px] text-slate-500">{Object.keys(predictions).length} instruments · 15 min cache</span>
      </div>

      <div className="bg-card border border-border rounded-xl p-4">
        <PredictionsPanel predictions={predictions} quotes={quotes} />
      </div>
    </div>
  );
}
