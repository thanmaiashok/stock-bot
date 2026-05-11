import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { Plus, X } from "lucide-react";
import clsx from "clsx";

const SIG_COLOR = { BUY: "text-buy", SELL: "text-sell", HOLD: "text-hold" };

export default function Watchlist() {
  const nav = useNavigate();
  const qc = useQueryClient();
  const [input, setInput] = useState("");

  const { data: items = [] } = useQuery({
    queryKey: ["screener-tier2"],
    queryFn: () => axios.get("/api/universe/screener?tier=2&limit=500").then((r) => r.data),
    refetchInterval: 60000,
  });

  const add = useMutation({
    mutationFn: (ticker) => axios.post("/api/watchlist/add", { ticker }),
    onSuccess: () => { qc.invalidateQueries(["screener-tier2"]); setInput(""); },
  });

  const remove = useMutation({
    mutationFn: (ticker) => axios.post("/api/watchlist/remove", { ticker }),
    onSuccess: () => qc.invalidateQueries(["screener-tier2"]),
  });

  const handleAdd = () => {
    if (input.trim()) add.mutate(input.trim().toUpperCase());
  };

  return (
    <div className="p-6 space-y-5">
      <h1 className="text-2xl font-bold">Watchlist</h1>
      <p className="text-slate-500 text-sm">Tier 2 tickers receive 15-min deep analysis. Add any stock from the 18k+ universe.</p>

      {/* Add ticker */}
      <div className="flex gap-3">
        <input
          className="bg-card border border-border rounded-lg px-4 py-2 text-sm outline-none focus:border-accent flex-1 max-w-xs"
          placeholder="Add ticker (e.g. AAPL, RELIANCE.NS)"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleAdd()}
        />
        <button
          onClick={handleAdd}
          disabled={!input.trim() || add.isLoading}
          className="flex items-center gap-2 bg-accent text-white px-4 py-2 rounded-lg text-sm hover:bg-accent/80 transition-colors disabled:opacity-50"
        >
          <Plus size={14} /> Add
        </button>
      </div>

      {/* Table */}
      <div className="bg-card border border-border rounded-xl overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-xs text-slate-500 uppercase tracking-wider">
              <th className="px-4 py-3">Ticker</th>
              <th className="px-4 py-3">Name</th>
              <th className="px-4 py-3">Exchange</th>
              <th className="px-4 py-3 text-right">Price</th>
              <th className="px-4 py-3 text-right">Volume</th>
              <th className="px-4 py-3 text-center">Signal</th>
              <th className="px-4 py-3 text-center">Confidence</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody>
            {items.map((r) => (
              <tr
                key={r.ticker}
                className="border-b border-border/30 hover:bg-white/3 transition-colors"
              >
                <td
                  className="px-4 py-3 font-bold text-white cursor-pointer hover:text-accent"
                  onClick={() => nav(`/stocks/stock/${r.ticker}`)}
                >
                  {r.ticker}
                </td>
                <td className="px-4 py-3 text-slate-400 text-xs max-w-[160px] truncate">{r.name || "—"}</td>
                <td className="px-4 py-3 text-slate-500 text-xs">{r.exchange}</td>
                <td className="px-4 py-3 text-right text-slate-300">
                  {r.last_price ? `${r.currency === "INR" ? "₹" : "$"}${r.last_price.toFixed(2)}` : "—"}
                </td>
                <td className="px-4 py-3 text-right text-slate-500 text-xs">
                  {r.avg_volume_30d ? `${(r.avg_volume_30d / 1e6).toFixed(1)}M` : "—"}
                </td>
                <td className="px-4 py-3 text-center">
                  <span className={clsx("text-xs font-bold", SIG_COLOR[r.signal] ?? "text-slate-600")}>
                    {r.signal ?? "—"}
                  </span>
                </td>
                <td className="px-4 py-3 text-center text-xs text-slate-400">
                  {r.confidence ? `${Math.round(r.confidence * 100)}%` : "—"}
                </td>
                <td className="px-4 py-3 text-right">
                  <button
                    onClick={() => remove.mutate(r.ticker)}
                    className="text-slate-600 hover:text-sell transition-colors"
                  >
                    <X size={14} />
                  </button>
                </td>
              </tr>
            ))}
            {items.length === 0 && (
              <tr>
                <td colSpan={8} className="px-4 py-8 text-center text-slate-600 text-sm">
                  No Tier 2 stocks yet. Universe refresh runs daily at 06:00 UTC and auto-assigns tiers.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
