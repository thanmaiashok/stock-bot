import { useEffect, useRef } from "react";

export default function CorrelationGraph({ nodes = [], links = [] }) {
  const containerRef = useRef(null);
  const graphRef = useRef(null);

  useEffect(() => {
    if (!nodes.length || !containerRef.current) return;

    // Dynamically import to avoid SSR issues
    import("react-force-graph-2d").then(({ default: ForceGraph2D }) => {
      // Already mounted — skip re-mount
      if (graphRef.current) return;

      const { createRoot } = require("react-dom/client");
      const root = createRoot(containerRef.current);
      graphRef.current = root;

      const graphData = {
        nodes: nodes.map((n) => ({ id: n.ticker, name: n.name || n.ticker, weight: n.weight || 1 })),
        links: links.map((l) => ({ source: l.source, target: l.target, value: l.weight || 0.5 })),
      };

      root.render(
        <ForceGraph2D
          graphData={graphData}
          width={containerRef.current.clientWidth}
          height={400}
          backgroundColor="#1a1d27"
          nodeLabel="name"
          nodeColor={() => "#6366f1"}
          nodeRelSize={5}
          linkColor={() => "#2a2d3e"}
          linkWidth={(l) => (l.value || 0.5) * 3}
          nodeCanvasObject={(node, ctx, globalScale) => {
            const label = node.id;
            const fontSize = 10 / globalScale;
            ctx.font = `${fontSize}px Sans-Serif`;
            ctx.fillStyle = "#6366f1";
            ctx.beginPath();
            ctx.arc(node.x, node.y, 5, 0, 2 * Math.PI);
            ctx.fill();
            ctx.fillStyle = "#e2e8f0";
            ctx.textAlign = "center";
            ctx.textBaseline = "middle";
            ctx.fillText(label, node.x, node.y + 9);
          }}
        />
      );
    });

    return () => {
      if (graphRef.current) {
        graphRef.current.unmount();
        graphRef.current = null;
      }
    };
  }, [nodes, links]);

  if (!nodes.length) {
    return (
      <div className="h-64 flex items-center justify-center text-slate-600 text-sm">
        No correlation data yet. Run the graph update job first.
      </div>
    );
  }

  return <div ref={containerRef} className="w-full rounded-lg overflow-hidden" />;
}
