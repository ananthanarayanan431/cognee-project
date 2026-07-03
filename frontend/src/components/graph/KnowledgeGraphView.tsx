// frontend/src/components/graph/KnowledgeGraphView.tsx
"use client";
import { useEffect, useRef } from "react";
import * as d3 from "d3";
import { KnowledgeGraphData, KnowledgeGraphNode } from "@/types";

// Distinct vocabulary from BrainGraph's weakness/strength/mastered/topic —
// this renders Cognee's raw typed graph, not the Postgres-derived mastery view.
const NODE_COLOR: Record<string, string> = {
  // Typed add_data_points() anchors (debatemind/cognee/schema.py)
  UserProfile: "#0d0d0d",
  Topic: "#1e3a5f",
  ArgumentRecord: "#C0392B",
  SessionSummary: "#8e44ad",
  PersonalFact: "#27AE60",
  // Cognify's prose-derived entity web (add() -> cognify())
  TextDocument: "#2c3e50",
  DocumentChunk: "#34495e",
  TextSummary: "#16a085",
  Entity: "#2980B9",
  EntityType: "#D4AC0D",
  Node: "#555",
};

const NODE_R: Record<string, number> = {
  UserProfile: 26,
  Topic: 18,
  ArgumentRecord: 11,
  SessionSummary: 13,
  PersonalFact: 11,
  TextDocument: 15,
  DocumentChunk: 9,
  TextSummary: 12,
  Entity: 9,
  EntityType: 14,
  Node: 8,
};

type SimNode = KnowledgeGraphNode & d3.SimulationNodeDatum;
type SimLink = { source: string; target: string; label: string } & d3.SimulationLinkDatum<SimNode>;

export default function KnowledgeGraphView({ data }: { data: KnowledgeGraphData }) {
  const svgRef = useRef<SVGSVGElement>(null);
  const tooltipRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;

    const W = svg.clientWidth || 600;
    const H = svg.clientHeight || 500;

    const nodes: SimNode[] = data.nodes.map((n) => ({ ...n }));
    const links: SimLink[] = data.edges.map((e) => ({ ...e }));

    const sel = d3.select(svg);
    sel.selectAll("*").remove();

    const g = sel.append("g");
    sel.call(
      d3.zoom<SVGSVGElement, unknown>()
        .scaleExtent([0.3, 3])
        .on("zoom", (ev) => g.attr("transform", ev.transform))
    );

    const link = g
      .append("g")
      .selectAll<SVGLineElement, SimLink>("line")
      .data(links)
      .join("line")
      .attr("stroke", "rgba(255,255,255,0.15)")
      .attr("stroke-width", 1);

    const node = g
      .append("g")
      .selectAll<SVGGElement, SimNode>("g")
      .data(nodes)
      .join("g")
      .attr("cursor", "grab");

    node.call(
      d3.drag<SVGGElement, SimNode>()
        .on("start", (ev, d) => {
          if (!ev.active) sim.alphaTarget(0.3).restart();
          d.fx = d.x;
          d.fy = d.y;
        })
        .on("drag", (ev, d) => {
          d.fx = ev.x;
          d.fy = ev.y;
        })
        .on("end", (ev, d) => {
          if (!ev.active) sim.alphaTarget(0);
          d.fx = null;
          d.fy = null;
        })
    );

    node
      .append("circle")
      .attr("r", (d) => NODE_R[d.type] ?? 10)
      .attr("fill", (d) => NODE_COLOR[d.type] ?? "#555")
      .attr("stroke", "rgba(255,255,255,0.2)")
      .attr("stroke-width", 1);

    // Persistent label below each node (mirrors BrainGraph) so the graph is
    // readable at a glance rather than only on hover.
    node
      .append("text")
      .attr("text-anchor", "middle")
      .attr("dominant-baseline", "hanging")
      .attr("y", (d) => (NODE_R[d.type] ?? 10) + 3)
      .attr("fill", "rgba(255,255,255,0.6)")
      .attr("font-size", "7")
      .attr("font-family", "Inter, system-ui, sans-serif")
      .attr("pointer-events", "none")
      .text((d) => (d.label.length > 16 ? d.label.slice(0, 15) + "…" : d.label));

    const tt = tooltipRef.current;
    node
      .on("mouseenter", (ev, d) => {
        if (!tt) return;
        tt.textContent = `${d.label} (${d.type})`;
        tt.style.opacity = "1";
        tt.style.left = ev.pageX + 14 + "px";
        tt.style.top = ev.pageY - 10 + "px";
      })
      .on("mousemove", (ev) => {
        if (!tt) return;
        tt.style.left = ev.pageX + 14 + "px";
        tt.style.top = ev.pageY - 10 + "px";
      })
      .on("mouseleave", () => {
        if (tt) tt.style.opacity = "0";
      });

    const sim = d3
      .forceSimulation<SimNode>(nodes)
      .force(
        "link",
        d3
          .forceLink<SimNode, SimLink>(links)
          .id((d) => d.id)
          .distance(70)
      )
      .force("charge", d3.forceManyBody<SimNode>().strength(-120))
      .force("center", d3.forceCenter(W / 2, H / 2))
      .force(
        "collision",
        d3.forceCollide<SimNode>((d) => (NODE_R[d.type] ?? 10) + 4)
      );

    sim.on("tick", () => {
      link
        .attr("x1", (d) => (d.source as unknown as SimNode).x ?? 0)
        .attr("y1", (d) => (d.source as unknown as SimNode).y ?? 0)
        .attr("x2", (d) => (d.target as unknown as SimNode).x ?? 0)
        .attr("y2", (d) => (d.target as unknown as SimNode).y ?? 0);
      node.attr("transform", (d) => `translate(${d.x ?? 0},${d.y ?? 0})`);
    });

    return () => {
      sim.stop();
    };
  }, [data]);

  if (!data.nodes.length) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center gap-3 p-8">
        <span className="text-4xl opacity-20">🕸️</span>
        <p className="font-sans text-[12px] text-white/30 text-center leading-relaxed">
          No knowledge graph yet.
          <br />
          Start debating to grow it.
        </p>
      </div>
    );
  }

  return (
    <div className="relative flex-1 w-full h-full">
      <svg ref={svgRef} width="100%" height="100%" style={{ display: "block" }} />
      <div
        ref={tooltipRef}
        className="fixed z-[200] pointer-events-none px-2.5 py-1.5 rounded-md bg-[#1c1c1c] border border-white/15 font-sans text-[11px] text-white/80 shadow-lg transition-opacity duration-100"
        style={{ opacity: 0 }}
      />
    </div>
  );
}
