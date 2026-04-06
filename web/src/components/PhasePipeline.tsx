import { PHASES, PHASE_META, phaseIndex, type Phase } from "../phaseConfig";
import type { TraceStep } from "../types";

interface Props {
  currentPhase: string | null;
  isInvestigating: boolean;
  steps: TraceStep[];
}

export default function PhasePipeline({ currentPhase, isInvestigating, steps }: Props) {
  const activeIdx = currentPhase ? phaseIndex(currentPhase) : -1;

  // Count steps per phase
  const stepCounts: Record<string, number> = {};
  const toolCounts: Record<string, number> = {};
  for (const s of steps) {
    stepCounts[s.phase] = (stepCounts[s.phase] ?? 0) + 1;
    if (s.tool_call) toolCounts[s.phase] = (toolCounts[s.phase] ?? 0) + 1;
  }

  return (
    <div className="flex items-center gap-1.5 px-6 py-3 border-b border-bio-border bg-bio-bg/50">
      {PHASES.map((phase, i) => {
        const meta = PHASE_META[phase];
        const isDone = isInvestigating ? i < activeIdx : activeIdx >= 0 && i <= activeIdx;
        const isActive = isInvestigating && i === activeIdx;
        const isFuture = !isDone && !isActive;
        const count = stepCounts[phase] ?? 0;
        const tools = toolCounts[phase] ?? 0;

        return (
          <div key={phase} className="flex items-center gap-1.5 flex-1">
            {/* Phase card */}
            <div
              className={`
                flex-1 rounded-lg px-3 py-2 transition-all duration-500 border
                ${isActive
                  ? `${meta.border}/40 bg-gradient-to-r from-bio-card to-bio-bg shadow-lg shadow-${phase === "research" ? "blue" : phase === "plan" ? "amber" : phase === "execute" ? "emerald" : "purple"}-500/5`
                  : isDone
                    ? `border-bio-border/60 bg-bio-card`
                    : `border-bio-border/30 bg-bio-bg/30`
                }
              `}
            >
              <div className="flex items-center gap-2">
                {/* Phase indicator dot/ring */}
                <div className={`
                  w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-bold shrink-0 transition-all duration-500
                  ${isActive
                    ? `${meta.bg} text-bio-bg animate-pulse`
                    : isDone
                      ? `${meta.bg}/20 ${meta.color}`
                      : "bg-bio-border/30 text-bio-muted/40"
                  }
                `}>
                  {isDone && !isActive ? (
                    <svg className="w-3 h-3" viewBox="0 0 12 12" fill="none">
                      <path d="M2.5 6l2.5 2.5 4.5-5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  ) : (
                    meta.shortLabel
                  )}
                </div>
                <div className="min-w-0">
                  <div className={`text-xs font-medium tracking-wide transition-colors duration-300 ${
                    isActive ? meta.color : isDone ? "text-gray-300" : "text-bio-muted/40"
                  }`}>
                    {isActive ? meta.label : phase.charAt(0).toUpperCase() + phase.slice(1)}
                  </div>
                  {/* Summary line */}
                  {count > 0 && (
                    <div className={`text-[10px] ${isDone || isActive ? "text-bio-muted" : "text-bio-muted/30"}`}>
                      {tools > 0 ? `${tools} tool call${tools > 1 ? "s" : ""}` : `${count} step${count > 1 ? "s" : ""}`}
                    </div>
                  )}
                  {isActive && count === 0 && (
                    <div className="text-[10px] text-bio-muted animate-pulse">
                      Working...
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Connector arrow */}
            {i < PHASES.length - 1 && (
              <svg
                className={`w-4 h-4 shrink-0 transition-colors duration-500 ${
                  i < activeIdx ? "text-gray-500" : "text-bio-border/40"
                }`}
                viewBox="0 0 16 16"
                fill="none"
              >
                <path d="M6 3l5 5-5 5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            )}
          </div>
        );
      })}
    </div>
  );
}
