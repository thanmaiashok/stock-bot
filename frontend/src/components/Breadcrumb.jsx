import { useLocation, useNavigate } from "react-router-dom";
import { ChevronRight, Home } from "lucide-react";

const LABELS = {
  stocks:       "Stocks",
  futures:      "Futures",
  signals:      "Signals",
  portfolio:    "Portfolio",
  screener:     "Screener",
  watchlist:    "Watchlist",
  graph:        "Graph",
  news:         "News",
  sectors:      "Sectors",
  map:          "Intel Map",
  correlations: "Correlations",
  positions:    "Positions",
  history:      "Trade Log",
  predictions:  "Predictions",
  stock:        null, // skip — next segment is ticker
};

export default function Breadcrumb() {
  const location = useLocation();
  const navigate  = useNavigate();
  const parts     = location.pathname.split("/").filter(Boolean);

  const crumbs = [];
  let path = "";
  let skipNext = false;

  for (let i = 0; i < parts.length; i++) {
    const seg = parts[i];
    path += `/${seg}`;

    if (skipNext) {
      // previous was "stock" — this is the ticker
      crumbs.push({ label: seg.toUpperCase(), path, clickable: true });
      skipNext = false;
      continue;
    }

    if (seg === "stock") {
      skipNext = true;
      continue; // skip "stock" segment itself
    }

    const label = LABELS[seg];
    if (label === null) continue; // explicitly hidden
    const displayLabel = label ?? seg;

    // Index routes (stocks, futures with no child) get "Dashboard" / "Markets" label
    const isBase = (seg === "stocks" || seg === "futures") && parts.length === 1;
    crumbs.push({
      label: isBase ? (seg === "stocks" ? "Dashboard" : "Markets") : displayLabel,
      path,
      clickable: i < parts.length - 1, // last crumb not clickable
    });
  }

  if (!crumbs.length) return null;

  return (
    <nav className="flex items-center gap-1 px-4 py-2 border-b border-border bg-card/30 text-xs text-slate-500 shrink-0">
      <button
        onClick={() => navigate("/")}
        className="hover:text-slate-300 transition-colors flex items-center gap-1"
      >
        <Home size={11} />
      </button>
      {crumbs.map((crumb, i) => (
        <span key={crumb.path} className="flex items-center gap-1">
          <ChevronRight size={10} className="text-slate-700" />
          {crumb.clickable ? (
            <button
              onClick={() => navigate(crumb.path)}
              className="hover:text-slate-300 transition-colors"
            >
              {crumb.label}
            </button>
          ) : (
            <span className="text-slate-300 font-medium">{crumb.label}</span>
          )}
        </span>
      ))}
    </nav>
  );
}
