import { Routes, Route } from "react-router-dom";
import Landing from "./pages/Landing";
import StocksShell from "./pages/StocksShell";
import FuturesShell from "./pages/FuturesShell";
import FuturesMarkets from "./pages/FuturesMarkets";
import FuturesPositions from "./pages/FuturesPositions";
import FuturesHistory from "./pages/FuturesHistory";
import FuturesAI from "./pages/FuturesAI";
import FuturesAnalytics from "./pages/FuturesAnalytics";
import Dashboard from "./pages/Dashboard";
import SignalFeed from "./pages/SignalFeed";
import StockDetail from "./pages/StockDetail";
import Portfolio from "./pages/Portfolio";
import Backtester from "./pages/Backtester";
import NewsPage from "./pages/NewsPage";
import DiscoverPage from "./pages/DiscoverPage";
// Legacy deep-link routes (still accessible via direct URL or stock detail links)
import GraphExplorer from "./pages/GraphExplorer";
import Screener from "./pages/Screener";
import PatternsPage from "./pages/PatternsPage";
import TopKPage from "./pages/TopKPage";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />

      <Route path="/stocks" element={<StocksShell />}>
        <Route index element={<Dashboard />} />
        <Route path="signals" element={<SignalFeed />} />
        <Route path="stock/:ticker" element={<StockDetail />} />
        <Route path="portfolio" element={<Portfolio />} />
        <Route path="discover" element={<DiscoverPage />} />
        <Route path="backtest" element={<Backtester />} />
        <Route path="news" element={<NewsPage />} />
        {/* Legacy routes — still reachable via direct URL */}
        <Route path="screener" element={<Screener />} />
        <Route path="graph" element={<GraphExplorer />} />
        <Route path="patterns" element={<PatternsPage />} />
        <Route path="topk" element={<TopKPage />} />
      </Route>

      <Route path="/futures" element={<FuturesShell />}>
        <Route index element={<FuturesMarkets />} />
        <Route path="ai" element={<FuturesAI />} />
        <Route path="positions" element={<FuturesPositions />} />
        <Route path="history" element={<FuturesHistory />} />
        <Route path="analytics" element={<FuturesAnalytics />} />
        {/* Legacy routes */}
        <Route path="brain" element={<FuturesAI />} />
        <Route path="predictions" element={<FuturesAI />} />
        <Route path="map" element={<FuturesAnalytics />} />
        <Route path="heatmap" element={<FuturesAnalytics />} />
        <Route path="correlations" element={<FuturesAnalytics />} />
      </Route>
    </Routes>
  );
}
