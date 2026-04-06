import { useState } from "react";
import type { TraceStep } from "../types";
import { PHASE_META, type Phase } from "../phaseConfig";

interface Props {
  steps: TraceStep[];
}

export default function TracePanel({ steps }: Props) {
  const [expanded, setExpanded] = useState<number | null>(null);
  const toolSteps = steps.filter((s) => s.tool_call !== null);

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-4 py-3 border-b border-bio-border shrink-0">
        <h2 className="text-sm font-semibold text-gray-300 uppercase tracking-wider">
          Audit Trail
        </h2>
        <p className="text-[10px] text-bio-muted mt-0.5">
          {toolSteps.length} tool call{toolSteps.length !== 1 && "s"} / {steps.length} step{steps.length !== 1 && "s"}
        </p>
      </div>

      {/* Steps list */}
      <div className="flex-1 overflow-y-auto px-3 py-2 space-y-0.5">
        {steps.map((step) => {
          const meta = PHASE_META[step.phase as Phase];
          const isExpanded = expanded === step.step_number;

          return (
            <div key={step.step_number}>
              <button
                onClick={() => setExpanded(isExpanded ? null : step.step_number)}
                className="w-full text-left flex items-center gap-2 py-1.5 px-2 rounded-lg hover:bg-bio-card transition-colors"
              >
                {/* Step number */}
                <span className="text-[10px] text-bio-muted w-4 text-right shrink-0 font-mono">
                  {step.step_number}
                </span>

                {/* Phase dot */}
                <div className={`w-1.5 h-1.5 rounded-full shrink-0 ${meta?.bg ?? "bg-bio-muted"}`} />

                {/* Description */}
                <span className="text-[11px] text-gray-300 truncate flex-1">
                  {step.tool_call ? step.tool_call.tool_name : step.description}
                </span>

                {/* Duration badge */}
                {step.tool_call && (
                  <span className="text-[10px] text-bio-muted font-mono shrink-0">
                    {step.tool_call.duration_ms}ms
                  </span>
                )}

                {/* Expand chevron */}
                <svg
                  className={`w-3 h-3 text-bio-muted shrink-0 transition-transform ${isExpanded ? "rotate-90" : ""}`}
                  viewBox="0 0 12 12"
                  fill="none"
                >
                  <path d="M4 2l4 4-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </button>

              {/* Expanded detail */}
              {isExpanded && (
                <div className="ml-6 mr-1 mb-1.5 rounded border border-bio-border bg-bio-card overflow-hidden">
                  {/* Reasoning */}
                  <div className="px-2.5 py-1.5 border-b border-bio-border/50">
                    <div className="text-[9px] text-bio-muted uppercase tracking-wider mb-0.5">Reasoning</div>
                    <p className="text-[11px] text-gray-400 leading-snug">{step.reasoning}</p>
                  </div>

                  {step.tool_call && (
                    <>
                      {/* Input */}
                      <div className="px-2.5 py-1.5 border-b border-bio-border/50">
                        <div className="text-[9px] text-bio-muted uppercase tracking-wider mb-0.5">Input</div>
                        <pre className="text-[10px] text-gray-400 font-mono bg-bio-bg rounded p-1.5 overflow-x-auto leading-tight">
                          {JSON.stringify(step.tool_call.input_params, null, 2)}
                        </pre>
                      </div>

                      {/* Output */}
                      <div className="px-2.5 py-1.5 border-b border-bio-border/50">
                        <div className="text-[9px] text-bio-muted uppercase tracking-wider mb-0.5">Output</div>
                        <p className="text-[11px] text-gray-300 leading-snug">{step.tool_call.output_summary}</p>
                      </div>

                      {/* Reproducible query */}
                      <div className="px-2.5 py-1.5">
                        <div className="text-[9px] text-bio-muted uppercase tracking-wider mb-0.5">Query</div>
                        <pre className="text-[10px] text-bio-accent/80 font-mono bg-bio-bg rounded p-1.5 overflow-x-auto break-all whitespace-pre-wrap leading-tight">
                          {step.tool_call.reproducible_query}
                        </pre>
                      </div>
                    </>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
