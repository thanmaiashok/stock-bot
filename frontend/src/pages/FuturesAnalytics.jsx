/**
 * FuturesAnalytics — merged Map + Heatmap + Correlations into one tabbed page.
 * Cuts 3 nav items → 1.
 */
import { useState } from "react";
import { Map, Grid, GitBranch } from "lucide-react";
import FuturesMap from "./FuturesMap";
import FuturesHeatmap from "./FuturesHeatmap";
import FuturesCorrelations from "./FuturesCorrelations";

const TABS = [
  { id: "map",          label: "Intel Map",   icon: Map       },
  { id: "heatmap",      label: "Heatmap",     icon: Grid      },
  { id: "correlations", label: "Correlations",icon: GitBranch },
];

export default function FuturesAnalytics() {
  const [tab, setTab] = useState("map");

  return (
    <div className="flex flex-col h-full">
      <div className="flex gap-1 bg-card border-b border-border px-4 pt-3 pb-0">
        {TABS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className={`flex items-center gap-2 px-4 py-2 text-sm border-b-2 transition-colors -mb-px ${
              tab === id
                ? "border-orange-400 text-orange-400"
                : "border-transparent text-slate-500 hover:text-slate-300"
            }`}
          >
            <Icon size={13} />
            {label}
          </button>
        ))}
      </div>
      <div className="flex-1 overflow-y-auto">
        {tab === "map"          && <FuturesMap />}
        {tab === "heatmap"      && <FuturesHeatmap />}
        {tab === "correlations" && <FuturesCorrelations />}
      </div>
    </div>
  );
}
