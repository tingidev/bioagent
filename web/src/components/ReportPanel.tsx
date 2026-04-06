import Markdown from "./Markdown";
import { exportMarkdown, exportDocx } from "../exportReport";
import type { TraceStep } from "../types";

interface Props {
  report: string;
  steps: TraceStep[];
  question: string;
}

export default function ReportPanel({ report, steps, question }: Props) {
  return (
    <div className="border-t-2 border-phase-synthesize/30 bg-gradient-to-b from-phase-synthesize/[0.03] to-transparent">
      <div className="p-6">
        {/* Header */}
        <div className="flex items-center gap-3 mb-5">
          <div className="w-8 h-8 rounded-lg bg-phase-synthesize/15 flex items-center justify-center">
            <svg className="w-4 h-4 text-phase-synthesize" viewBox="0 0 16 16" fill="none">
              <path d="M2 3h12M2 7h8M2 11h10M2 15h6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
            </svg>
          </div>
          <div className="flex-1">
            <h3 className="text-sm font-semibold text-gray-200 uppercase tracking-wider">
              Investigation Findings
            </h3>
            <p className="text-[10px] text-bio-muted mt-0.5">
              Structured report with citations and reproducible queries
            </p>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="text-[10px] text-bio-muted">Download:</span>
            <ExportButton label=".md" onClick={() => exportMarkdown(report, steps, question)} />
            <ExportButton label=".docx" onClick={() => exportDocx(report, steps, question)} />
          </div>
        </div>

        {/* Report content */}
        <div className="bg-bio-card border border-bio-border rounded-xl p-6">
          <Markdown>{report}</Markdown>
        </div>
      </div>
    </div>
  );
}

function ExportButton({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="text-[10px] text-bio-muted hover:text-gray-300 px-2 py-1 rounded border border-bio-border hover:border-bio-muted/50 transition-colors"
    >
      {label}
    </button>
  );
}
