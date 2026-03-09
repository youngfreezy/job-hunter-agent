// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

import { useEffect, useRef, useState } from "react";
import * as d3 from "d3";

interface PivotComparisonScatterProps {
  pivots: Array<{
    role: string;
    skill_overlap_pct: number;
    salary_range?: { min: number; max: number; median: number };
    market_demand: number;
    ai_risk_pct: number;
  }>;
}

function aiRiskColor(pct: number): string {
  if (pct > 70) return "#ef4444";
  if (pct >= 40) return "#eab308";
  return "#22c55e";
}

export default function PivotComparisonScatter({ pivots }: PivotComparisonScatterProps) {
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
    if (!containerRef.current || !pivots || pivots.length === 0 || containerWidth === 0) return;

    const container = containerRef.current;
    d3.select(container).selectAll("*").remove();

    const margin = { top: 20, right: 30, bottom: 50, left: 65 };
    const width = containerWidth;
    const height = 340;

    const svg = d3.select(container).append("svg").attr("width", width).attr("height", height);

    const data = pivots
      .filter((p) => p.salary_range)
      .map((p) => {
        const sr = p.salary_range!;
        return {
          role: p.role,
          skillOverlap: p.skill_overlap_pct,
          salaryMedian: sr.median / 1000,
          salaryMin: sr.min / 1000,
          salaryMax: sr.max / 1000,
          demand: p.market_demand,
          aiRisk: p.ai_risk_pct,
        };
      });

    if (data.length === 0) return;

    const salaryExtent = d3.extent(data, (d) => d.salaryMedian) as [number, number];
    const demandExtent = d3.extent(data, (d) => d.demand) as [number, number];

    const x = d3
      .scaleLinear()
      .domain([0, 100])
      .range([margin.left, width - margin.right]);

    const y = d3
      .scaleLinear()
      .domain([Math.max(0, salaryExtent[0] - 15), salaryExtent[1] + 15])
      .range([height - margin.bottom, margin.top]);

    const r = d3.scaleSqrt().domain(demandExtent).range([8, 35]);

    // Gridlines
    svg
      .append("g")
      .attr("transform", `translate(0,${height - margin.bottom})`)
      .call(
        d3
          .axisBottom(x)
          .ticks(5)
          .tickFormat((d) => `${d}%`)
      )
      .call((g) => g.select(".domain").attr("stroke", "#374151"))
      .call((g) =>
        g
          .selectAll(".tick line")
          .clone()
          .attr("y2", -(height - margin.top - margin.bottom))
          .attr("stroke", "#1f2937")
          .attr("stroke-dasharray", "2,3")
      )
      .call((g) => g.selectAll(".tick text").attr("fill", "#a1a1aa").attr("font-size", "11px"));

    svg
      .append("g")
      .attr("transform", `translate(${margin.left},0)`)
      .call(
        d3
          .axisLeft(y)
          .ticks(5)
          .tickFormat((d) => `$${d}K`)
      )
      .call((g) => g.select(".domain").attr("stroke", "#374151"))
      .call((g) =>
        g
          .selectAll(".tick line")
          .clone()
          .attr("x2", width - margin.left - margin.right)
          .attr("stroke", "#1f2937")
          .attr("stroke-dasharray", "2,3")
      )
      .call((g) => g.selectAll(".tick text").attr("fill", "#a1a1aa").attr("font-size", "11px"));

    // Axis labels
    svg
      .append("text")
      .attr("x", (width + margin.left) / 2)
      .attr("y", height - 6)
      .attr("text-anchor", "middle")
      .attr("fill", "#a1a1aa")
      .attr("font-size", "12px")
      .text("Skill Overlap %");

    svg
      .append("text")
      .attr("transform", "rotate(-90)")
      .attr("x", -(height - margin.bottom + margin.top) / 2)
      .attr("y", 16)
      .attr("text-anchor", "middle")
      .attr("fill", "#a1a1aa")
      .attr("font-size", "12px")
      .text("Median Salary ($K)");

    // Tooltip div
    const tooltip = d3
      .select(container)
      .append("div")
      .style("position", "absolute")
      .style("pointer-events", "none")
      .style("background", "#1f2937")
      .style("border", "1px solid #374151")
      .style("border-radius", "6px")
      .style("padding", "8px 12px")
      .style("color", "#e5e7eb")
      .style("font-size", "13px")
      .style("line-height", "1.5")
      .style("opacity", "0")
      .style("z-index", "10");

    // Bubbles
    svg
      .selectAll(".bubble")
      .data(data)
      .join("circle")
      .attr("class", "bubble")
      .attr("cx", (d) => x(d.skillOverlap))
      .attr("cy", (d) => y(d.salaryMedian))
      .attr("fill", (d) => aiRiskColor(d.aiRisk))
      .attr("fill-opacity", 0.75)
      .attr("stroke", (d) => aiRiskColor(d.aiRisk))
      .attr("stroke-width", 1.5)
      .attr("r", 0)
      .transition()
      .duration(600)
      .delay((_, i) => i * 120)
      .attr("r", (d) => r(d.demand));

    // Role name labels
    svg
      .selectAll(".role-label")
      .data(data)
      .join("text")
      .attr("class", "role-label")
      .attr("x", (d) => x(d.skillOverlap))
      .attr("y", (d) => y(d.salaryMedian) - r(d.demand) - 6)
      .attr("text-anchor", "middle")
      .attr("fill", "#d1d5db")
      .attr("font-size", "11px")
      .attr("font-weight", "500")
      .text((d) => d.role);

    // Hover interactions (applied after transition)
    svg
      .selectAll<SVGCircleElement, typeof data[number]>(".bubble")
      .on("mouseenter", function (event, d) {
        d3.select(this).attr("fill-opacity", 1).attr("stroke-width", 2.5);
        tooltip
          .style("opacity", "1")
          .html(
            `<div style="font-weight:600;margin-bottom:4px">${d.role}</div>` +
              `Skill Overlap: ${d.skillOverlap}%<br/>` +
              `Salary: $${d.salaryMin}K – $${d.salaryMax}K (median $${d.salaryMedian}K)<br/>` +
              `Openings: ${d.demand.toLocaleString()}<br/>` +
              `AI Risk: ${d.aiRisk}%`
          );
      })
      .on("mousemove", function (event) {
        const [mx, my] = d3.pointer(event, container);
        tooltip.style("left", `${mx + 14}px`).style("top", `${my - 10}px`);
      })
      .on("mouseleave", function () {
        d3.select(this).attr("fill-opacity", 0.75).attr("stroke-width", 1.5);
        tooltip.style("opacity", "0");
      });
  }, [pivots, containerWidth]);

  if (!pivots || pivots.length === 0) return null;

  return <div ref={containerRef} className="relative w-full" />;
}
