// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

import { useEffect, useRef, useState } from "react";
import * as d3 from "d3";

interface SkillComparison {
  categories: string[];
  user_scores: number[];
  target_scores: number[];
}

interface SkillGapRadarProps {
  comparison: SkillComparison;
  roleName: string;
}

export default function SkillGapRadar({
  comparison,
  roleName,
}: SkillGapRadarProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [containerWidth, setContainerWidth] = useState(0);

  useEffect(() => {
    if (!containerRef.current) return;
    const ro = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect.width ?? 0;
      if (w > 0) setContainerWidth(w);
    });
    ro.observe(containerRef.current);
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    if (!containerRef.current || !comparison?.categories?.length || containerWidth === 0) return;

    const container = containerRef.current;
    d3.select(container).selectAll("*").remove();

    const { categories, user_scores, target_scores } = comparison;
    const n = categories.length;
    if (n < 3) return;

    const size = Math.min(containerWidth, 360);
    const margin = 50;
    const radius = (size - margin * 2) / 2;
    const cx = size / 2;
    const cy = size / 2;
    const angleSlice = (2 * Math.PI) / n;

    const svg = d3
      .select(container)
      .append("svg")
      .attr("width", size)
      .attr("height", size + 40); // extra for legend

    const g = svg.append("g").attr("transform", `translate(${cx},${cy})`);

    const rScale = d3.scaleLinear().domain([0, 100]).range([0, radius]);

    // Grid circles
    const levels = [20, 40, 60, 80, 100];
    levels.forEach((level) => {
      g.append("circle")
        .attr("r", rScale(level))
        .attr("fill", "none")
        .attr("stroke", "#374151")
        .attr("stroke-width", 0.5)
        .attr("stroke-dasharray", level < 100 ? "2,3" : "none");
    });

    // Level labels
    levels.forEach((level) => {
      g.append("text")
        .attr("x", 4)
        .attr("y", -rScale(level) - 2)
        .attr("fill", "#6b7280")
        .attr("font-size", "9px")
        .text(`${level}`);
    });

    // Axis lines and labels
    categories.forEach((cat, i) => {
      const angle = angleSlice * i - Math.PI / 2;
      const x2 = Math.cos(angle) * radius;
      const y2 = Math.sin(angle) * radius;

      g.append("line")
        .attr("x1", 0)
        .attr("y1", 0)
        .attr("x2", x2)
        .attr("y2", y2)
        .attr("stroke", "#374151")
        .attr("stroke-width", 0.5);

      const labelRadius = radius + 14;
      const lx = Math.cos(angle) * labelRadius;
      const ly = Math.sin(angle) * labelRadius;

      g.append("text")
        .attr("x", lx)
        .attr("y", ly)
        .attr("text-anchor", Math.abs(lx) < 5 ? "middle" : lx > 0 ? "start" : "end")
        .attr("dominant-baseline", Math.abs(ly) < 5 ? "central" : ly > 0 ? "hanging" : "auto")
        .attr("fill", "#a1a1aa")
        .attr("font-size", "10px")
        .text(cat.length > 18 ? cat.slice(0, 17) + "\u2026" : cat);
    });

    // Polygon path generator
    function polygonPoints(scores: number[]): string {
      return scores
        .map((score, i) => {
          const angle = angleSlice * i - Math.PI / 2;
          const r = rScale(Math.min(100, Math.max(0, score)));
          return `${Math.cos(angle) * r},${Math.sin(angle) * r}`;
        })
        .join(" ");
    }

    // Target role polygon (green, drawn first = behind)
    const targetPoly = g
      .append("polygon")
      .attr("points", polygonPoints(target_scores.map(() => 0)))
      .attr("fill", "#22c55e")
      .attr("fill-opacity", 0.15)
      .attr("stroke", "#22c55e")
      .attr("stroke-width", 2)
      .attr("stroke-opacity", 0.8);

    targetPoly
      .transition()
      .duration(700)
      .delay(200)
      .attr("points", polygonPoints(target_scores));

    // User polygon (blue, drawn on top)
    const userPoly = g
      .append("polygon")
      .attr("points", polygonPoints(user_scores.map(() => 0)))
      .attr("fill", "#3b82f6")
      .attr("fill-opacity", 0.2)
      .attr("stroke", "#3b82f6")
      .attr("stroke-width", 2)
      .attr("stroke-opacity", 0.9);

    userPoly
      .transition()
      .duration(700)
      .attr("points", polygonPoints(user_scores));

    // Dots on user polygon
    user_scores.forEach((score, i) => {
      const angle = angleSlice * i - Math.PI / 2;
      const r = rScale(Math.min(100, score));
      g.append("circle")
        .attr("cx", Math.cos(angle) * r)
        .attr("cy", Math.sin(angle) * r)
        .attr("r", 3.5)
        .attr("fill", "#3b82f6")
        .attr("stroke", "#1e3a5f")
        .attr("stroke-width", 1)
        .attr("opacity", 0)
        .transition()
        .duration(400)
        .delay(500)
        .attr("opacity", 1);
    });

    // Legend
    const legend = svg
      .append("g")
      .attr("transform", `translate(${cx - 80},${size + 10})`);

    // User legend
    legend
      .append("rect")
      .attr("width", 12)
      .attr("height", 12)
      .attr("rx", 2)
      .attr("fill", "#3b82f6")
      .attr("fill-opacity", 0.6);
    legend
      .append("text")
      .attr("x", 16)
      .attr("y", 10)
      .attr("fill", "#d1d5db")
      .attr("font-size", "11px")
      .text("Your Skills");

    // Target legend
    legend
      .append("rect")
      .attr("x", 90)
      .attr("width", 12)
      .attr("height", 12)
      .attr("rx", 2)
      .attr("fill", "#22c55e")
      .attr("fill-opacity", 0.5);
    legend
      .append("text")
      .attr("x", 106)
      .attr("y", 10)
      .attr("fill", "#d1d5db")
      .attr("font-size", "11px")
      .text(roleName);

  }, [comparison, roleName, containerWidth]);

  if (!comparison?.categories?.length) return null;

  return <div ref={containerRef} className="relative w-full flex justify-center" />;
}
