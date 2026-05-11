/**
 * FuturesAI — merged Brain + Predictions into one tabbed page.
 * Cuts 2 nav items → 1.
 */
import { useState } from "react";
import { useOutletContext } from "react-router-dom";
import { Brain, TrendingUp } from "lucide-react";
import FuturesBrain from "./FuturesBrain";
import FuturesPredictions from "./FuturesPredictions";

const TABS = [
  { id: "brain",       label: "AI Brain",    icon: Brain      },
  { id: "predictions", label: "Predictions", icon: TrendingUp },
];

export default function FuturesAI() {
  const [tab, setTab] = useState("brain");
  const ctx = useOutletContext();

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
        {tab === "brain" ? <FuturesBrain /> : <FuturesPredictions />}
      </div>
    </div>
  );
}
