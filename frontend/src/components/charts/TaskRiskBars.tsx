"use client";

import { useEffect, useRef, useState } from "react";
import * as d3 from "d3";

interface TaskRiskBarsProps {
  tasks: Array<{ task: string; risk_pct: number }>;
}

function riskColor(pct: number): string {
  if (pct > 70) return "#ef4444";
  if (pct >= 40) return "#eab308";
  return "#22c55e";
}

function truncate(str: string, max: number): string {
  return str.length > max ? str.slice(0, max - 1) + "\u2026" : str;
}

export default function TaskRiskBars({ tasks }: TaskRiskBarsProps) {
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
    if (!containerRef.current || !tasks || tasks.length === 0 || containerWidth === 0) return;

    const container = containerRef.current;
    d3.select(container).selectAll("*").remove();

    const margin = { top: 8, right: 60, bottom: 32, left: 280 };
    const barHeight = 28;
    const barGap = 8;
    const width = containerWidth;
    const height = tasks.length * (barHeight + barGap) + margin.top + margin.bottom;

    const svg = d3
      .select(container)
      .append("svg")
      .attr("width", width)
      .attr("height", height);

    const data = tasks.map((t) => ({
      name: truncate(t.task, 42),
      fullName: t.task,
      risk: Math.min(100, Math.max(0, t.risk_pct)),
    }));

    const x = d3.scaleLinear().domain([0, 100]).range([margin.left, width - margin.right]);
    const y = d3
      .scaleBand()
      .domain(data.map((d) => d.name))
      .range([margin.top, height - margin.bottom])
      .padding(0.25);

    // X axis
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
      .call((g) => g.selectAll(".tick line").attr("stroke", "#374151"))
      .call((g) => g.selectAll(".tick text").attr("fill", "#a1a1aa").attr("font-size", "11px"));

    // X axis label
    svg
      .append("text")
      .attr("x", (width + margin.left) / 2)
      .attr("y", height - 2)
      .attr("text-anchor", "middle")
      .attr("fill", "#a1a1aa")
      .attr("font-size", "11px")
      .text("Automation Risk %");

    // Tooltip (created early so labels and bars can reference it)
    const tooltip = d3
      .select(container)
      .append("div")
      .style("position", "absolute")
      .style("pointer-events", "none")
      .style("background", "#1f2937")
      .style("border", "1px solid #374151")
      .style("border-radius", "6px")
      .style("padding", "6px 10px")
      .style("color", "#e5e7eb")
      .style("font-size", "13px")
      .style("opacity", "0")
      .style("z-index", "10");

    // Y axis labels with tooltips for truncated names
    svg
      .selectAll(".label")
      .data(data)
      .join("text")
      .attr("x", margin.left - 8)
      .attr("y", (d) => (y(d.name) ?? 0) + y.bandwidth() / 2)
      .attr("text-anchor", "end")
      .attr("dominant-baseline", "central")
      .attr("fill", "#a1a1aa")
      .attr("font-size", "12px")
      .style("cursor", (d) => d.name !== d.fullName ? "help" : "default")
      .text((d) => d.name)
      .on("mouseenter", function (event, d) {
        const datum = d as (typeof data)[number];
        if (datum.name !== datum.fullName) {
          tooltip
            .style("opacity", "1")
            .html(`<strong>${datum.fullName}</strong><br/>Risk: ${datum.risk}%`);
        }
      })
      .on("mousemove", function (event) {
        const [mx, my] = d3.pointer(event, container);
        tooltip.style("left", `${mx + 12}px`).style("top", `${my - 10}px`);
      })
      .on("mouseleave", function () {
        tooltip.style("opacity", "0");
      });

    // Bars with enter transition
    svg
      .selectAll(".bar")
      .data(data)
      .join("rect")
      .attr("class", "bar")
      .attr("x", margin.left)
      .attr("y", (d) => y(d.name) ?? 0)
      .attr("height", y.bandwidth())
      .attr("rx", 4)
      .attr("fill", (d) => riskColor(d.risk))
      .attr("opacity", 0.9)
      .attr("width", 0)
      .transition()
      .duration(600)
      .delay((_, i) => i * 80)
      .attr("width", (d) => x(d.risk) - margin.left);

    // Percentage labels on bars
    svg
      .selectAll(".pct-label")
      .data(data)
      .join("text")
      .attr("class", "pct-label")
      .attr("x", (d) => x(d.risk) + 6)
      .attr("y", (d) => (y(d.name) ?? 0) + y.bandwidth() / 2)
      .attr("dominant-baseline", "central")
      .attr("fill", "#e5e7eb")
      .attr("font-size", "12px")
      .attr("font-weight", "600")
      .attr("opacity", 0)
      .text((d) => `${d.risk}%`)
      .transition()
      .duration(300)
      .delay((_, i) => i * 80 + 400)
      .attr("opacity", 1);

    svg
      .selectAll(".bar")
      .on("mouseenter", function (event, d) {
        const datum = d as (typeof data)[number];
        tooltip
          .style("opacity", "1")
          .html(`<strong>${datum.fullName}</strong><br/>Risk: ${datum.risk}%`);
        d3.select(this).attr("opacity", 1);
      })
      .on("mousemove", function (event) {
        const [mx, my] = d3.pointer(event, container);
        tooltip.style("left", `${mx + 12}px`).style("top", `${my - 10}px`);
      })
      .on("mouseleave", function () {
        tooltip.style("opacity", "0");
        d3.select(this).attr("opacity", 0.9);
      });

  }, [tasks, containerWidth]);

  if (!tasks || tasks.length === 0) return null;

  return <div ref={containerRef} className="relative w-full" />;
}
