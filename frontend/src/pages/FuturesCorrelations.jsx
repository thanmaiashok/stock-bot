import { useQuery } from "@tanstack/react-query";
import { useOutletContext } from "react-router-dom";
import axios from "axios";

const api = (path) => axios.get(path).then((r) => r.data);

function corrColor(v) {
  if (v == null) return "#1e293b";
  if (v >= 0) {
    const g = Math.round(v * 255);
    return `rgb(0,${g},0)`;
  } else {
    const r = Math.round(-v * 255);
    return `rgb(${r},0,0)`;
  }
}

function corrTextColor(v) {
  if (v == null) return "#475569";
  return Math.abs(v) > 0.5 ? "#fff" : "#94a3b8";
}

export default function FuturesCorrelations() {
  const { quotes } = useOutletContext();

  const { data, isLoading } = useQuery({
    queryKey: ["futures-correlations"],
    queryFn: () => api("/api/futures/correlations"),
    staleTime: 300_000,  // 5 min — heavy computation
    refetchInterval: 600_000,
  });

  const { data: equityCurve = [] } = useQuery({
    queryKey: ["futures-equity-curve"],
    queryFn: () => api("/api/futures/equity-curve"),
  });

  const syms   = data?.symbols ?? [];
  const names  = data?.names   ?? {};
  const matrix = data?.matrix  ?? [];

  const shortName = (sym) => names[sym]?.split(" ")[0] ?? sym.replace("=F", "").replace("-USD", "");

  // Equity curve min/max for chart scale
  const equities = equityCurve.map((p) => p.equity).filter(Boolean);
  const minEq = equities.length ? Math.min(...equities) : 0;
  const maxEq = equities.length ? Math.max(...equities) : 10000;
  const eqRange = maxEq - minEq || 1;

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Futures Correlations</h1>
        <p className="text-xs text-slate-500 mt-0.5">
          Pearson correlation · 10d hourly closes · green = positive · red = negative
        </p>
      </div>

      {/* Equity curve */}
      {equityCurve.length > 1 && (
        <div className="bg-card border border-border rounded-xl p-4">
          <p className="text-xs text-slate-500 uppercase tracking-wider mb-3">Futures Account Equity Curve</p>
          <div className="relative h-32">
            <svg className="w-full h-full" viewBox={`0 0 800 120`} preserveAspectRatio="none">
              <defs>
                <linearGradient id="feqGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#f97316" stopOpacity={0.3} />
                  <stop offset="100%" stopColor="#f97316" stopOpacity={0} />
                </linearGradient>
              </defs>
              {/* Fill area */}
              <path
                d={equityCurve.map((p, i) => {
                  const x = (i / (equityCurve.length - 1)) * 800;
                  const y = 120 - ((p.equity - minEq) / eqRange) * 110 - 5;
                  return `${i === 0 ? "M" : "L"}${x},${y}`;
                }).join(" ") + ` L800,115 L0,115 Z`}
                fill="url(#feqGrad)"
              />
              {/* Line */}
              <polyline
                points={equityCurve.map((p, i) => {
                  const x = (i / (equityCurve.length - 1)) * 800;
                  const y = 120 - ((p.equity - minEq) / eqRange) * 110 - 5;
                  return `${x},${y}`;
                }).join(" ")}
                fill="none" stroke="#f97316" strokeWidth="2"
              />
              {/* Start line */}
              <line x1="0" y1={120 - ((10000 - minEq) / eqRange) * 110 - 5}
                    x2="800" y2={120 - ((10000 - minEq) / eqRange) * 110 - 5}
                    stroke="#334155" strokeDasharray="4,3" strokeWidth="1" />
            </svg>
            <div className="absolute bottom-0 left-0 right-0 flex justify-between text-[9px] text-slate-600 mt-1">
              <span>${(minEq).toLocaleString()}</span>
              <span>Start $10,000</span>
              <span>${(maxEq).toLocaleString()}</span>
            </div>
          </div>
        </div>
      )}

      {/* Correlation heatmap */}
      <div className="bg-card border border-border rounded-xl p-4">
        <p className="text-xs text-slate-500 uppercase tracking-wider mb-4">Correlation Heatmap</p>
        {isLoading ? (
          <div className="text-center py-16 text-slate-600">Computing correlations from 10d hourly data…</div>
        ) : syms.length === 0 ? (
          <div className="text-center py-16 text-slate-600">No data available</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="text-[10px] border-collapse">
              <thead>
                <tr>
                  <th className="w-20 pr-2" />
                  {syms.map((sym) => (
                    <th key={sym} className="text-center pb-2 px-0.5">
                      <div className="text-slate-400 font-bold" style={{ writingMode: "vertical-rl", transform: "rotate(180deg)", height: 60 }}>
                        {shortName(sym)}
                      </div>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {syms.map((rowSym, i) => (
                  <tr key={rowSym}>
                    <td className="pr-2 text-right text-slate-400 font-bold whitespace-nowrap py-0.5">
                      {shortName(rowSym)}
                    </td>
                    {(matrix[i] ?? []).map((val, j) => (
                      <td key={j} className="p-0.5">
                        <div
                          style={{
                            background: corrColor(val),
                            color: corrTextColor(val),
                            width: 38, height: 28,
                            display: "flex", alignItems: "center", justifyContent: "center",
                            borderRadius: 4,
                            fontWeight: i === j ? "900" : "600",
                          }}
                        >
                          {val != null ? (i === j ? "—" : val.toFixed(2)) : "·"}
                        </div>
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Color scale legend */}
        <div className="flex items-center gap-3 mt-4">
          <span className="text-[10px] text-slate-600">−1.00</span>
          <div className="flex h-2 flex-1 rounded-full overflow-hidden">
            {Array.from({ length: 20 }, (_, i) => {
              const v = -1 + i * 0.1;
              return <div key={i} style={{ flex: 1, background: corrColor(v) }} />;
            })}
          </div>
          <span className="text-[10px] text-slate-600">+1.00</span>
        </div>
        <p className="text-[10px] text-slate-700 mt-1">Refreshes every 10 min · computed from yfinance 1h candles</p>
      </div>

      {/* Strongest correlations */}
      {syms.length > 0 && (
        <div className="grid grid-cols-2 gap-4">
          {[
            { label: "Most Correlated Pairs", filter: (v) => v > 0.7, cls: "text-buy", border: "border-buy/20" },
            { label: "Most Inversely Correlated", filter: (v) => v < -0.5, cls: "text-sell", border: "border-sell/20" },
          ].map(({ label, filter, cls, border }) => {
            const pairs = [];
            syms.forEach((a, i) => {
              syms.forEach((b, j) => {
                if (j <= i) return;
                const v = matrix[i]?.[j];
                if (v != null && filter(v)) {
                  pairs.push({ a, b, v });
                }
              });
            });
            pairs.sort((x, y) => Math.abs(y.v) - Math.abs(x.v));
            return (
              <div key={label} className={`bg-card border ${border} rounded-xl p-4`}>
                <p className={`text-xs ${cls} font-bold uppercase tracking-wider mb-3`}>{label}</p>
                {pairs.length === 0 ? (
                  <p className="text-xs text-slate-600">None detected</p>
                ) : (
                  <div className="space-y-2">
                    {pairs.slice(0, 6).map(({ a, b, v }) => (
                      <div key={`${a}-${b}`} className="flex items-center justify-between text-xs">
                        <span>
                          <span className="font-mono font-bold text-slate-300">{shortName(a)}</span>
                          <span className="text-slate-600 mx-1">↔</span>
                          <span className="font-mono font-bold text-slate-300">{shortName(b)}</span>
                        </span>
                        <div className="flex items-center gap-2">
                          <div className="w-20 h-1.5 bg-surface rounded-full overflow-hidden">
                            <div
                              style={{ width: `${Math.abs(v) * 100}%`, background: v > 0 ? "#22c55e" : "#ef4444" }}
                              className="h-full rounded-full"
                            />
                          </div>
                          <span className={`font-bold w-10 text-right ${cls}`}>{v.toFixed(2)}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
