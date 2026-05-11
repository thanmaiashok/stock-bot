import { useState } from "react";
import { Outlet, NavLink, useNavigate } from "react-router-dom";
import { LayoutDashboard, Zap, Briefcase, Compass, FlaskConical, Newspaper, TrendingUp, ArrowLeft, Search } from "lucide-react";
import Breadcrumb from "../components/Breadcrumb";

const navItems = [
  { to: "",          icon: LayoutDashboard, label: "Dashboard", end: true },
  { to: "signals",   icon: Zap,             label: "Signals" },
  { to: "portfolio", icon: Briefcase,       label: "Portfolio" },
  { to: "discover",  icon: Compass,         label: "Discover" },
  { to: "backtest",  icon: FlaskConical,    label: "Backtester" },
  { to: "news",      icon: Newspaper,       label: "News" },
];

export default function StocksShell() {
  const navigate = useNavigate();
  const [search, setSearch] = useState("");

  function handleSearch(e) {
    e.preventDefault();
    const t = search.trim().toUpperCase();
    if (t) { navigate(`/stocks/stock/${t}`); setSearch(""); }
  }

  return (
    <div className="flex h-screen bg-surface overflow-hidden">
      <aside className="w-52 bg-card border-r border-border flex flex-col shrink-0">
        <div className="p-4 border-b border-border">
          <button
            onClick={() => navigate("/")}
            className="flex items-center gap-1 text-xs text-slate-600 hover:text-slate-300 mb-3 transition-colors"
          >
            <ArrowLeft size={12} /> Markets
          </button>
          <div className="flex items-center gap-2">
            <TrendingUp className="text-accent" size={20} />
            <span className="font-bold text-base tracking-tight">Stocks</span>
          </div>
          <form onSubmit={handleSearch} className="mt-3">
            <div className="flex items-center gap-1.5 bg-surface border border-border rounded-lg px-2 py-1.5">
              <Search size={11} className="text-slate-600 shrink-0" />
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search ticker…"
                className="bg-transparent text-xs flex-1 outline-none text-slate-300 placeholder:text-slate-600"
              />
            </div>
          </form>
        </div>

        <nav className="flex-1 p-2 space-y-0.5">
          {navItems.map(({ to, icon: Icon, label, end }) => (
            <NavLink
              key={label}
              to={to}
              end={end}
              className={({ isActive }) =>
                `flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-colors ${
                  isActive ? "bg-accent text-white" : "text-slate-400 hover:text-white hover:bg-white/5"
                }`
              }
            >
              <Icon size={15} />
              {label}
            </NavLink>
          ))}
        </nav>

        <div className="p-3 border-t border-border">
          <p className="text-[10px] text-slate-700">Paper trading only</p>
        </div>
      </aside>

      <main className="flex-1 overflow-hidden flex flex-col">
        <Breadcrumb />
        <div className="flex-1 overflow-y-auto">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
