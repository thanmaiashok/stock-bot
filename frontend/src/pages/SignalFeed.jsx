import { useQuery } from "@tanstack/react-query";
import axios from "axios";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import clsx from "clsx";

const api = (path) => axios.get(path).then((r) => r.data);

const SIG_COLOR = {
  BUY: "text-buy border-buy/30 bg-buy/10",
  SELL: "text-sell border-sell/30 bg-sell/10",
  HOLD: "text-hold border-hold/30 bg-hold/10",
};

export default function SignalFeed() {
  const nav = useNavigate();
  const [filter, setFilter] = useState("ALL");
  const { data: signals = [], isLoading } = useQuery({
    queryKey: ["signals-all"],
    queryFn: () => api("/api/signals?limit=500"),
    refetchInterval: 15000,
  });

  const filtered = filter === "ALL" ? signals : signals.filter((s) => s.signal === filter);

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Signal Feed</h1>
          <p className="text-slate-500 text-sm">{signals.length} signals · refreshes every 15 min</p>
        </div>
        <div className="flex gap-2">
          {["ALL", "BUY", "SELL", "HOLD"].map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={clsx(
                "px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors",
                filter === f
                  ? f === "BUY" ? "bg-buy text-white border-buy"
                    : f === "SELL" ? "bg-sell text-white border-sell"
                    : f === "HOLD" ? "bg-hold text-white border-hold"
                    : "bg-accent text-white border-accent"
                  : "border-border text-slate-400 hover:text-white hover:border-slate-500"
              )}
            >
              {f}
            </button>
          ))}
        </div>
      </div>

      {isLoading ? (
        <p className="text-slate-500 text-sm">Loading signals...</p>
      ) : filtered.length === 0 ? (
        <p className="text-slate-500 text-sm">No {filter !== "ALL" ? filter : ""} signals yet.</p>
      ) : (
        <div className="space-y-2">
          {filtered.map((s, i) => (
            <div
              key={`${s.ticker}-${i}`}
              onClick={() => nav(`/stocks/stock/${s.ticker}`)}
              className="bg-card border border-border rounded-xl p-4 flex items-center gap-4 hover:border-accent cursor-pointer transition-colors"
            >
              <span className={clsx("text-xs font-bold px-2 py-1 rounded-full border w-14 text-center shrink-0", SIG_COLOR[s.signal])}>
                {s.signal}
              </span>

              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="font-bold">{s.ticker}</span>
                  {s.name && <span className="text-xs text-slate-500 truncate">{s.name}</span>}
                  <span className="text-xs text-slate-600 shrink-0">{s.exchange}</span>
                </div>
                {s.reasons?.length > 0 && (
                  <p className="text-xs text-slate-500 mt-0.5 truncate">{s.reasons.join(" · ")}</p>
                )}
              </div>

              {/* Model breakdown */}
              <div className="hidden lg:flex gap-4 text-xs text-slate-500 shrink-0">
                <span>GNN: <span className={s.gnn_score > 0 ? "text-buy" : "text-sell"}>{s.gnn_score?.toFixed(2)}</span></span>
                <span>XGB: <span className={s.xgb_score > 0 ? "text-buy" : "text-sell"}>{s.xgb_score?.toFixed(2)}</span></span>
                <span>Sent: <span className={s.sentiment_score > 0 ? "text-buy" : "text-sell"}>{s.sentiment_score?.toFixed(2)}</span></span>
              </div>

              {/* Confidence */}
              <div className="text-right shrink-0">
                <p className="font-bold text-sm">{Math.round(s.confidence * 100)}%</p>
                {s.price && <p className="text-xs text-slate-500">${s.price?.toFixed(2)}</p>}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
