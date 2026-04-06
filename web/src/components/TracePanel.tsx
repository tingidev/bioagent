import { useState } from "react";
import type { TraceStep } from "../types";

interface Props {
  steps: TraceStep[];
}

export default function TracePanel({ steps }: Props) {
  const [expanded, setExpanded] = useState<number | null>(null);
  const toolSteps = steps.filter((s) => s.tool_call !== null);

  return (
    <div className="p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-gray-300 uppercase tracking-wider">
          Audit Trail
        </h3>
        <span className="text-xs text-bio-muted">
          {toolSteps.length} tool calls / {steps.length} total steps
        </span>
      </div>
      <div className="space-y-1">
        {steps.map((step) => (
          <div
            key={step.step_number}
            className="text-xs font-mono"
          >
            <button
              onClick={() =>
                setExpanded(expanded === step.step_number ? null : step.step_number)
              }
              className="w-full text-left flex items-center gap-2 py-1 px-2 rounded hover:bg-bio-card transition-colors"
            >
              <span className="text-bio-accent w-6 text-right shrink-0">
                {step.step_number}.
              </span>
              <span className="text-bio-muted w-16 shrink-0">
                [{step.phase}]
              </span>
              <span className="text-gray-400 truncate">
                {step.description}
              </span>
              {step.tool_call && (
                <span className="ml-auto text-bio-muted shrink-0">
                  {step.tool_call.duration_ms}ms
                </span>
              )}
            </button>
            {expanded === step.step_number && (
              <div className="ml-10 mt-1 mb-2 p-2 bg-bio-card rounded border border-bio-border space-y-1">
                <p className="text-gray-400">{step.reasoning}</p>
                {step.tool_call && (
                  <>
                    <p className="text-bio-muted">
                      Input: {JSON.stringify(step.tool_call.input_params)}
                    </p>
                    <p className="text-bio-muted">
                      Output: {step.tool_call.output_summary}
                    </p>
                    <p className="text-bio-accent break-all">
                      Reproduce: {step.tool_call.reproducible_query}
                    </p>
                  </>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
