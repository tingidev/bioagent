import type { TraceStep } from "../types";

interface Props {
  question: string;
  onQuestionChange: (q: string) => void;
  onInvestigate: () => void;
  isInvestigating: boolean;
  currentPhase: string | null;
  steps: TraceStep[];
  error: string | null;
}

const SAMPLE_QUESTIONS = [
  "What are the strongest SARS-CoV-2 antibody binders in AlphaSeq, and do any have known crystal structures in SAbDab?",
  "Find antibodies targeting coronavirus spike proteins across all databases. What do we know about their binding characteristics and structural features?",
  "Are there any ChEMBL bioactivity measurements for compounds targeting SARS-CoV-2? Cross-reference with AlphaSeq binding data.",
];

const PHASE_LABELS: Record<string, string> = {
  research: "Researching",
  plan: "Planning",
  execute: "Executing",
  synthesize: "Synthesizing",
};

export default function InvestigationPanel({
  question,
  onQuestionChange,
  onInvestigate,
  isInvestigating,
  currentPhase,
  steps,
  error,
}: Props) {
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      onInvestigate();
    }
  };

  return (
    <div className="flex-1 flex flex-col p-6 overflow-y-auto">
      {/* Question input */}
      <div className="mb-6">
        <div className="flex gap-3">
          <textarea
            value={question}
            onChange={(e) => onQuestionChange(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask a research question across the connected databases..."
            rows={2}
            className="flex-1 bg-bio-card border border-bio-border rounded-lg px-4 py-3 text-gray-200 placeholder-bio-muted text-sm resize-none focus:outline-none focus:border-bio-accent transition-colors"
            disabled={isInvestigating}
          />
          <button
            onClick={onInvestigate}
            disabled={isInvestigating || !question.trim()}
            className="px-6 py-3 bg-bio-accent text-bio-bg font-medium rounded-lg text-sm hover:bg-bio-accent/90 disabled:opacity-40 disabled:cursor-not-allowed transition-all self-end"
          >
            {isInvestigating ? "Investigating..." : "Investigate"}
          </button>
        </div>

        {/* Sample questions */}
        {!isInvestigating && steps.length === 0 && (
          <div className="mt-4 space-y-2">
            <p className="text-xs text-bio-muted">Try a question:</p>
            {SAMPLE_QUESTIONS.map((q, i) => (
              <button
                key={i}
                onClick={() => onQuestionChange(q)}
                className="block w-full text-left text-xs text-bio-muted hover:text-gray-300 bg-bio-card border border-bio-border rounded px-3 py-2 transition-colors"
              >
                {q}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Live investigation stream */}
      {steps.length > 0 && (
        <div className="space-y-2">
          <div className="flex items-center gap-2 mb-3">
            <h3 className="text-sm font-semibold text-gray-300 uppercase tracking-wider">
              Investigation
            </h3>
            {isInvestigating && currentPhase && (
              <span className="text-xs px-2 py-0.5 rounded-full bg-bio-accent/20 text-bio-accent animate-pulse">
                {PHASE_LABELS[currentPhase] ?? currentPhase}...
              </span>
            )}
          </div>
          {steps.map((step) => (
            <StepCard key={step.step_number} step={step} />
          ))}
        </div>
      )}

      {error && (
        <div className="mt-4 bg-red-900/20 border border-red-800 rounded-lg p-3 text-sm text-red-300">
          {error}
        </div>
      )}
    </div>
  );
}

function StepCard({ step }: { step: TraceStep }) {
  const isToolCall = step.tool_call !== null;
  return (
    <div className="bg-bio-card border border-bio-border rounded-lg p-3 text-sm">
      <div className="flex items-center gap-2 mb-1">
        <span className="text-[10px] uppercase tracking-wider text-bio-accent font-medium">
          {step.phase}
        </span>
        <span className="text-bio-muted text-xs">#{step.step_number}</span>
        {isToolCall && step.tool_call && (
          <span className="ml-auto text-[10px] px-1.5 py-0.5 rounded bg-bio-border text-bio-muted">
            {step.tool_call.tool_name} ({step.tool_call.duration_ms}ms)
          </span>
        )}
      </div>
      <p className="text-gray-300 text-xs leading-relaxed">
        {isToolCall && step.tool_call
          ? step.tool_call.output_summary
          : step.reasoning.slice(0, 300)}
        {!isToolCall && step.reasoning.length > 300 && "..."}
      </p>
      {isToolCall && step.tool_call && (
        <p className="text-[10px] text-bio-muted mt-1 font-mono break-all">
          {step.tool_call.reproducible_query}
        </p>
      )}
    </div>
  );
}
