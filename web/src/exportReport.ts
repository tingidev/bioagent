import { Document, Packer, Paragraph, TextRun, HeadingLevel } from "docx";
import { saveAs } from "file-saver";

/** Download the report as a .md file. */
export function exportMarkdown(report: string): void {
  const blob = new Blob([report], { type: "text/markdown;charset=utf-8" });
  saveAs(blob, "bioagent-report.md");
}

/** Download the report as a .docx file. */
export async function exportDocx(report: string): Promise<void> {
  const paragraphs = markdownToParagraphs(report);
  const doc = new Document({
    sections: [{ children: paragraphs }],
  });
  const blob = await Packer.toBlob(doc);
  saveAs(blob, "bioagent-report.docx");
}

/** Simple markdown-to-docx paragraph converter. */
function markdownToParagraphs(md: string): Paragraph[] {
  const lines = md.split("\n");
  const paragraphs: Paragraph[] = [];

  for (const line of lines) {
    if (line.startsWith("# ")) {
      paragraphs.push(
        new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun({ text: line.slice(2), bold: true })] }),
      );
    } else if (line.startsWith("## ")) {
      paragraphs.push(
        new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun({ text: line.slice(3), bold: true })] }),
      );
    } else if (line.startsWith("### ")) {
      paragraphs.push(
        new Paragraph({ heading: HeadingLevel.HEADING_3, children: [new TextRun({ text: line.slice(4), bold: true })] }),
      );
    } else if (line.startsWith("- ")) {
      paragraphs.push(
        new Paragraph({ bullet: { level: 0 }, children: inlineRuns(line.slice(2)) }),
      );
    } else if (line.trim() === "") {
      paragraphs.push(new Paragraph({}));
    } else {
      paragraphs.push(new Paragraph({ children: inlineRuns(line) }));
    }
  }

  return paragraphs;
}

/** Parse bold (**text**) and code (`text`) into TextRuns. */
function inlineRuns(text: string): TextRun[] {
  const runs: TextRun[] = [];
  const pattern = /(\*\*(.+?)\*\*|`(.+?)`)/g;
  let last = 0;

  for (const match of text.matchAll(pattern)) {
    const idx = match.index ?? 0;
    if (idx > last) {
      runs.push(new TextRun({ text: text.slice(last, idx) }));
    }
    if (match[2]) {
      runs.push(new TextRun({ text: match[2], bold: true }));
    } else if (match[3]) {
      runs.push(new TextRun({ text: match[3], font: "Courier New", size: 20 }));
    }
    last = idx + match[0].length;
  }

  if (last < text.length) {
    runs.push(new TextRun({ text: text.slice(last) }));
  }

  return runs.length > 0 ? runs : [new TextRun({ text })];
}
