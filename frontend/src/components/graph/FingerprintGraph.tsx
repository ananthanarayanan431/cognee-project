"use client";
import { useEffect, useRef } from "react";
import * as d3 from "d3";
import { GraphData, GraphNode, GraphEdge } from "@/types";
import { COLORS } from "@/lib/tokens";

const NODE_COLOR: Record<string, string> = {
  weakness: COLORS.scarlet,
  strength: COLORS.verdant,
  mastered: "#444",
  topic: COLORS.slate,
};

type SimNode = GraphNode & d3.SimulationNodeDatum;
type SimLink = Omit<GraphEdge, "source" | "target"> & d3.SimulationLinkDatum<SimNode>;

export default function FingerprintGraph({ data }: { data: GraphData }) {
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    if (!svgRef.current) return;

    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();

    if (!data.nodes.length) return;

    const W = svgRef.current.clientWidth || 320;
    const H = 380;

    const nodes: SimNode[] = data.nodes.map((n) => ({ ...n }));
    const links: SimLink[] = data.edges.map((e) => ({ ...e }));

    const sim = d3
      .forceSimulation<SimNode>(nodes)
      .force(
        "link",
        d3
          .forceLink<SimNode, SimLink>(links)
          .id((d) => d.id)
          .distance(100)
      )
      .force("charge", d3.forceManyBody().strength(-200))
      .force("center", d3.forceCenter(W / 2, H / 2));

    const line = svg
      .append("g")
      .selectAll<SVGLineElement, SimLink>("line")
      .data(links)
      .join("line")
      .attr("stroke", "rgba(255,255,255,0.25)")
      .attr("stroke-width", (d) => d.weight * 2);

    const node = svg
      .append("g")
      .selectAll<SVGGElement, SimNode>("g")
      .data(nodes)
      .join("g")
      .attr("cursor", "pointer");

    node
      .append("circle")
      .attr("r", (d) => 14 + d.weight * 22)
      .attr("fill", (d) => NODE_COLOR[d.type] ?? COLORS.fog);

    node
      .append("text")
      .attr("text-anchor", "middle")
      .attr("dy", "0.35em")
      .attr("fill", "white")
      .attr("font-size", 8)
      .attr("font-family", "Inter")
      .text((d) => (d.label.length > 12 ? d.label.slice(0, 11) + "…" : d.label));

    sim.on("tick", () => {
      line
        .attr("x1", (d) => (d.source as SimNode).x ?? 0)
        .attr("y1", (d) => (d.source as SimNode).y ?? 0)
        .attr("x2", (d) => (d.target as SimNode).x ?? 0)
        .attr("y2", (d) => (d.target as SimNode).y ?? 0);

      node.attr("transform", (d) => `translate(${d.x ?? 0},${d.y ?? 0})`);
    });

    return () => {
      sim.stop();
    };
  }, [data]);

  if (!data.nodes.length) {
    return (
      <div className="flex-1 flex items-center justify-center px-5">
        <p className="font-sans text-[11px] text-[#555] text-center leading-relaxed">
          No graph data yet.
          <br />
          Start debating to build your cognitive fingerprint.
        </p>
      </div>
    );
  }

  return (
    <div className="flex-1 w-full">
      <svg
        ref={svgRef}
        viewBox="0 0 320 380"
        width="100%"
        style={{ display: "block" }}
      />
    </div>
  );
}
