import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { ChevronUp, ChevronDown, ChevronRight } from "lucide-react";

const api = (path) => axios.get(path).then((r) => r.data);

function SectorBar({ buy, sell, hold, total }) {
  const bPct = total ? (buy  / total) * 100 : 0;
  const sPct = total ? (sell / total) * 100 : 0;
  const hPct = total ? (hold / total) * 100 : 0;
  return (
    <div className="h-2 w-full bg-surface rounded-full overflow-hidden flex">
      <div className="bg-buy h-full"    style={{ width: `${bPct}%` }} />
      <div className="bg-slate-600 h-full" style={{ width: `${hPct}%` }} />
      <div className="bg-sell h-full"   style={{ width: `${sPct}%` }} />
    </div>
  );
}

export default function SectorPage() {
  const navigate = useNavigate();
  const [active, setActive] = useState(null);

  const { data: sectors = [], isLoading } = useQuery({
    queryKey: ["sectors"],
    queryFn: () => api("/api/universe/sectors"),
    refetchInterval: 60_000,
  });

  const { data: tickers = [] } = useQuery({
    queryKey: ["sector-tickers", active],
    queryFn: () => api(`/api/universe/sector/${encodeURIComponent(active)}/tickers?limit=50`),
    enabled: !!active,
  });

  const total = sectors.reduce((s, r) => s + (r.buy_count ?? 0) + (r.sell_count ?? 0), 0);
  const topBuy  = [...sectors].sort((a, b) => (b.buy_count  ?? 0) - (a.buy_count  ?? 0)).slice(0, 3);
  const topSell = [...sectors].sort((a, b) => (b.sell_count ?? 0) - (a.sell_count ?? 0)).slice(0, 3);

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Sector Rotation</h1>
        <p className="text-xs text-slate-500 mt-0.5">
          Signal distribution across {sectors.length} sectors · real-time from AI engine
        </p>
      </div>

      {/* Hot / Cold sectors */}
      {sectors.length > 0 && (
        <div className="grid grid-cols-2 gap-4">
          <div className="bg-buy/5 border border-buy/20 rounded-xl p-4">
            <p className="text-xs text-buy uppercase tracking-wider font-bold mb-3">▲ Bullish Sectors</p>
            {topBuy.map((s) => (
              <div key={s.sector} className="flex justify-between items-center text-sm mb-2">
                <button onClick={() => setActive(s.sector === active ? null : s.sector)}
                  className="hover:text-buy transition-colors text-left truncate">{s.sector}</button>
                <span className="text-buy font-bold ml-2">{s.buy_count} BUY</span>
              </div>
            ))}
          </div>
          <div className="bg-sell/5 border border-sell/20 rounded-xl p-4">
            <p className="text-xs text-sell uppercase tracking-wider font-bold mb-3">▼ Bearish Sectors</p>
            {topSell.map((s) => (
              <div key={s.sector} className="flex justify-between items-center text-sm mb-2">
                <button onClick={() => setActive(s.sector === active ? null : s.sector)}
                  className="hover:text-sell transition-colors text-left truncate">{s.sector}</button>
                <span className="text-sell font-bold ml-2">{s.sell_count} SELL</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Full sector table */}
      <div className="bg-card border border-border rounded-xl">
        <div className="px-4 py-3 border-b border-border">
          <p className="text-xs text-slate-500 uppercase tracking-wider">All Sectors</p>
        </div>
        {isLoading ? (
          <div className="text-center py-12 text-slate-600">Loading…</div>
        ) : (
          <div className="divide-y divide-border">
            {sectors.map((s) => {
              const sigTotal = (s.buy_count ?? 0) + (s.sell_count ?? 0) + (s.hold_count ?? 0);
              const bias = (s.buy_count ?? 0) - (s.sell_count ?? 0);
              const isOpen = active === s.sector;
              return (
                <div key={s.sector}>
                  <button
                    onClick={() => setActive(isOpen ? null : s.sector)}
                    className="w-full flex items-center gap-4 px-4 py-3 hover:bg-white/2 transition-colors text-left"
                  >
                    <div className="w-40 shrink-0 font-medium text-sm truncate">{s.sector}</div>

                    <div className="flex-1">
                      <SectorBar
                        buy={s.buy_count ?? 0}
                        sell={s.sell_count ?? 0}
                        hold={s.hold_count ?? 0}
                        total={sigTotal}
                      />
                    </div>

                    <div className="flex items-center gap-4 text-xs shrink-0">
                      <span className="text-buy w-12 text-right">▲ {s.buy_count ?? 0}</span>
                      <span className="text-slate-500 w-12 text-right">~ {s.hold_count ?? 0}</span>
                      <span className="text-sell w-12 text-right">▼ {s.sell_count ?? 0}</span>
                      <span className={`w-16 text-right font-bold ${bias > 0 ? "text-buy" : bias < 0 ? "text-sell" : "text-slate-500"}`}>
                        {bias > 0 ? `+${bias}` : bias}
                      </span>
                      <span className="text-slate-600 w-12 text-right">{s.total_tickers}</span>
                      <ChevronRight size={12} className={`text-slate-600 transition-transform ${isOpen ? "rotate-90" : ""}`} />
                    </div>
                  </button>

                  {/* Expanded: tickers in sector */}
                  {isOpen && (
                    <div className="px-4 pb-4 bg-surface/40">
                      {tickers.length === 0 ? (
                        <p className="text-xs text-slate-600 py-2">Loading tickers…</p>
                      ) : (
                        <div className="flex flex-wrap gap-2 pt-2">
                          {tickers.map((t) => (
                            <button
                              key={t.ticker}
                              onClick={() => navigate(`/stocks/stock/${t.ticker}`)}
                              className={`text-[10px] flex items-center gap-1.5 rounded-lg border px-2 py-1 transition-colors
                                ${t.signal === "BUY"  ? "border-buy/30 text-buy hover:bg-buy/10" :
                                  t.signal === "SELL" ? "border-sell/30 text-sell hover:bg-sell/10" :
                                  "border-border text-slate-400 hover:border-slate-500"}`}
                            >
                              <span className="font-mono font-bold">{t.ticker}</span>
                              {t.signal && t.signal !== "HOLD" && (
                                <span className="font-bold">{t.signal === "BUY" ? "▲" : "▼"} {Math.round((t.confidence ?? 0) * 100)}%</span>
                              )}
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}

        {/* Legend */}
        <div className="px-4 py-2 border-t border-border flex gap-6 text-[10px] text-slate-600">
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-sm bg-buy inline-block" /> BUY</span>
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-sm bg-slate-600 inline-block" /> HOLD</span>
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-sm bg-sell inline-block" /> SELL</span>
          <span className="ml-auto">Click row to expand tickers · click ticker to open detail</span>
        </div>
      </div>
    </div>
  );
}
