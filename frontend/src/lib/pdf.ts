// Copyright (c) 2026 V2 Software LLC. All rights reserved.

import jsPDF from "jspdf";

/* ──────────────────────────────────────────────────────────────
   Resume text parser – turns the plain-text tailored resume
   into structured sections so we can lay them out properly.
   ────────────────────────────────────────────────────────────── */

interface ResumeSection {
  title: string;
  lines: string[];
}

interface ParsedResume {
  name: string;
  subtitle: string;
  contact: string;
  sections: ResumeSection[];
}

const DIVIDER_RE = /^[─━─\-=]{5,}/;

function parseResumeText(raw: string): ParsedResume {
  const lines = raw.replace(/\r\n/g, "\n").split("\n");
  const name = lines[0]?.trim() || "";
  const subtitle = lines[1]?.trim() || "";
  const contact = lines[2]?.trim() || "";

  // Find where sections start (after contact line)
  let cursor = 3;
  // Skip any blank / divider lines between header and first section
  while (cursor < lines.length && (lines[cursor].trim() === "" || DIVIDER_RE.test(lines[cursor]))) {
    cursor++;
  }

  const sections: ResumeSection[] = [];
  let currentSection: ResumeSection | null = null;

  for (let i = cursor; i < lines.length; i++) {
    const line = lines[i];
    if (DIVIDER_RE.test(line)) continue; // skip divider lines

    const trimmed = line.trim();
    // Section header: ALL CAPS line that isn't a bullet and is followed by content
    if (trimmed.length > 0 && trimmed === trimmed.toUpperCase() && !trimmed.startsWith("•") && trimmed.length < 80) {
      if (currentSection) sections.push(currentSection);
      currentSection = { title: trimmed, lines: [] };
      continue;
    }

    if (currentSection) {
      currentSection.lines.push(line);
    }
  }
  if (currentSection) sections.push(currentSection);

  return { name, subtitle, contact, sections };
}

/* ──────────────────────────────────────────────────────────────
   Sidebar sections – extracted from parsed resume for the
   left column (contact, education, skills, competencies)
   ────────────────────────────────────────────────────────────── */

const SIDEBAR_KEYWORDS = ["CORE COMPETENCIES", "SKILLS", "EDUCATION", "CERTIFICATIONS", "CERTIFICATES"];

function isSidebarSection(title: string): boolean {
  return SIDEBAR_KEYWORDS.some((kw) => title.toUpperCase().includes(kw));
}

/* ──────────────────────────────────────────────────────────────
   PDF constants
   ────────────────────────────────────────────────────────────── */

const ACCENT = [37, 99, 163] as const; // Blue accent matching user's resume
const WHITE = [255, 255, 255] as const;
const DARK = [33, 37, 41] as const;
const GRAY = [108, 117, 125] as const;
const LIGHT_GRAY = [220, 220, 220] as const;

const PAGE_W = 215.9; // letter mm
const PAGE_H = 279.4;
const SIDEBAR_W = 62;
const MARGIN = 8;
const BODY_LEFT = SIDEBAR_W + 10;
const BODY_RIGHT = PAGE_W - MARGIN;
const BODY_WIDTH = BODY_RIGHT - BODY_LEFT;

/* ──────────────────────────────────────────────────────────────
   Resume PDF
   ────────────────────────────────────────────────────────────── */

export function buildResumePdf(rawText: string): jsPDF {
  const parsed = parseResumeText(rawText);
  const doc = new jsPDF({ unit: "mm", format: "letter" });

  const sidebarSections = parsed.sections.filter((s) => isSidebarSection(s.title));
  const mainSections = parsed.sections.filter((s) => !isSidebarSection(s.title));

  // ─── Draw sidebar background ───
  doc.setFillColor(...ACCENT);
  doc.rect(0, 0, SIDEBAR_W, PAGE_H, "F");

  // ─── Sidebar: Name ───
  let sy = 18;
  doc.setTextColor(...WHITE);
  doc.setFont("helvetica", "bold");
  doc.setFontSize(18);
  const nameLines = doc.splitTextToSize(parsed.name, SIDEBAR_W - MARGIN * 2);
  doc.text(nameLines, MARGIN, sy);
  sy += nameLines.length * 7 + 2;

  // ─── Sidebar: Subtitle ───
  doc.setFont("helvetica", "normal");
  doc.setFontSize(9);
  const subLines = doc.splitTextToSize(parsed.subtitle, SIDEBAR_W - MARGIN * 2);
  doc.text(subLines, MARGIN, sy);
  sy += subLines.length * 4 + 6;

  // ─── Sidebar: Contact ───
  doc.setFontSize(7.5);
  doc.setFont("helvetica", "bold");
  doc.text("Contact", MARGIN, sy);
  sy += 5;
  doc.setFont("helvetica", "normal");
  doc.setFontSize(7);
  const contactParts = parsed.contact.split("|").map((s) => s.trim());
  for (const part of contactParts) {
    const cLines = doc.splitTextToSize(part, SIDEBAR_W - MARGIN * 2);
    doc.text(cLines, MARGIN, sy);
    sy += cLines.length * 3.5 + 1.5;
  }
  sy += 4;

  // ─── Sidebar: sections (skills, education, etc.) ───
  for (const section of sidebarSections) {
    if (sy > PAGE_H - 20) break;

    // Section header
    doc.setFont("helvetica", "bold");
    doc.setFontSize(7.5);
    doc.text(section.title, MARGIN, sy);
    sy += 5;

    doc.setFont("helvetica", "normal");
    doc.setFontSize(6.5);
    for (const line of section.lines) {
      if (sy > PAGE_H - 10) break;
      const trimmed = line.trim();
      if (!trimmed) {
        sy += 2;
        continue;
      }
      const wrapped = doc.splitTextToSize(trimmed, SIDEBAR_W - MARGIN * 2);
      doc.text(wrapped, MARGIN, sy);
      sy += wrapped.length * 3 + 1;
    }
    sy += 4;
  }

  // ─── Main body: Professional Summary / Experience / Projects ───
  let my = 18;

  for (const section of mainSections) {
    if (my > PAGE_H - 20) {
      doc.addPage();
      // Re-draw sidebar on new page
      doc.setFillColor(...ACCENT);
      doc.rect(0, 0, SIDEBAR_W, PAGE_H, "F");
      my = 18;
    }

    // Section header
    doc.setTextColor(...ACCENT);
    doc.setFont("helvetica", "bold");
    doc.setFontSize(10);
    doc.text(section.title, BODY_LEFT, my);
    my += 1.5;

    // Divider line under header
    doc.setDrawColor(...LIGHT_GRAY);
    doc.setLineWidth(0.3);
    doc.line(BODY_LEFT, my, BODY_RIGHT, my);
    my += 5;

    // Section content
    doc.setTextColor(...DARK);
    doc.setFont("helvetica", "normal");
    doc.setFontSize(8.5);

    for (const line of section.lines) {
      const trimmed = line.trim();
      if (!trimmed) {
        my += 2.5;
        continue;
      }

      // Check for page overflow
      if (my > PAGE_H - 15) {
        doc.addPage();
        doc.setFillColor(...ACCENT);
        doc.rect(0, 0, SIDEBAR_W, PAGE_H, "F");
        my = 18;
        doc.setTextColor(...DARK);
        doc.setFont("helvetica", "normal");
        doc.setFontSize(8.5);
      }

      const isBullet = trimmed.startsWith("•") || trimmed.startsWith("-");
      const isSubheading = !isBullet && trimmed.length < 100 && (
        trimmed.includes(" | ") || trimmed.includes(" — ") || trimmed.includes(" -- ")
      );

      if (isSubheading) {
        doc.setFont("helvetica", "bold");
        doc.setFontSize(8.5);
        const wrapped = doc.splitTextToSize(trimmed, BODY_WIDTH);
        doc.text(wrapped, BODY_LEFT, my);
        my += wrapped.length * 4 + 1.5;
        doc.setFont("helvetica", "normal");
      } else if (isBullet) {
        const bulletText = trimmed.replace(/^[•\-]\s*/, "");
        const wrapped = doc.splitTextToSize(bulletText, BODY_WIDTH - 6);
        doc.text("•", BODY_LEFT + 1, my);
        doc.text(wrapped, BODY_LEFT + 5, my);
        my += wrapped.length * 3.8 + 1;
      } else {
        const wrapped = doc.splitTextToSize(trimmed, BODY_WIDTH);
        doc.text(wrapped, BODY_LEFT, my);
        my += wrapped.length * 3.8 + 1;
      }
    }
    my += 4;
  }

  return doc;
}

/* ──────────────────────────────────────────────────────────────
   Cover Letter PDF – clean business letter format
   ────────────────────────────────────────────────────────────── */

export function buildCoverLetterPdf(text: string, company: string, position: string): jsPDF {
  const doc = new jsPDF({ unit: "mm", format: "letter" });

  const marginX = 25;
  const contentWidth = PAGE_W - marginX * 2;

  // ─── Header accent bar ───
  doc.setFillColor(...ACCENT);
  doc.rect(0, 0, PAGE_W, 3, "F");

  // ─── Name block ───
  let y = 20;
  doc.setTextColor(...DARK);
  doc.setFont("helvetica", "bold");
  doc.setFontSize(20);
  doc.text("Jane Doe", marginX, y);
  y += 6;

  doc.setFont("helvetica", "normal");
  doc.setFontSize(9);
  doc.setTextColor(...GRAY);
  doc.text("San Francisco, CA | (555) 123-4567 | jane.doe@example.com", marginX, y);
  y += 10;

  // ─── Divider ───
  doc.setDrawColor(...ACCENT);
  doc.setLineWidth(0.5);
  doc.line(marginX, y, PAGE_W - marginX, y);
  y += 10;

  // ─── Date ───
  doc.setTextColor(...DARK);
  doc.setFont("helvetica", "normal");
  doc.setFontSize(10);
  const today = new Date().toLocaleDateString("en-US", {
    year: "numeric",
    month: "long",
    day: "numeric",
  });
  doc.text(today, marginX, y);
  y += 8;

  // ─── Recipient ───
  doc.setFont("helvetica", "bold");
  doc.text(`Re: ${position}`, marginX, y);
  y += 5;
  doc.setFont("helvetica", "normal");
  doc.setTextColor(...GRAY);
  doc.setFontSize(9);
  doc.text(company, marginX, y);
  y += 10;

  // ─── Body text ───
  doc.setTextColor(...DARK);
  doc.setFont("helvetica", "normal");
  doc.setFontSize(10);

  const paragraphs = text.replace(/\r\n/g, "\n").split("\n");
  for (const para of paragraphs) {
    const trimmed = para.trim();
    if (!trimmed) {
      y += 4;
      continue;
    }

    if (y > PAGE_H - 25) {
      doc.addPage();
      doc.setFillColor(...ACCENT);
      doc.rect(0, 0, PAGE_W, 3, "F");
      y = 18;
      doc.setTextColor(...DARK);
      doc.setFont("helvetica", "normal");
      doc.setFontSize(10);
    }

    const wrapped = doc.splitTextToSize(trimmed, contentWidth);
    doc.text(wrapped, marginX, y);
    y += wrapped.length * 4.5 + 2;
  }

  return doc;
}

/* ──────────────────────────────────────────────────────────────
   Download helpers
   ────────────────────────────────────────────────────────────── */

function sanitizeFilename(value: string): string {
  return value
    .replace(/[<>:"/\\|?*\u0000-\u001f]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

export function downloadResumePdf(resumeText: string, filename: string): void {
  const doc = buildResumePdf(resumeText);
  doc.save(`${sanitizeFilename(filename) || "Resume"}.pdf`);
}

export function downloadCoverLetterPdf(
  text: string,
  company: string,
  position: string,
  filename: string,
): void {
  const doc = buildCoverLetterPdf(text, company, position);
  doc.save(`${sanitizeFilename(filename) || "Cover Letter"}.pdf`);
}
