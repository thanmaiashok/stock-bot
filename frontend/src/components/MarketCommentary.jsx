import { useQuery } from "@tanstack/react-query";
import axios from "axios";
import { Brain, RefreshCw } from "lucide-react";

const SENTIMENT_STYLE = {
  "BULLISH":            { bg: "bg-green-500/10",  border: "border-green-500/30",  text: "text-green-400"  },
  "CAUTIOUSLY BULLISH": { bg: "bg-green-500/8",   border: "border-green-500/20",  text: "text-green-400"  },
  "RISK-ON":            { bg: "bg-green-500/10",  border: "border-green-500/30",  text: "text-green-400"  },
  "MILDLY BULLISH":     { bg: "bg-green-500/8",   border: "border-green-500/20",  text: "text-green-400"  },
  "BEARISH":            { bg: "bg-red-500/10",    border: "border-red-500/30",    text: "text-red-400"    },
  "CAUTIOUSLY BEARISH": { bg: "bg-red-500/8",     border: "border-red-500/20",    text: "text-red-400"    },
  "RISK-OFF":           { bg: "bg-red-500/10",    border: "border-red-500/30",    text: "text-red-400"    },
  "MILDLY BEARISH":     { bg: "bg-red-500/8",     border: "border-red-500/20",    text: "text-red-400"    },
  "MIXED":              { bg: "bg-slate-500/10",  border: "border-slate-500/30",  text: "text-slate-400"  },
  "UNKNOWN":            { bg: "bg-slate-500/10",  border: "border-slate-500/30",  text: "text-slate-400"  },
};

export default function MarketCommentary({ mode = "stocks" }) {
  const endpoint = mode === "futures" ? "/api/futures/commentary" : "/api/market/commentary";

  const { data, isLoading, refetch, dataUpdatedAt } = useQuery({
    queryKey: ["commentary", mode],
    queryFn:  () => axios.get(endpoint).then((r) => r.data),
    refetchInterval: 900_000, // 15 min
    staleTime: 900_000,
  });

  const style = SENTIMENT_STYLE[data?.sentiment] ?? SENTIMENT_STYLE["MIXED"];

  return (
    <div className={`rounded-xl border p-4 ${style.bg} ${style.border}`}>
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <Brain size={14} className={style.text} />
          <span className="text-xs font-semibold text-slate-300">AI Market Commentary</span>
          {data?.sentiment && (
            <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full border ${style.bg} ${style.border} ${style.text}`}>
              {data.sentiment}
            </span>
          )}
        </div>
        <div className="flex items-center gap-3">
          {dataUpdatedAt > 0 && (
            <span className="text-[10px] text-slate-600">
              {new Date(dataUpdatedAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
            </span>
          )}
          <button onClick={() => refetch()} className="text-slate-500 hover:text-slate-300 transition-colors">
            <RefreshCw size={11} className={isLoading ? "animate-spin" : ""} />
          </button>
        </div>
      </div>

      {isLoading ? (
        <div className="h-8 flex items-center">
          <span className="text-xs text-slate-600 animate-pulse">Generating commentary…</span>
        </div>
      ) : data?.commentary ? (
        <p className="text-sm text-slate-300 leading-relaxed">{data.commentary}</p>
      ) : (
        <p className="text-xs text-slate-600">No signal data yet — run signal generation first.</p>
      )}

      {/* Mini stat pills */}
      {data && (
        <div className="flex gap-3 mt-3 flex-wrap">
          {mode === "stocks" ? (
            <>
              <Pill label="BUY"  val={`${data.buy_pct}%`}  color="text-green-400" />
              <Pill label="SELL" val={`${data.sell_pct}%`} color="text-red-400"   />
              <Pill label="Conf" val={`${Math.round((data.avg_confidence ?? 0) * 100)}%`} color="text-slate-300" />
              {data.hot_sector  && <Pill label="Hot"  val={data.hot_sector}  color="text-green-400" />}
              {data.cold_sector && <Pill label="Cold" val={data.cold_sector} color="text-red-400"   />}
            </>
          ) : (
            <>
              <Pill label="LONG"  val={`${data.long_pct}%`}  color="text-green-400" />
              <Pill label="SHORT" val={`${data.short_pct}%`} color="text-red-400"   />
              <Pill label="Conf"  val={`${Math.round((data.avg_confidence ?? 0) * 100)}%`} color="text-slate-300" />
              {data.best_cat  && <Pill label="Leading" val={data.best_cat}  color="text-green-400" />}
              {data.worst_cat && <Pill label="Lagging" val={data.worst_cat} color="text-red-400"   />}
            </>
          )}
        </div>
      )}
    </div>
  );
}

function Pill({ label, val, color }) {
  return (
    <span className="text-[10px] bg-surface border border-border rounded px-2 py-0.5 flex items-center gap-1">
      <span className="text-slate-500">{label}</span>
      <span className={`font-bold font-mono ${color}`}>{val}</span>
    </span>
  );
}
