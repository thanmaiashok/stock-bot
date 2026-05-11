import { useNavigate } from "react-router-dom";
import clsx from "clsx";

export default function PortfolioTable({ positions = [] }) {
  const nav = useNavigate();

  if (!positions.length) {
    return (
      <div className="text-center py-12 text-slate-500 text-sm">
        No open positions. Signals with confidence &gt;70% will trigger buys.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border text-left text-slate-500 text-xs uppercase tracking-wider">
            <th className="pb-3 pr-4">Ticker</th>
            <th className="pb-3 pr-4 text-right">Qty</th>
            <th className="pb-3 pr-4 text-right">Avg Entry</th>
            <th className="pb-3 pr-4 text-right">Current</th>
            <th className="pb-3 pr-4 text-right">Mkt Value</th>
            <th className="pb-3 pr-4 text-right">Unreal. P&L</th>
            <th className="pb-3 pr-4 text-right">Stop Loss</th>
            <th className="pb-3 text-right">Take Profit</th>
          </tr>
        </thead>
        <tbody>
          {positions.map((pos) => (
            <tr
              key={pos.ticker}
              onClick={() => nav(`/stocks/stock/${pos.ticker}`)}
              className="border-b border-border/50 hover:bg-white/3 cursor-pointer transition-colors"
            >
              <td className="py-3 pr-4 font-medium text-white">{pos.ticker}</td>
              <td className="py-3 pr-4 text-right text-slate-300">{pos.quantity?.toFixed(4)}</td>
              <td className="py-3 pr-4 text-right text-slate-300">${pos.avg_entry?.toFixed(2)}</td>
              <td className="py-3 pr-4 text-right text-slate-300">${pos.current_price?.toFixed(2)}</td>
              <td className="py-3 pr-4 text-right text-slate-300">${pos.market_value?.toFixed(2)}</td>
              <td className={clsx("py-3 pr-4 text-right font-medium",
                pos.unrealized_pnl >= 0 ? "text-buy" : "text-sell")}>
                {pos.unrealized_pnl >= 0 ? "+" : ""}${pos.unrealized_pnl?.toFixed(2)}
                <span className="text-xs ml-1 opacity-70">
                  ({pos.unrealized_pct >= 0 ? "+" : ""}{pos.unrealized_pct?.toFixed(1)}%)
                </span>
              </td>
              <td className="py-3 pr-4 text-right text-sell/80 text-xs">${pos.stop_loss?.toFixed(2)}</td>
              <td className="py-3 text-right text-buy/80 text-xs">${pos.take_profit?.toFixed(2)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
