import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { Compass, Filter, Flame, Trophy } from "lucide-react";

const api = (url) => axios.get(url).then((r) => r.data);
const SIG_COLOR = { BUY: "text-green-400", SELL: "text-red-400", HOLD: "text-yellow-400" };
const TABS = [
  { id: "screener", label: "Screener",  icon: Filter },
  { id: "patterns", label: "Patterns",  icon: Flame  },
  { id: "topk",     label: "Top-K",     icon: Trophy },
];

// ── Screener tab ──────────────────────────────────────────────────────────
function ScreenerTab() {
  const nav = useNavigate();
  const [search, setSearch] = useState("");
  const [signal, setSignal] = useState("");

  const params = new URLSearchParams({ limit: 50 });
  if (search) params.set("search", search);
  if (signal) params.set("signal", signal);

  const { data = [], isLoading } = useQuery({
    queryKey: ["screener", search, signal],
    queryFn: () => api(`/api/universe/screener?${params}`),
    staleTime: 60_000,
  });

  return (
    <div className="space-y-3">
      <div className="flex gap-2">
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Ticker or name…"
          className="flex-1 bg-surface border border-border rounded-lg px-3 py-2 text-sm outline-none focus:border-accent text-slate-300 placeholder:text-slate-600"
        />
        <select
          value={signal}
          onChange={(e) => setSignal(e.target.value)}
          className="bg-surface border border-border rounded-lg px-3 py-2 text-sm text-slate-300 outline-none focus:border-accent"
        >
          <option value="">All signals</option>
          <option value="BUY">BUY</option>
          <option value="SELL">SELL</option>
          <option value="HOLD">HOLD</option>
        </select>
      </div>

      {isLoading ? (
        <p className="text-slate-600 text-sm py-6 text-center">Loading…</p>
      ) : (
        <div className="overflow-auto rounded-xl border border-border">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-border text-slate-500">
                <th className="text-left px-3 py-2">Ticker</th>
                <th className="text-left px-3 py-2 hidden md:table-cell">Name</th>
                <th className="text-right px-3 py-2">Price</th>
                <th className="text-right px-3 py-2">Signal</th>
                <th className="text-right px-3 py-2">Confidence</th>
              </tr>
            </thead>
            <tbody>
              {data.map((row) => (
                <tr
                  key={row.ticker}
                  onClick={() => nav(`/stocks/stock/${row.ticker}`)}
                  className="border-b border-border/50 hover:bg-white/5 cursor-pointer transition-colors"
                >
                  <td className="px-3 py-2 font-mono font-bold text-white">{row.ticker}</td>
                  <td className="px-3 py-2 text-slate-400 hidden md:table-cell truncate max-w-[180px]">{row.name}</td>
                  <td className="px-3 py-2 text-right font-mono">${row.last_price?.toFixed(2) ?? "—"}</td>
                  <td className={`px-3 py-2 text-right font-bold ${SIG_COLOR[row.signal] ?? "text-slate-500"}`}>
                    {row.signal ?? "—"}
                  </td>
                  <td className="px-3 py-2 text-right text-slate-400">
                    {row.confidence != null ? `${(row.confidence * 100).toFixed(0)}%` : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ── Patterns tab ──────────────────────────────────────────────────────────
const PATTERN_COLORS = {
  VCP: "bg-purple-500/20 text-purple-300",
  NR7: "bg-blue-500/20 text-blue-300",
  CUP_HANDLE: "bg-yellow-500/20 text-yellow-300",
  STAGE2: "bg-green-500/20 text-green-300",
  BB_SQUEEZE: "bg-orange-500/20 text-orange-300",
};

function PatternsTab() {
  const nav = useNavigate();
  const { data = [], isLoading } = useQuery({
    queryKey: ["patterns-top"],
    queryFn: () => api("/api/patterns/scan/top?limit=40").then((r) => r.results ?? r),
    staleTime: 120_000,
  });

  return isLoading ? (
    <p className="text-slate-600 text-sm py-6 text-center">Scanning patterns…</p>
  ) : (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
      {data.map((item) => (
        <div
          key={item.ticker}
          onClick={() => nav(`/stocks/stock/${item.ticker}`)}
          className="bg-card border border-border rounded-xl p-3 hover:border-accent/40 cursor-pointer transition-colors"
        >
          <div className="flex items-center justify-between mb-2">
            <span className="font-mono font-bold">{item.ticker}</span>
            <span className="text-xs text-slate-500">
              score {(item.pattern_score * 100).toFixed(0)}%
            </span>
          </div>
          <div className="flex flex-wrap gap-1">
            {(item.patterns || []).map((p) => (
              <span key={p} className={`px-1.5 py-0.5 rounded text-[9px] font-bold ${PATTERN_COLORS[p] ?? "bg-slate-700 text-slate-400"}`}>
                {p.replace(/_/g, " ")}
              </span>
            ))}
          </div>
          {item.stage_name && (
            <p className="text-[10px] text-slate-500 mt-1.5">{item.stage_name}</p>
          )}
        </div>
      ))}
    </div>
  );
}

// ── Top-K tab ─────────────────────────────────────────────────────────────
function TopKTab() {
  const nav = useNavigate();
  const [k, setK] = useState(10);

  const { data, isLoading } = useQuery({
    queryKey: ["topk", k],
    queryFn: () => api(`/api/topk?k=${k}`),
    staleTime: 60_000,
  });

  const items = Array.isArray(data) ? data : (data?.longs ?? data ?? []);

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <span className="text-xs text-slate-500">Portfolio size K =</span>
        {[5, 10, 15, 20].map((n) => (
          <button
            key={n}
            onClick={() => setK(n)}
            className={`px-2.5 py-1 rounded-lg text-xs border transition-colors ${
              k === n ? "bg-accent/20 text-accent border-accent/30" : "text-slate-500 border-transparent hover:border-border"
            }`}
          >{n}</button>
        ))}
      </div>
      {isLoading ? (
        <p className="text-slate-600 text-sm py-6 text-center">Ranking…</p>
      ) : (
        <div className="space-y-2">
          {items.filter(i => i.position === "LONG" || i.composite_score > 0).map((item, idx) => (
            <div
              key={item.ticker}
              onClick={() => nav(`/stocks/stock/${item.ticker}`)}
              className="flex items-center gap-3 p-3 bg-card border border-border rounded-xl hover:border-accent/40 cursor-pointer transition-colors"
            >
              <span className="text-slate-600 text-xs w-5 text-center">#{idx + 1}</span>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="font-mono font-bold">{item.ticker}</span>
                  <span className="text-[10px] text-slate-500 truncate">{item.name}</span>
                </div>
                <div className="flex gap-1 mt-0.5">
                  {(item.patterns || []).slice(0, 3).map((p) => (
                    <span key={p} className={`px-1 py-px rounded text-[8px] font-bold ${PATTERN_COLORS[p] ?? "bg-slate-700 text-slate-400"}`}>
                      {p.replace(/_/g, " ")}
                    </span>
                  ))}
                </div>
              </div>
              <div className="text-right shrink-0">
                <p className={`text-xs font-bold ${item.composite_score >= 0 ? "text-green-400" : "text-red-400"}`}>
                  {item.composite_score >= 0 ? "+" : ""}{(item.composite_score * 100).toFixed(1)}
                </p>
                {item.optimal_weight != null && (
                  <p className="text-[10px] text-slate-500">{(item.optimal_weight * 100).toFixed(1)}% wt</p>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Main ──────────────────────────────────────────────────────────────────
export default function DiscoverPage() {
  const [tab, setTab] = useState("screener");
  const Tab = tab === "screener" ? ScreenerTab : tab === "patterns" ? PatternsTab : TopKTab;

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center gap-2">
        <Compass size={20} className="text-accent" />
        <h1 className="text-2xl font-bold">Discover</h1>
      </div>

      <div className="flex gap-1 bg-card border border-border rounded-xl p-1 w-fit">
        {TABS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm transition-colors ${
              tab === id ? "bg-accent text-white" : "text-slate-400 hover:text-white"
            }`}
          >
            <Icon size={14} />
            {label}
          </button>
        ))}
      </div>

      <Tab />
    </div>
  );
}
