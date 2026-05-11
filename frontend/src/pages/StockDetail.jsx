import { useParams, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import axios from "axios";
import CandlestickChart from "../components/CandlestickChart";
import clsx from "clsx";
import { MessageSquare, Newspaper, BarChart2 } from "lucide-react";

const api = (path) => axios.get(path).then((r) => r.data);

const SIG_COLOR = { BUY: "text-buy", SELL: "text-sell", HOLD: "text-hold" };

function fmt(n, dec = 2) {
  if (n == null) return "—";
  return Number(n).toLocaleString("en-US", { minimumFractionDigits: dec, maximumFractionDigits: dec });
}
function pct(n) {
  if (n == null) return "—";
  const v = Number(n);
  return `${v >= 0 ? "+" : ""}${v.toFixed(2)}%`;
}

export default function StockDetail() {
  const { ticker } = useParams();
  const navigate   = useNavigate();
  const t          = ticker.toUpperCase();

  const { data: market }          = useQuery({ queryKey: ["market",   t], queryFn: () => api(`/api/market/${t}`), refetchInterval: (data) => data?.refreshing ? 5000 : false });
  const { data: sigHistory = [] } = useQuery({ queryKey: ["sig-hist", t], queryFn: () => api(`/api/signals/${t}`) });
  const { data: newsData }        = useQuery({ queryKey: ["news",     t], queryFn: () => api(`/api/news/${t}`) });
  const { data: correlations = []}= useQuery({ queryKey: ["corr",     t], queryFn: () => api(`/api/graph/correlations/${t}`), retry: false });
  const { data: tierInfo }        = useQuery({ queryKey: ["tier",     t], queryFn: () => api(`/api/universe/${t}/tier`) });
  const { data: fundamentals }    = useQuery({ queryKey: ["fund",     t], queryFn: () => api(`/api/fundamentals/${t}`), retry: false });
  const { data: social = [] }     = useQuery({ queryKey: ["social",   t], queryFn: () => api(`/api/social/${t}`) });

  const tech     = market?.technicals ?? {};
  const ohlcv    = market?.ohlcv ?? [];
  const latestSig= sigHistory[0];
  const sentiment= newsData?.sentiment ?? [];

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-3xl font-bold">{t}</h1>
          {tierInfo && (
            <p className="text-slate-500 text-sm mt-0.5">
              {tierInfo.exchange} · {tierInfo.sector || "Unknown sector"} ·{" "}
              <span className={tierInfo.tier === 2 ? "text-accent" : "text-slate-500"}>
                Tier {tierInfo.tier}{tierInfo.tier === 2 ? " (deep analysis)" : tierInfo.tier === 1 ? " (active)" : " (universe)"}
              </span>
            </p>
          )}
        </div>
        {latestSig && (
          <div className="text-right">
            <span className={clsx("text-2xl font-bold", SIG_COLOR[latestSig.signal])}>
              {latestSig.signal}
            </span>
            <p className="text-sm text-slate-400">{Math.round(latestSig.confidence * 100)}% confidence</p>
          </div>
        )}
      </div>

      {/* Candlestick chart */}
      <div className="bg-card border border-border rounded-xl p-4">
        <div className="flex items-center gap-2 mb-3">
          <p className="text-xs text-slate-500">Price (1D)</p>
          {market?.refreshing && (
            <span className="text-[10px] text-orange-400 animate-pulse">⟳ Fetching history…</span>
          )}
        </div>
        <CandlestickChart data={ohlcv.slice(-60)} />
      </div>

      {/* Technicals */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
        {[
          { label: "RSI (14)",  value: tech.rsi?.toFixed(1),   color: tech.rsi < 30 ? "text-buy" : tech.rsi > 70 ? "text-sell" : "text-white" },
          { label: "MACD",      value: tech.macd?.toFixed(4),  color: tech.macd > 0 ? "text-buy" : "text-sell" },
          { label: "ATR",       value: tech.atr?.toFixed(4) },
          { label: "VWAP",      value: tech.vwap?.toFixed(2) },
          { label: "EMA 9",     value: tech.ema9?.toFixed(2) },
          { label: "EMA 21",    value: tech.ema21?.toFixed(2) },
          { label: "BB Upper",  value: tech.bb_upper?.toFixed(2) },
          { label: "BB Lower",  value: tech.bb_lower?.toFixed(2) },
        ].map(({ label, value, color = "text-white" }) => (
          <div key={label} className="bg-card border border-border rounded-lg p-3">
            <p className="text-xs text-slate-500">{label}</p>
            <p className={`font-bold mt-1 ${color}`}>{value ?? "—"}</p>
          </div>
        ))}
      </div>

      {/* Signal model breakdown */}
      {latestSig && (
        <div className="bg-card border border-border rounded-xl p-4">
          <p className="text-xs text-slate-500 uppercase tracking-wider mb-3">Signal Breakdown</p>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {[
              { label: "GNN (35%)",          score: latestSig.gnn_score },
              { label: "XGBoost (25%)",       score: latestSig.xgb_score },
              { label: "Sentiment (20%)",     score: latestSig.sentiment_score },
              { label: "Fundamentals (20%)",  score: latestSig.fundamental_score },
            ].map(({ label, score }) => (
              <div key={label}>
                <p className="text-xs text-slate-500">{label}</p>
                <div className="flex items-center gap-2 mt-1">
                  <div className="flex-1 h-1.5 bg-white/5 rounded-full overflow-hidden">
                    <div
                      className={score > 0 ? "h-full bg-buy rounded-full" : "h-full bg-sell rounded-full"}
                      style={{ width: `${Math.abs(score ?? 0) * 100}%` }}
                    />
                  </div>
                  <span className={clsx("text-xs font-medium", score > 0 ? "text-buy" : "text-sell")}>
                    {score >= 0 ? "+" : ""}{score?.toFixed(2)}
                  </span>
                </div>
              </div>
            ))}
          </div>
          {latestSig.reasons?.length > 0 && (
            <ul className="mt-3 space-y-1">
              {latestSig.reasons.map((r, i) => (
                <li key={i} className="text-xs text-slate-400 flex gap-2">
                  <span className="text-accent shrink-0">›</span> {r}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* Fundamentals — SEC EDGAR + yfinance real data */}
      {fundamentals && (
        <div className="bg-card border border-border rounded-xl p-4">
          <div className="flex items-center gap-2 mb-3">
            <BarChart2 size={14} className="text-slate-500" />
            <p className="text-xs text-slate-500 uppercase tracking-wider">Fundamentals</p>
            <span className="text-[10px] text-slate-700 ml-auto">SEC EDGAR + yfinance</span>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {[
              { label: "P/E Ratio",       value: fundamentals.pe_ratio != null      ? fmt(fundamentals.pe_ratio, 1)       : null },
              { label: "EPS",             value: fundamentals.eps != null            ? `$${fmt(fundamentals.eps, 2)}`      : null },
              { label: "Revenue Growth",  value: fundamentals.revenue_growth != null ? pct(fundamentals.revenue_growth * 100) : null },
              { label: "Profit Margin",   value: fundamentals.profit_margin != null  ? pct(fundamentals.profit_margin * 100) : null,
                color: fundamentals.profit_margin > 0 ? "text-buy" : "text-sell" },
              { label: "Debt / Equity",   value: fundamentals.debt_to_equity != null ? fmt(fundamentals.debt_to_equity, 2) : null,
                color: fundamentals.debt_to_equity > 2 ? "text-sell" : fundamentals.debt_to_equity < 1 ? "text-buy" : "text-white" },
              { label: "Current Ratio",   value: fundamentals.current_ratio != null  ? fmt(fundamentals.current_ratio, 2)  : null,
                color: fundamentals.current_ratio > 1.5 ? "text-buy" : "text-sell" },
              { label: "ROE",             value: fundamentals.roe != null            ? pct(fundamentals.roe * 100)         : null,
                color: fundamentals.roe > 0 ? "text-buy" : "text-sell" },
              { label: "Sector P/E",      value: fundamentals.sector_pe != null      ? fmt(fundamentals.sector_pe, 1)      : null },
            ].map(({ label, value, color = "text-white" }) => value != null && (
              <div key={label} className="bg-surface rounded-lg p-3">
                <p className="text-xs text-slate-500">{label}</p>
                <p className={`font-bold mt-1 text-sm ${color}`}>{value}</p>
              </div>
            ))}
          </div>
          <p className="text-[10px] text-slate-700 mt-2">Updated: {fundamentals.updated_at?.slice(0, 10)}</p>
        </div>
      )}

      {/* Sentiment timeline */}
      {sentiment.length > 0 && (
        <div className="bg-card border border-border rounded-xl p-4">
          <p className="text-xs text-slate-500 uppercase tracking-wider mb-3">Sentiment (7d · VADER NLP)</p>
          <div className="space-y-2">
            {sentiment.map((s) => (
              <div key={s.date} className="flex items-center gap-3 text-xs">
                <span className="text-slate-600 w-20 shrink-0">{s.date}</span>
                <div className="flex-1 h-2 bg-surface rounded-full overflow-hidden flex">
                  <div className="bg-buy h-full" style={{ width: `${s.positive * 100}%` }} />
                  <div className="bg-slate-600 h-full" style={{ width: `${s.neutral * 100}%` }} />
                  <div className="bg-sell h-full" style={{ width: `${s.negative * 100}%` }} />
                </div>
                <span className={`w-12 text-right font-bold ${s.composite_score >= 0 ? "text-buy" : "text-sell"}`}>
                  {s.composite_score >= 0 ? "+" : ""}{s.composite_score?.toFixed(2)}
                </span>
                <span className="text-slate-600 w-16 text-right">{s.article_count} articles</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Social mentions — StockTwits, Google News, Finviz, ET, Moneycontrol */}
      {social.length > 0 && (
        <div className="bg-card border border-border rounded-xl p-4">
          <div className="flex items-center gap-2 mb-3">
            <MessageSquare size={14} className="text-slate-500" />
            <p className="text-xs text-slate-500 uppercase tracking-wider">
              Social Mentions · {social.length} recent
            </p>
            <span className="text-[10px] text-slate-700 ml-auto">StockTwits · Google News · Finviz · ET · Moneycontrol</span>
          </div>
          <ul className="space-y-2">
            {social.slice(0, 10).map((m, i) => (
              <li key={i} className="text-xs flex gap-3 items-start">
                <span className="text-[10px] text-slate-600 w-24 shrink-0 pt-0.5">{m.source}</span>
                <span className="text-slate-400 flex-1 leading-relaxed">{m.text}</span>
                <span className="text-[10px] text-slate-700 shrink-0">{m.created_at?.slice(0, 16).replace("T", " ")}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* News + correlations */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="bg-card border border-border rounded-xl p-4">
          <div className="flex items-center gap-2 mb-3">
            <Newspaper size={14} className="text-slate-500" />
            <p className="text-xs text-slate-500 uppercase tracking-wider">Recent News</p>
          </div>
          {newsData?.news?.length ? (
            <ul className="space-y-3">
              {newsData.news.slice(0, 8).map((n, i) => (
                <li key={i} className="text-sm">
                  <a href={n.url} target="_blank" rel="noreferrer" className="hover:text-accent transition-colors leading-snug">
                    {n.headline}
                  </a>
                  <p className="text-xs text-slate-600 mt-0.5">{n.source} · {n.published_at?.slice(0, 10)}</p>
                </li>
              ))}
            </ul>
          ) : <p className="text-sm text-slate-600">No recent news</p>}
        </div>

        <div className="bg-card border border-border rounded-xl p-4">
          <p className="text-xs text-slate-500 uppercase tracking-wider mb-3">Correlated Stocks</p>
          {correlations.length ? (
            <ul className="space-y-2">
              {correlations.slice(0, 10).map((c) => (
                <li key={c.ticker}
                  className="flex justify-between text-sm hover:text-accent cursor-pointer transition-colors"
                  onClick={() => navigate(`/stocks/stock/${c.ticker}`)}>
                  <span className="font-medium">{c.ticker}</span>
                  <span className="text-slate-500">{(c.weight * 100).toFixed(1)}% corr</span>
                </li>
              ))}
            </ul>
          ) : <p className="text-sm text-slate-600">No correlations yet</p>}
        </div>
      </div>
    </div>
  );
}
