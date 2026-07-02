"use client";
import { useEffect, useRef, useState, useCallback } from "react";
import * as d3 from "d3";
import { GraphData, GraphNode } from "@/types";
import { COLORS } from "@/lib/tokens";

// ── types ────────────────────────────────────────────────────────────────────

interface SimNode extends d3.SimulationNodeDatum {
  id: string;
  label: string;
  type: string;
  weight: number;
  parentId?: string;
}

interface SimLink extends d3.SimulationLinkDatum<SimNode> {
  weight: number;
}

// ── constants ─────────────────────────────────────────────────────────────────

const NODE_COLOR: Record<string, string> = {
  root:     "#0d0d0d",
  topic:    "#1e3a5f",
  weakness: COLORS.scarlet,
  strength: COLORS.verdant,
  mastered: "#3a3a3a",
};

const NODE_BORDER: Record<string, string> = {
  root:     "#ffffff44",
  topic:    "#3b82f6aa",
  weakness: COLORS.scarlet + "88",
  strength: COLORS.verdant + "88",
  mastered: "#666",
};

const NODE_R: Record<string, number> = {
  root:     32,
  topic:    20,
  weakness: 13,
  strength: 13,
  mastered: 11,
};

const PATTERN_ICON: Record<string, string> = {
  EvidenceBased:    "📊",
  AppealToAuthority:"👑",
  StrawMan:         "🎭",
  AdHominem:        "⚡",
  SlipperySlope:    "⚠️",
  FalseEquivalence: "⚖️",
  EmotionalAppeal:  "❤️",
  AnecdotalEvidence:"📖",
  Concession:       "🏳️",
};

// ── component ─────────────────────────────────────────────────────────────────

export default function BrainGraph({ data }: { data: GraphData }) {
  const svgRef     = useRef<SVGSVGElement>(null);
  const simRef     = useRef<d3.Simulation<SimNode, SimLink> | null>(null);
  const posRef     = useRef<Map<string, { x: number; y: number }>>(new Map());
  const tooltipRef = useRef<HTMLDivElement>(null);

  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  // Build child→parent map once from edge list
  const parentOf = useCallback((): Record<string, string> => {
    const m: Record<string, string> = {};
    for (const e of data.edges) m[e.target as string] = e.source as string;
    return m;
  }, [data.edges]);

  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;

    // Save positions from previous sim before teardown
    simRef.current?.nodes().forEach((n) => {
      if (n.x != null && n.y != null) posRef.current.set(n.id, { x: n.x, y: n.y });
    });
    simRef.current?.stop();

    const W = svg.clientWidth  || 600;
    const H = svg.clientHeight || 500;

    // Determine which nodes are visible
    const pOf = parentOf();
    const visibleIds = new Set<string>();
    for (const n of data.nodes) {
      if (n.type === "root" || n.type === "topic") visibleIds.add(n.id);
    }
    for (const n of data.nodes) {
      if (n.type !== "root" && n.type !== "topic") {
        const pid = pOf[n.id];
        if (pid && expanded.has(pid)) visibleIds.add(n.id);
      }
    }

    const nodeById = new Map<string, GraphNode>(data.nodes.map((n) => [n.id, n]));

    const simNodes: SimNode[] = Array.from(visibleIds).reduce<SimNode[]>((acc, id) => {
      const n = nodeById.get(id);
      if (!n) return acc;
      const saved  = posRef.current.get(id);
      const psaved = posRef.current.get(pOf[id] ?? "");
      acc.push({
        ...n,
        parentId: pOf[id],
        x: saved?.x ?? psaved?.x ?? W / 2 + (Math.random() - 0.5) * 30,
        y: saved?.y ?? psaved?.y ?? H / 2 + (Math.random() - 0.5) * 30,
        vx: 0,
        vy: 0,
      });
      return acc;
    }, []);

    const simLinks: SimLink[] = data.edges
      .filter((e) => visibleIds.has(e.source as string) && visibleIds.has(e.target as string))
      .map((e) => ({ source: e.source, target: e.target, weight: e.weight }));

    // ── build SVG ──────────────────────────────────────────────────────────

    const sel = d3.select(svg);
    sel.selectAll("*").remove();

    // Defs: glow filter + clip
    const defs = sel.append("defs");
    const glow = defs.append("filter").attr("id", "bg-glow").attr("x", "-50%").attr("y", "-50%").attr("width", "200%").attr("height", "200%");
    glow.append("feGaussianBlur").attr("in", "SourceGraphic").attr("stdDeviation", "6").attr("result", "blur");
    const merge = glow.append("feMerge");
    merge.append("feMergeNode").attr("in", "blur");
    merge.append("feMergeNode").attr("in", "SourceGraphic");

    const topicGlow = defs.append("filter").attr("id", "topic-glow").attr("x", "-80%").attr("y", "-80%").attr("width", "260%").attr("height", "260%");
    topicGlow.append("feGaussianBlur").attr("in", "SourceGraphic").attr("stdDeviation", "4").attr("result", "blur");
    const tm = topicGlow.append("feMerge");
    tm.append("feMergeNode").attr("in", "blur");
    tm.append("feMergeNode").attr("in", "SourceGraphic");

    // Root container (supports zoom/pan)
    const g = sel.append("g");
    sel.call(
      d3.zoom<SVGSVGElement, unknown>()
        .scaleExtent([0.4, 2.5])
        .on("zoom", (ev) => g.attr("transform", ev.transform))
    );

    // Links layer
    const linkG = g.append("g");
    const link = linkG
      .selectAll<SVGLineElement, SimLink>("line")
      .data(simLinks)
      .join("line")
      .attr("stroke", "rgba(255,255,255,0.12)")
      .attr("stroke-width", (d) => Math.max(1, d.weight * 2.5))
      .attr("stroke-dasharray", (d) => {
        const src = nodeById.get((d.source as SimNode).id ?? (d.source as string));
        return src?.type === "topic" ? "4,3" : "none";
      });

    // Nodes layer
    const nodeG = g.append("g");
    const node = nodeG
      .selectAll<SVGGElement, SimNode>("g")
      .data(simNodes)
      .join("g")
      .attr("cursor", (d) => (d.type === "topic" ? "pointer" : "grab"));

    // Drag
    node.call(
      d3.drag<SVGGElement, SimNode>()
        .on("start", (ev, d) => {
          if (!ev.active) sim.alphaTarget(0.3).restart();
          d.fx = d.x; d.fy = d.y;
        })
        .on("drag", (ev, d) => { d.fx = ev.x; d.fy = ev.y; })
        .on("end", (ev, d) => {
          if (!ev.active) sim.alphaTarget(0);
          if (d.type !== "root") { d.fx = null; d.fy = null; }
        })
    );

    // Outer glow ring on root
    node.filter((d) => d.type === "root")
      .append("circle")
      .attr("r", NODE_R.root + 10)
      .attr("fill", "rgba(255,255,255,0.03)")
      .attr("stroke", "rgba(255,255,255,0.06)")
      .attr("stroke-width", 1);

    // Expand indicator ring on topics
    node.filter((d) => d.type === "topic")
      .append("circle")
      .attr("r", NODE_R.topic + 6)
      .attr("fill", "none")
      .attr("stroke", (d) => (expanded.has(d.id) ? "#3b82f6" : "rgba(255,255,255,0.08)"))
      .attr("stroke-width", 1.5)
      .attr("stroke-dasharray", "3,2");

    // Main circle
    node.append("circle")
      .attr("r", (d) => NODE_R[d.type] ?? 12)
      .attr("fill", (d) => NODE_COLOR[d.type] ?? "#333")
      .attr("stroke", (d) => NODE_BORDER[d.type] ?? "#555")
      .attr("stroke-width", (d) => (d.type === "root" ? 2 : 1.5))
      .attr("filter", (d) => (d.type === "root" ? "url(#bg-glow)" : d.type === "topic" ? "url(#topic-glow)" : null));

    // Icon / label text
    node.append("text")
      .attr("text-anchor", "middle")
      .attr("dominant-baseline", "central")
      .attr("fill", "white")
      .attr("font-size", (d) => {
        if (d.type === "root")  return "18";
        if (d.type === "topic") return "7";
        return "10";
      })
      .attr("font-family", "Inter, system-ui, sans-serif")
      .attr("pointer-events", "none")
      .text((d) => {
        if (d.type === "root")  return "🧠";
        if (d.type === "topic") return d.label.length > 14 ? d.label.slice(0, 13) + "…" : d.label;
        return PATTERN_ICON[d.label] ?? d.label.slice(0, 4);
      });

    // Label below for pattern nodes
    node.filter((d) => d.type !== "root" && d.type !== "topic")
      .append("text")
      .attr("text-anchor", "middle")
      .attr("dominant-baseline", "hanging")
      .attr("y", (d) => (NODE_R[d.type] ?? 12) + 4)
      .attr("fill", "rgba(255,255,255,0.55)")
      .attr("font-size", "6.5")
      .attr("font-family", "Inter, system-ui, sans-serif")
      .attr("pointer-events", "none")
      .text((d) => d.label.length > 12 ? d.label.slice(0, 11) + "…" : d.label);

    // Expand/collapse on topic click
    node.filter((d) => d.type === "topic").on("click", (_ev, d) => {
      setExpanded((prev) => {
        const next = new Set(prev);
        if (next.has(d.id)) {
          next.delete(d.id);
        } else {
          next.add(d.id);
        }
        return next;
      });
    });

    // Tooltip
    const tt = tooltipRef.current;
    node
      .on("mouseenter", (ev, d) => {
        if (!tt) return;
        const label =
          d.type === "topic"
            ? `${d.label} — click to ${expanded.has(d.id) ? "collapse" : "expand"}`
            : `${d.label} (${d.type})`;
        tt.textContent = label;
        tt.style.opacity = "1";
        tt.style.left = ev.pageX + 14 + "px";
        tt.style.top  = ev.pageY - 10 + "px";
      })
      .on("mousemove", (ev) => {
        if (!tt) return;
        tt.style.left = ev.pageX + 14 + "px";
        tt.style.top  = ev.pageY - 10 + "px";
      })
      .on("mouseleave", () => {
        if (tt) tt.style.opacity = "0";
      });

    // ── simulation ─────────────────────────────────────────────────────────

    const sim = d3.forceSimulation<SimNode>(simNodes)
      .force(
        "link",
        d3.forceLink<SimNode, SimLink>(simLinks)
          .id((d) => d.id)
          .distance((d) => {
            const src = d.source as SimNode;
            return src.type === "root" ? 140 : 80;
          })
          .strength(0.7)
      )
      .force("charge", d3.forceManyBody<SimNode>().strength((d) =>
        d.type === "root" ? -700 : d.type === "topic" ? -260 : -100
      ))
      .force("center", d3.forceCenter(W / 2, H / 2).strength(0.05))
      .force("collision", d3.forceCollide<SimNode>((d) => (NODE_R[d.type] ?? 12) + 8));

    simRef.current = sim;

    // Pin root at center
    const rootSim = simNodes.find((n) => n.type === "root");
    if (rootSim) { rootSim.fx = W / 2; rootSim.fy = H / 2; }

    sim.on("tick", () => {
      link
        .attr("x1", (d) => (d.source as SimNode).x ?? 0)
        .attr("y1", (d) => (d.source as SimNode).y ?? 0)
        .attr("x2", (d) => (d.target as SimNode).x ?? 0)
        .attr("y2", (d) => (d.target as SimNode).y ?? 0);
      node.attr("transform", (d) => `translate(${d.x ?? 0},${d.y ?? 0})`);
    });

    return () => { sim.stop(); };
  }, [data, expanded, parentOf]);

  // ── empty state ────────────────────────────────────────────────────────────

  const topicCount = data.nodes.filter((n) => n.type === "topic").length;
  if (!topicCount) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center gap-3 p-8">
        <span className="text-4xl opacity-20">🧠</span>
        <p className="font-sans text-[12px] text-white/30 text-center leading-relaxed">
          No debate sessions yet.
          <br />
          Start debating to build your brain map.
        </p>
      </div>
    );
  }

  return (
    <div className="relative flex-1 w-full h-full">
      <svg
        ref={svgRef}
        width="100%"
        height="100%"
        style={{ display: "block" }}
      />
      {/* Floating tooltip — lives outside the SVG so it renders on top */}
      <div
        ref={tooltipRef}
        className="fixed z-[200] pointer-events-none px-2.5 py-1.5 rounded-md bg-[#1c1c1c] border border-white/15 font-sans text-[11px] text-white/80 shadow-lg transition-opacity duration-100"
        style={{ opacity: 0 }}
      />
    </div>
  );
}
