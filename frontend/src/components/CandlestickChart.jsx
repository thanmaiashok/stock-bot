/**
 * Real candlestick chart using TradingView lightweight-charts.
 * github.com/tradingview/lightweight-charts
 * Proper OHLC candles + volume histogram + crosshair + auto-resize.
 */
import { useEffect, useRef } from "react";
import { createChart, ColorType, CrosshairMode } from "lightweight-charts";

const THEME = {
  bg:          "#0b0e18",
  grid:        "#1a1f2e",
  border:      "#1e293b",
  text:        "#64748b",
  upColor:     "#22c55e",
  downColor:   "#ef4444",
  upWick:      "#22c55e",
  downWick:    "#ef4444",
};

export default function CandlestickChart({ data = [], height = 300 }) {
  const containerRef = useRef(null);
  const chartRef     = useRef(null);
  const candleRef    = useRef(null);
  const volRef       = useRef(null);

  // Create chart once on mount
  useEffect(() => {
    if (!containerRef.current) return;

    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: THEME.bg },
        textColor: THEME.text,
        fontFamily: "'Inter', 'ui-monospace', monospace",
        fontSize: 11,
      },
      grid: {
        vertLines: { color: THEME.grid },
        horzLines: { color: THEME.grid },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: "#475569", labelBackgroundColor: "#1e293b" },
        horzLine: { color: "#475569", labelBackgroundColor: "#1e293b" },
      },
      rightPriceScale: {
        borderColor: THEME.border,
        scaleMargins: { top: 0.1, bottom: 0.25 },
      },
      timeScale: {
        borderColor: THEME.border,
        timeVisible: true,
        secondsVisible: false,
        fixLeftEdge: true,
        fixRightEdge: true,
      },
      handleScroll: true,
      handleScale: true,
    });

    // Candlestick series
    const candles = chart.addCandlestickSeries({
      upColor:          THEME.upColor,
      downColor:        THEME.downColor,
      wickUpColor:      THEME.upWick,
      wickDownColor:    THEME.downWick,
      borderUpColor:    THEME.upColor,
      borderDownColor:  THEME.downColor,
      priceLineVisible: true,
      priceLineColor:   "#475569",
    });

    // Volume histogram (separate pane-like scale using scaleMargins)
    const volume = chart.addHistogramSeries({
      priceFormat: { type: "volume" },
      priceScaleId: "vol",
      color: "#22c55e44",
    });
    chart.priceScale("vol").applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
    });

    chartRef.current  = chart;
    candleRef.current = candles;
    volRef.current    = volume;

    // Auto-resize with ResizeObserver
    const ro = new ResizeObserver(entries => {
      const { width } = entries[0].contentRect;
      chart.applyOptions({ width });
    });
    ro.observe(containerRef.current);

    return () => {
      ro.disconnect();
      chart.remove();
    };
  }, []);

  // Update data when prop changes
  useEffect(() => {
    if (!candleRef.current || !volRef.current || !data.length) return;

    const toTime = (raw = "") => {
      const s = String(raw).replace(" ", "T");
      // midnight timestamps (T00:00:00) = daily data → yyyy-mm-dd only
      const isTrulyIntraday = s.includes("T") && !s.match(/T00:00:00/);
      return isTrulyIntraday ? s.slice(0, 19) : s.slice(0, 10);
    };

    const seen = new Map();
    data
      .filter(d => d.close)
      .forEach(d => {
        const c = Number(d.close);
        const o = d.open  ? Number(d.open)  : c;
        const h = d.high  ? Number(d.high)  : c;
        const l = d.low   ? Number(d.low)   : c;
        const time = toTime(d.date ?? d.time);
        if (time) seen.set(time, { time, open: o, high: Math.max(o, h, c), low: Math.min(o, l, c), close: c });
      });
    const candleData = Array.from(seen.values()).sort((a, b) => (a.time > b.time ? 1 : -1));

    const volData = Array.from(new Map(
      data
        .filter(d => d.close && d.volume != null && Number(d.volume) > 0)
        .map(d => {
          const time = toTime(d.date ?? d.time);
          return [time, { time, value: Number(d.volume), color: Number(d.close) >= Number(d.open) ? "#22c55e33" : "#ef444433" }];
        })
    ).values()).sort((a, b) => (a.time > b.time ? 1 : -1));

    candleRef.current.setData(candleData);
    volRef.current.setData(volData);
    chartRef.current?.timeScale().fitContent();
  }, [data]);

  return (
    <div style={{ position: "relative", width: "100%", height }}>
      <div
        ref={containerRef}
        style={{ width: "100%", height: "100%" }}
        className="rounded-lg overflow-hidden"
      />
      {!data.length && (
        <div
          style={{ position: "absolute", inset: 0 }}
          className="flex items-center justify-center text-slate-600 text-sm"
        >
          No price data available
        </div>
      )}
    </div>
  );
}
