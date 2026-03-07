const LETTER_WIDTH = 612;
const LETTER_HEIGHT = 792;
const LEFT_MARGIN = 54;
const TOP_MARGIN = 72;
const BOTTOM_MARGIN = 60;
const BODY_FONT_SIZE = 11;
const TITLE_FONT_SIZE = 18;
const META_FONT_SIZE = 9;
const LEADING = 15;
const MAX_CHARS_PER_LINE = 88;

function escapePdfText(value: string): string {
  return value.replace(/\\/g, "\\\\").replace(/\(/g, "\\(").replace(/\)/g, "\\)");
}

function sanitizeFilename(value: string): string {
  return value
    .replace(/[<>:"/\\|?*\u0000-\u001f]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function wrapParagraph(paragraph: string, maxChars = MAX_CHARS_PER_LINE): string[] {
  const words = paragraph.trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return [""];

  const lines: string[] = [];
  let current = "";

  for (const word of words) {
    const candidate = current ? `${current} ${word}` : word;
    if (candidate.length <= maxChars) {
      current = candidate;
      continue;
    }

    if (current) {
      lines.push(current);
    }

    if (word.length <= maxChars) {
      current = word;
      continue;
    }

    const chunks = word.match(new RegExp(`.{1,${maxChars}}`, "g")) || [word];
    lines.push(...chunks.slice(0, -1));
    current = chunks[chunks.length - 1] || "";
  }

  if (current) {
    lines.push(current);
  }

  return lines;
}

function buildPageStream(title: string, meta: string, lines: string[]): string {
  const commands: string[] = ["BT"];
  let y = LETTER_HEIGHT - TOP_MARGIN;

  commands.push(`/F1 ${TITLE_FONT_SIZE} Tf`);
  commands.push(`1 0 0 1 ${LEFT_MARGIN} ${y} Tm`);
  commands.push(`(${escapePdfText(title)}) Tj`);

  y -= 24;
  commands.push(`/F1 ${META_FONT_SIZE} Tf`);
  commands.push(`1 0 0 1 ${LEFT_MARGIN} ${y} Tm`);
  commands.push(`(${escapePdfText(meta)}) Tj`);

  y -= 28;
  commands.push(`/F1 ${BODY_FONT_SIZE} Tf`);

  for (const line of lines) {
    if (y <= BOTTOM_MARGIN) break;
    commands.push(`1 0 0 1 ${LEFT_MARGIN} ${y} Tm`);
    commands.push(`(${escapePdfText(line)}) Tj`);
    y -= LEADING;
  }

  commands.push("ET");
  return commands.join("\n");
}

function splitIntoPages(body: string): string[][] {
  const paragraphs = body.replace(/\r\n/g, "\n").split("\n");
  const pageHeight = LETTER_HEIGHT - TOP_MARGIN - BOTTOM_MARGIN - 60;
  const maxLinesPerPage = Math.max(1, Math.floor(pageHeight / LEADING));

  const lines: string[] = [];
  for (const paragraph of paragraphs) {
    lines.push(...wrapParagraph(paragraph));
  }

  if (lines.length === 0) {
    lines.push("");
  }

  const pages: string[][] = [];
  for (let i = 0; i < lines.length; i += maxLinesPerPage) {
    pages.push(lines.slice(i, i + maxLinesPerPage));
  }
  return pages;
}

export function buildSimplePdfBlob(title: string, body: string, meta: string): Blob {
  const pageBodies = splitIntoPages(body);

  const objects: string[] = [];
  const fontObjectId = 3;
  const pageObjectIds = pageBodies.map((_, index) => 4 + index * 2);
  const contentObjectIds = pageBodies.map((_, index) => 5 + index * 2);
  const pagesObjectId = 2;

  objects[1] = "<< /Type /Catalog /Pages 2 0 R >>";
  objects[2] = `<< /Type /Pages /Count ${pageBodies.length} /Kids [${pageObjectIds
    .map((id) => `${id} 0 R`)
    .join(" ")}] >>`;
  objects[3] = "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>";

  pageBodies.forEach((pageLines, index) => {
    const pageObjectId = pageObjectIds[index];
    const contentObjectId = contentObjectIds[index];
    const stream = buildPageStream(title, meta, pageLines);
    objects[pageObjectId] =
      `<< /Type /Page /Parent ${pagesObjectId} 0 R /MediaBox [0 0 ${LETTER_WIDTH} ${LETTER_HEIGHT}] ` +
      `/Resources << /Font << /F1 ${fontObjectId} 0 R >> >> /Contents ${contentObjectId} 0 R >>`;
    objects[contentObjectId] = `<< /Length ${stream.length} >>\nstream\n${stream}\nendstream`;
  });

  let pdf = "%PDF-1.4\n";
  const offsets: number[] = [0];

  for (let i = 1; i < objects.length; i += 1) {
    offsets[i] = pdf.length;
    pdf += `${i} 0 obj\n${objects[i]}\nendobj\n`;
  }

  const xrefOffset = pdf.length;
  pdf += `xref\n0 ${objects.length}\n`;
  pdf += "0000000000 65535 f \n";
  for (let i = 1; i < objects.length; i += 1) {
    pdf += `${String(offsets[i]).padStart(10, "0")} 00000 n \n`;
  }
  pdf += `trailer\n<< /Size ${objects.length} /Root 1 0 R >>\nstartxref\n${xrefOffset}\n%%EOF`;

  return new Blob([pdf], { type: "application/pdf" });
}

export function downloadPdfDocument(params: {
  title: string;
  body: string;
  filename: string;
  meta: string;
}): void {
  const blob = buildSimplePdfBlob(params.title, params.body, params.meta);
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${sanitizeFilename(params.filename) || "document"}.pdf`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  setTimeout(() => URL.revokeObjectURL(url), 0);
}
