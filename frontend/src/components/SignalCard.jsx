import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import axios from "axios";
import clsx from "clsx";
import { ChevronDown, Zap } from "lucide-react";

const SIGNAL_STYLES = {
  BUY:  "bg-buy/10 text-buy border-buy/30",
  SELL: "bg-sell/10 text-sell border-sell/30",
  HOLD: "bg-hold/10 text-hold border-hold/30",
};

function ComponentRow({ c, sigDir }) {
  const agree = c.bullish === sigDir;
  return (
    <div className="flex items-center gap-2 text-[10px]">
      <span className={agree ? "text-green-400" : "text-red-400"}>{agree ? "✓" : "✗"}</span>
      <span className="text-slate-400 font-medium w-24 shrink-0">{c.name}</span>
      <span className="text-slate-500 truncate">{c.detail}</span>
    </div>
  );
}

export default function SignalCard({ signal }) {
  const nav = useNavigate();
  const [open, setOpen] = useState(false);
  const pct = Math.round(signal.confidence * 100);

  const { data: bd } = useQuery({
    queryKey: ["breakdown", signal.ticker],
    queryFn: () => axios.get(`/api/signals/breakdown/${signal.ticker}`).then(r => r.data),
    enabled: open,
    staleTime: 5 * 60 * 1000,
  });

  const bullishDir = signal.signal === "BUY";

  // Client-side conviction from existing reasons (no extra fetch needed for badge)
  const reasons = signal.reasons ?? [];
  const quickConviction = reasons.length >= 3 && (
    signal.confidence >= 0.75 || pct >= 75
  );

  return (
    <div
      className={clsx(
        "border rounded-xl cursor-pointer hover:border-accent transition-colors",
        SIGNAL_STYLES[signal.signal] ?? "bg-card border-border"
      )}
    >
      {/* Main card — navigate on click */}
      <div className="p-4" onClick={() => nav(`/stocks/stock/${signal.ticker}`)}>
        <div className="flex items-start gap-2 mb-2">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-1.5">
              <span className="font-bold text-lg">{signal.ticker}</span>
              {quickConviction && (
                <span className="flex items-center gap-0.5 text-[9px] font-bold px-1.5 py-0.5 rounded-full bg-yellow-500/20 text-yellow-400 border border-yellow-500/30">
                  <Zap size={8} /> HIGH CONVICTION
                </span>
              )}
            </div>
            {signal.name && (
              <p className="text-xs text-slate-400 truncate">{signal.name}</p>
            )}
          </div>
          <span className={clsx(
            "shrink-0 text-xs font-bold px-2 py-0.5 rounded-full border",
            SIGNAL_STYLES[signal.signal]
          )}>
            {signal.signal}
          </span>
        </div>

        <div className="mb-3">
          <div className="flex justify-between text-xs text-slate-500 mb-1">
            <span>Confidence</span>
            <span className="font-medium text-white">{pct}%</span>
          </div>
          <div className="h-1.5 bg-white/5 rounded-full overflow-hidden">
            <div
              className={clsx("h-full rounded-full transition-all",
                signal.signal === "BUY" ? "bg-buy" : signal.signal === "SELL" ? "bg-sell" : "bg-hold"
              )}
              style={{ width: `${pct}%` }}
            />
          </div>
        </div>

        <div className="flex justify-between text-xs text-slate-400">
          {signal.price && <span>${signal.price.toFixed(2)}</span>}
          <span className="text-slate-600">{signal.exchange}</span>
        </div>

        {reasons.length > 0 && (
          <p className="text-xs text-slate-500 mt-2 truncate">{reasons[0]}</p>
        )}
      </div>

      {/* Why? toggle */}
      {reasons.length > 0 && (
        <div className="border-t border-white/5">
          <button
            onClick={(e) => { e.stopPropagation(); setOpen(v => !v); }}
            className="w-full flex items-center justify-between px-4 py-1.5 text-[10px] text-slate-500 hover:text-slate-300 transition-colors"
          >
            <span>Why {signal.signal}?</span>
            <ChevronDown size={10} className={clsx("transition-transform", open && "rotate-180")} />
          </button>

          {open && (
            <div className="px-4 pb-3 space-y-1.5">
              {bd ? (
                <>
                  {bd.components.map((c, i) => (
                    <ComponentRow key={i} c={c} sigDir={bullishDir} />
                  ))}
                  <div className="mt-2 flex items-center gap-2">
                    <div className="h-px flex-1 bg-white/5" />
                    <span className={clsx("text-[9px] font-bold",
                      bd.high_conviction ? "text-yellow-400" : "text-slate-600"
                    )}>
                      {bd.agreeing}/{bd.total} signals agree
                      {bd.high_conviction && " · HIGH CONVICTION"}
                    </span>
                    <div className="h-px flex-1 bg-white/5" />
                  </div>
                </>
              ) : (
                reasons.map((r, i) => (
                  <p key={i} className="text-[10px] text-slate-500">• {r}</p>
                ))
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
