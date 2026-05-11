import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import axios from "axios";
import { useNavigate } from "react-router-dom";
import { Newspaper, RefreshCw, TrendingUp, TrendingDown, Zap } from "lucide-react";

const api = (path) => axios.get(path).then((r) => r.data);

// Map futures symbol → short display name
const FUTURES_NAMES = {
  "CL=F": "WTI Oil", "BZ=F": "Brent", "NG=F": "Nat Gas", "RB=F": "Gasoline", "HO=F": "Htg Oil",
  "GC=F": "Gold", "SI=F": "Silver", "HG=F": "Copper", "PL=F": "Platinum", "PA=F": "Palladium",
  "ZC=F": "Corn", "ZW=F": "Wheat", "KE=F": "KC Wheat", "ZS=F": "Soybeans", "ZO=F": "Oats",
  "SB=F": "Sugar", "KC=F": "Coffee", "CT=F": "Cotton", "CC=F": "Cocoa",
  "ES=F": "S&P500", "NQ=F": "NASDAQ", "YM=F": "Dow", "RTY=F": "Russell", "NKD=F": "Nikkei", "GD=F": "TSX",
  "ZB=F": "T-Bond", "ZN=F": "10Y Note", "ZF=F": "5Y Note", "ZT=F": "2Y Note",
  "EURUSD=X": "EUR/USD", "GBPUSD=X": "GBP/USD", "USDJPY=X": "USD/JPY",
  "AUDUSD=X": "AUD/USD", "USDCAD=X": "USD/CAD", "USDCHF=X": "USD/CHF", "USDINR=X": "USD/INR",
  "BTC-USD": "Bitcoin", "ETH-USD": "Ethereum", "BNB-USD": "BNB",
  "SOL-USD": "Solana", "XRP-USD": "XRP", "ADA-USD": "Cardano",
};

function SentimentBadge({ score }) {
  if (score === null || score === undefined || score === 0) return null;
  const abs = Math.abs(score);
  if (abs < 0.05) return null;
  const positive = score > 0;
  return (
    <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded border flex items-center gap-0.5 ${
      positive
        ? "text-emerald-400 border-emerald-500/30 bg-emerald-500/10"
        : "text-red-400 border-red-500/30 bg-red-500/10"
    }`}>
      {positive ? <TrendingUp size={9} /> : <TrendingDown size={9} />}
      {score > 0 ? "+" : ""}{score.toFixed(2)}
    </span>
  );
}

function ImpactPanel({ impact }) {
  const [tab, setTab] = useState("stocks");
  if (!impact) return null;

  const items = tab === "stocks" ? impact.stocks : impact.futures;

  return (
    <div className="bg-card border border-border rounded-xl p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Zap size={14} className="text-yellow-400" />
          <span className="text-sm font-semibold">News Impact (24h)</span>
          <span className="text-xs text-slate-600">{impact.total_articles} articles</span>
        </div>
        <div className="flex gap-1">
          {["stocks", "futures"].map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`text-xs px-2.5 py-1 rounded transition-colors ${
                tab === t
                  ? t === "futures"
                    ? "bg-orange-500/20 text-orange-400 border border-orange-500/30"
                    : "bg-accent/20 text-accent border border-accent/30"
                  : "text-slate-500 hover:text-slate-300"
              }`}
            >
              {t === "futures" ? "Futures" : "Stocks"}
            </button>
          ))}
        </div>
      </div>

      {items?.length === 0 ? (
        <p className="text-xs text-slate-600 text-center py-4">No mentions yet — crawler runs hourly</p>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-2">
          {items?.slice(0, 15).map((item) => {
            const sentColor =
              item.avg_sentiment > 0.05 ? "text-emerald-400" :
              item.avg_sentiment < -0.05 ? "text-red-400" : "text-slate-500";
            const isFut = tab === "futures";
            return (
              <div
                key={item.symbol}
                className={`rounded-lg border p-2.5 ${
                  isFut
                    ? "border-orange-500/20 bg-orange-500/5"
                    : "border-border bg-surface"
                }`}
              >
                <div className={`text-xs font-mono font-bold ${isFut ? "text-orange-400" : "text-accent"}`}>
                  {isFut ? (FUTURES_NAMES[item.symbol] || item.symbol) : item.symbol}
                </div>
                <div className="text-[10px] text-slate-500 mt-0.5">{item.mentions} articles</div>
                <div className={`text-[10px] font-mono mt-0.5 ${sentColor}`}>
                  {item.avg_sentiment >= 0 ? "+" : ""}{item.avg_sentiment.toFixed(2)} sentiment
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

export default function NewsPage() {
  const navigate = useNavigate();
  const [filter, setFilter] = useState("all"); // all | stocks | futures

  const { data: feed = [], isLoading, refetch } = useQuery({
    queryKey: ["news-feed"],
    queryFn: () => api("/api/news/feed?limit=100"),
    refetchInterval: 120_000,
  });

  const { data: impact } = useQuery({
    queryKey: ["news-impact"],
    queryFn: () => api("/api/news/impact?hours=24"),
    refetchInterval: 300_000,
  });

  const filtered = feed.filter((n) => {
    if (filter === "stocks")  return n.ticker_mentions?.length > 0;
    if (filter === "futures") return n.futures_mentions?.length > 0;
    return true;
  });

  const sources = [...new Set(feed.map((n) => n.source).filter(Boolean))];

  return (
    <div className="p-6 space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold">News Intelligence</h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Reuters · Yahoo Finance · MarketWatch · StockTwits · ET · Moneycontrol
          </p>
        </div>
        <button
          onClick={() => refetch()}
          className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-300 transition-colors"
        >
          <RefreshCw size={12} /> Refresh
        </button>
      </div>

      {/* Impact panel */}
      <ImpactPanel impact={impact} />

      {/* Filters */}
      <div className="flex items-center gap-3">
        <div className="flex gap-1">
          {[["all", "All"], ["stocks", "Stocks only"], ["futures", "Futures only"]].map(([val, label]) => (
            <button
              key={val}
              onClick={() => setFilter(val)}
              className={`text-xs px-2.5 py-1 rounded transition-colors ${
                filter === val
                  ? val === "futures"
                    ? "bg-orange-500/20 text-orange-400 border border-orange-500/30"
                    : "bg-accent/20 text-accent border border-accent/30"
                  : "text-slate-500 hover:text-slate-300 border border-transparent"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
        <span className="text-xs text-slate-600">{filtered.length} articles</span>
      </div>

      {/* Source chips */}
      {sources.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {sources.map((s) => (
            <span key={s} className="text-[10px] bg-surface border border-border rounded px-2 py-0.5 text-slate-500">
              {s}
            </span>
          ))}
        </div>
      )}

      {/* Article list */}
      {isLoading ? (
        <div className="text-center py-16 text-slate-600">Loading…</div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-16 text-slate-600">
          <Newspaper size={32} className="mx-auto mb-3 opacity-30" />
          <p className="text-sm">No articles yet</p>
          <p className="text-xs mt-1">News crawler runs every hour.</p>
        </div>
      ) : (
        <div className="space-y-2">
          {filtered.map((n, i) => (
            <div key={i} className="bg-card border border-border rounded-xl p-4 hover:border-accent/40 transition-colors">
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <a
                    href={n.url}
                    target="_blank"
                    rel="noreferrer"
                    className="text-sm font-medium hover:text-accent transition-colors leading-snug"
                  >
                    {n.headline}
                  </a>
                  <div className="flex items-center gap-3 mt-1.5 flex-wrap">
                    <span className="text-[10px] text-slate-600">{n.source}</span>
                    <span className="text-[10px] text-slate-700">
                      {n.published_at?.slice(0, 16).replace("T", " ")}
                    </span>
                    <SentimentBadge score={n.sentiment_score} />
                  </div>
                </div>

                {/* Stock + futures tags */}
                <div className="flex flex-col gap-1 shrink-0 max-w-[180px] items-end">
                  {/* Stock tickers — blue/accent */}
                  {n.ticker_mentions?.length > 0 && (
                    <div className="flex flex-wrap gap-1 justify-end">
                      {n.ticker_mentions.slice(0, 4).map((tick) => (
                        <button
                          key={tick}
                          onClick={() => navigate(`/stocks/stock/${tick}`)}
                          className="text-[10px] font-mono bg-accent/10 text-accent border border-accent/20 rounded px-1.5 py-0.5 hover:bg-accent/20 transition-colors"
                        >
                          {tick}
                        </button>
                      ))}
                      {n.ticker_mentions.length > 4 && (
                        <span className="text-[10px] text-slate-600">+{n.ticker_mentions.length - 4}</span>
                      )}
                    </div>
                  )}
                  {/* Futures instruments — orange */}
                  {n.futures_mentions?.length > 0 && (
                    <div className="flex flex-wrap gap-1 justify-end">
                      {n.futures_mentions.slice(0, 3).map((sym) => (
                        <button
                          key={sym}
                          onClick={() => navigate("/futures")}
                          className="text-[10px] font-mono bg-orange-500/10 text-orange-400 border border-orange-500/20 rounded px-1.5 py-0.5 hover:bg-orange-500/20 transition-colors"
                          title={sym}
                        >
                          {FUTURES_NAMES[sym] || sym}
                        </button>
                      ))}
                      {n.futures_mentions.length > 3 && (
                        <span className="text-[10px] text-slate-600">+{n.futures_mentions.length - 3}</span>
                      )}
                    </div>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
