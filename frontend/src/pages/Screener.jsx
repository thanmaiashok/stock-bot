import { useState, useCallback } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import clsx from "clsx";
import { Search } from "lucide-react";

const SIG_COLOR = { BUY: "text-buy", SELL: "text-sell", HOLD: "text-hold" };

export default function Screener() {
  const nav = useNavigate();
  const [search, setSearch] = useState("");
  const [exchange, setExchange] = useState("");
  const [tier, setTier] = useState("");
  const [signal, setSignal] = useState("");
  const [minVol, setMinVol] = useState("");

  const params = new URLSearchParams();
  if (search) params.set("search", search);
  if (exchange) params.set("exchange", exchange);
  if (tier !== "") params.set("tier", tier);
  if (signal) params.set("signal", signal);
  if (minVol) params.set("min_volume", minVol);
  params.set("limit", "300");

  const { data: results = [], isLoading } = useQuery({
    queryKey: ["screener", search, exchange, tier, signal, minVol],
    queryFn: () => axios.get(`/api/universe/screener?${params}`).then((r) => r.data),
    keepPreviousData: true,
  });

  const { data: stats } = useQuery({
    queryKey: ["universe-stats"],
    queryFn: () => axios.get("/api/universe/stats").then((r) => r.data),
  });

  return (
    <div className="p-6 space-y-4">
      <div>
        <h1 className="text-2xl font-bold">Screener</h1>
        <p className="text-slate-500 text-sm">
          {stats ? `${stats.total_active?.toLocaleString()} stocks in universe` : "Loading..."}
        </p>
      </div>

      {/* Filter bar */}
      <div className="bg-card border border-border rounded-xl p-4 flex flex-wrap gap-3 items-end">
        <div className="flex-1 min-w-[200px]">
          <label className="text-xs text-slate-500 block mb-1">Search</label>
          <div className="relative">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
            <input
              className="w-full bg-surface border border-border rounded-lg pl-8 pr-3 py-2 text-sm outline-none focus:border-accent"
              placeholder="AAPL, Apple, RELIANCE..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
        </div>

        <div>
          <label className="text-xs text-slate-500 block mb-1">Exchange</label>
          <select
            className="bg-surface border border-border rounded-lg px-3 py-2 text-sm outline-none focus:border-accent"
            value={exchange}
            onChange={(e) => setExchange(e.target.value)}
          >
            <option value="">All</option>
            <option value="NASDAQ">NASDAQ</option>
            <option value="NYSE/AMEX">NYSE/AMEX</option>
            <option value="NSE">NSE (India)</option>
            <option value="BSE">BSE (India)</option>
          </select>
        </div>

        <div>
          <label className="text-xs text-slate-500 block mb-1">Tier</label>
          <select
            className="bg-surface border border-border rounded-lg px-3 py-2 text-sm outline-none focus:border-accent"
            value={tier}
            onChange={(e) => setTier(e.target.value)}
          >
            <option value="">All</option>
            <option value="2">Tier 2 — Deep Analysis</option>
            <option value="1">Tier 1 — Active</option>
            <option value="0">Tier 0 — Universe</option>
          </select>
        </div>

        <div>
          <label className="text-xs text-slate-500 block mb-1">Signal</label>
          <select
            className="bg-surface border border-border rounded-lg px-3 py-2 text-sm outline-none focus:border-accent"
            value={signal}
            onChange={(e) => setSignal(e.target.value)}
          >
            <option value="">Any</option>
            <option value="BUY">BUY</option>
            <option value="SELL">SELL</option>
            <option value="HOLD">HOLD</option>
          </select>
        </div>

        <div>
          <label className="text-xs text-slate-500 block mb-1">Min Volume</label>
          <input
            className="bg-surface border border-border rounded-lg px-3 py-2 text-sm outline-none focus:border-accent w-32"
            placeholder="e.g. 500000"
            value={minVol}
            onChange={(e) => setMinVol(e.target.value)}
          />
        </div>
      </div>

      {/* Results */}
      <div className="bg-card border border-border rounded-xl overflow-hidden">
        <div className="px-4 py-3 border-b border-border flex items-center justify-between">
          <p className="text-sm text-slate-400">{isLoading ? "Searching..." : `${results.length} results`}</p>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-xs text-slate-500 uppercase tracking-wider">
                <th className="px-4 py-3">Ticker</th>
                <th className="px-4 py-3">Name</th>
                <th className="px-4 py-3">Exchange</th>
                <th className="px-4 py-3">Sector</th>
                <th className="px-4 py-3">Tier</th>
                <th className="px-4 py-3 text-right">Price</th>
                <th className="px-4 py-3 text-right">Avg Vol (30d)</th>
                <th className="px-4 py-3 text-center">Signal</th>
                <th className="px-4 py-3 text-right">Confidence</th>
              </tr>
            </thead>
            <tbody>
              {results.map((r) => (
                <tr
                  key={r.ticker}
                  onClick={() => nav(`/stocks/stock/${r.ticker}`)}
                  className="border-b border-border/30 hover:bg-white/3 cursor-pointer transition-colors"
                >
                  <td className="px-4 py-3 font-bold text-white">{r.ticker}</td>
                  <td className="px-4 py-3 text-slate-400 max-w-[160px] truncate">{r.name || "—"}</td>
                  <td className="px-4 py-3 text-slate-500 text-xs">{r.exchange}</td>
                  <td className="px-4 py-3 text-slate-500 text-xs max-w-[120px] truncate">{r.sector || "—"}</td>
                  <td className="px-4 py-3">
                    <span className={clsx(
                      "text-xs px-2 py-0.5 rounded-full",
                      r.tier === 2 ? "bg-accent/20 text-accent" :
                      r.tier === 1 ? "bg-hold/20 text-hold" :
                      "bg-white/5 text-slate-500"
                    )}>
                      T{r.tier}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right text-slate-300">
                    {r.last_price ? `${r.currency === "INR" ? "₹" : "$"}${r.last_price.toFixed(2)}` : "—"}
                  </td>
                  <td className="px-4 py-3 text-right text-slate-500 text-xs">
                    {r.avg_volume_30d ? `${(r.avg_volume_30d / 1e6).toFixed(1)}M` : "—"}
                  </td>
                  <td className="px-4 py-3 text-center">
                    {r.signal ? (
                      <span className={clsx("text-xs font-bold", SIG_COLOR[r.signal])}>
                        {r.signal}
                      </span>
                    ) : (
                      <span className="text-slate-700 text-xs">—</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-right text-slate-400 text-xs">
                    {r.confidence ? `${Math.round(r.confidence * 100)}%` : "—"}
                  </td>
                </tr>
              ))}
              {results.length === 0 && !isLoading && (
                <tr>
                  <td colSpan={9} className="px-4 py-8 text-center text-slate-600 text-sm">
                    No stocks match these filters. Try broadening your search.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
