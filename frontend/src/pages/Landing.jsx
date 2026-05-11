import { useNavigate } from "react-router-dom";
import { TrendingUp, Flame, BarChart2, Activity } from "lucide-react";

export default function Landing() {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen bg-surface flex flex-col items-center justify-center p-8">
      <div className="text-center mb-10">
        <div className="flex items-center justify-center gap-3 mb-3">
          <Activity className="text-accent" size={32} />
          <h1 className="text-4xl font-bold tracking-tight">StockBot</h1>
        </div>
        <p className="text-slate-400 text-sm">AI-powered paper trading · Choose your market</p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-6 w-full max-w-2xl">
        {/* Stocks */}
        <button
          onClick={() => navigate("/stocks")}
          className="group bg-card border border-border rounded-2xl p-8 text-left
                     hover:border-accent hover:bg-accent/5 transition-all duration-200 cursor-pointer"
        >
          <div className="w-12 h-12 bg-accent/10 rounded-xl flex items-center justify-center mb-5
                          group-hover:bg-accent/20 transition-colors">
            <TrendingUp className="text-accent" size={24} />
          </div>
          <h2 className="text-xl font-bold mb-2">Stocks</h2>
          <p className="text-slate-400 text-sm leading-relaxed">
            Equity markets · NASDAQ + NSE · AI signals · Long-term &amp; day trading
          </p>
          <div className="mt-4 flex gap-2 flex-wrap">
            {["AAPL", "MSFT", "TCS.NS", "RELIANCE.NS"].map((t) => (
              <span key={t} className="text-xs bg-surface px-2 py-0.5 rounded text-slate-500">{t}</span>
            ))}
          </div>
          <div className="mt-6 flex items-center gap-1 text-accent text-sm font-medium">
            Enter Stocks <span className="group-hover:translate-x-1 transition-transform inline-block">→</span>
          </div>
        </button>

        {/* Futures */}
        <button
          onClick={() => navigate("/futures")}
          className="group bg-card border border-border rounded-2xl p-8 text-left
                     hover:border-orange-500 hover:bg-orange-500/5 transition-all duration-200 cursor-pointer"
        >
          <div className="w-12 h-12 bg-orange-500/10 rounded-xl flex items-center justify-center mb-5
                          group-hover:bg-orange-500/20 transition-colors">
            <Flame className="text-orange-400" size={24} />
          </div>
          <h2 className="text-xl font-bold mb-2">Futures &amp; Commodities</h2>
          <p className="text-slate-400 text-sm leading-relaxed">
            Gold, Oil, Silver, Crypto · 10× leverage · Fast signals · Long &amp; Short
          </p>
          <div className="mt-4 flex gap-2 flex-wrap">
            {["Gold", "WTI Oil", "Bitcoin", "Nat Gas"].map((t) => (
              <span key={t} className="text-xs bg-surface px-2 py-0.5 rounded text-slate-500">{t}</span>
            ))}
          </div>
          <div className="mt-6 flex items-center gap-1 text-orange-400 text-sm font-medium">
            Enter Futures <span className="group-hover:translate-x-1 transition-transform inline-block">→</span>
          </div>
        </button>
      </div>

      <p className="text-xs text-slate-700 mt-10">Paper trading only · No real money · For educational purposes</p>
    </div>
  );
}
