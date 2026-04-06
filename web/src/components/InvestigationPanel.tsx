import { useEffect, useState } from "react";
import type { TraceStep } from "../types";
import { PHASE_META, type Phase } from "../phaseConfig";
import Markdown from "./Markdown";

interface Props {
  question: string;
  onQuestionChange: (q: string) => void;
  onInvestigate: () => void;
  isInvestigating: boolean;
  isThinking: boolean;
  currentPhase: string | null;
  steps: TraceStep[];
  error: string | null;
}

const SAMPLE_QUESTIONS = [
  "Compare the top-scoring antibodies against MIT_Target with the negative controls. Are the best binders statistically different, and what do their sequences have in common?",
  "What compounds in ChEMBL have measured bioactivity against SARS-CoV-2 spike protein? Cross-reference the target biology with AlphaSeq binding data and compare measurement approaches.",
  "Profile the full AlphaSeq dataset: how are binding scores distributed across targets, are there outliers worth investigating, and what does ChEMBL tell us about the same biological targets?",
];

export default function InvestigationPanel({
  question,
  onQuestionChange,
  onInvestigate,
  isInvestigating,
  isThinking,
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
    <div className="p-6">
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
              <span className={`text-xs px-2 py-0.5 rounded-full animate-pulse ${PHASE_META[currentPhase as Phase]?.color ?? "text-bio-accent"} ${PHASE_META[currentPhase as Phase]?.bg ?? "bg-bio-accent"}/20`}>
                {PHASE_META[currentPhase as Phase]?.label ?? currentPhase}...
              </span>
            )}
          </div>
          {steps.map((step) => (
            <StepCard key={step.step_number} step={step} />
          ))}

          {/* Thinking indicator — shown while LLM is processing */}
          {isThinking && <ThinkingCard currentPhase={currentPhase} />}
        </div>
      )}

      {/* Thinking indicator when no steps yet */}
      {isInvestigating && steps.length === 0 && isThinking && (
        <ThinkingCard currentPhase={currentPhase} />
      )}

      {error && (
        <div className="mt-4 bg-red-900/20 border border-red-800 rounded-lg p-3 text-sm text-red-300">
          {error}
        </div>
      )}
    </div>
  );
}

const THINKING_MESSAGES: Record<string, string[]> = {
  research: [
    "Research agent exploring data landscape",
    "Checking database connectivity",
    "Profiling targets and record counts",
    "Mapping available entities across sources",
  ],
  plan: [
    "Plan agent designing investigation strategy",
    "Identifying cross-database links",
    "Formulating hypothesis and query sequence",
  ],
  execute: [
    "Execute agent running queries",
    "Cross-referencing findings between databases",
    "Following leads across sources",
    "Comparing metrics across databases",
  ],
  synthesize: [
    "Synthesis agent compiling report",
    "Connecting evidence across sources",
    "Writing final findings",
  ],
};

function ThinkingCard({ currentPhase }: { currentPhase: string | null }) {
  const meta = currentPhase ? PHASE_META[currentPhase as Phase] : null;
  const messages = currentPhase ? THINKING_MESSAGES[currentPhase] ?? [] : [];
  const [msgIdx, setMsgIdx] = useState(0);

  // Cycle through messages
  useEffect(() => {
    if (messages.length <= 1) return;
    const interval = setInterval(() => {
      setMsgIdx((i) => (i + 1) % messages.length);
    }, 2800);
    return () => clearInterval(interval);
  }, [messages.length]);

  const label = messages[msgIdx % messages.length] || "Reasoning";
  const color = meta?.color ?? "text-bio-muted";
  const bg = meta?.bg ?? "bg-bio-accent";

  return (
    <div className={`border rounded-lg px-4 py-3 ${meta ? `${meta.border}/20` : "border-bio-border"} bg-bio-card/50 overflow-hidden`}>
      <div className="flex items-center gap-3">
        {/* Animated spinner ring */}
        <div className="relative w-5 h-5 shrink-0">
          <div className={`absolute inset-0 rounded-full border-2 border-current opacity-20 ${color}`} />
          <div className={`absolute inset-0 rounded-full border-2 border-transparent border-t-current animate-spin ${color}`} />
        </div>

        {/* Message with fade transition */}
        <span className={`text-xs font-medium ${color} animate-pulse`}>
          {label}...
        </span>
      </div>

      {/* Subtle scanning line */}
      <div className="mt-2 h-px w-full overflow-hidden rounded-full bg-bio-border/30">
        <div className={`h-full w-1/3 ${bg} opacity-40 animate-scan rounded-full`} />
      </div>
    </div>
  );
}

/** Plain-text preview: strip markdown, truncate. */
function plainPreview(text: string, maxLen = 120): string {
  const plain = text
    .replace(/#{1,4}\s+/g, "")   // headings
    .replace(/\*{1,2}([^*]+)\*{1,2}/g, "$1") // bold/italic
    .replace(/\n+/g, " ")        // newlines
    .trim();
  return plain.length > maxLen ? plain.slice(0, maxLen) + "..." : plain;
}

function StepCard({ step }: { step: TraceStep }) {
  const isToolCall = step.tool_call !== null;
  const isReasoning = !isToolCall;
  const isLong = isReasoning && step.reasoning.length > 150;
  const [expanded, setExpanded] = useState(false);
  const meta = PHASE_META[step.phase as Phase];

  return (
    <div className="bg-bio-card border border-bio-border rounded-lg p-3 text-sm">
      <div className="flex items-center gap-2 mb-1">
        <span className={`text-[10px] uppercase tracking-wider font-medium ${meta?.color ?? "text-bio-accent"}`}>
          {step.phase}
        </span>
        <span className="text-bio-muted text-xs">#{step.step_number}</span>
        {isToolCall && step.tool_call && (
          <span className="ml-auto text-[10px] px-1.5 py-0.5 rounded bg-bio-border text-bio-muted">
            {step.tool_call.tool_name} ({step.tool_call.duration_ms}ms)
          </span>
        )}
        {isReasoning && isLong && (
          <button
            onClick={() => setExpanded((v) => !v)}
            className="ml-auto text-[10px] px-1.5 py-0.5 rounded bg-bio-border text-bio-muted hover:text-gray-300 transition-colors"
          >
            {expanded ? "Collapse" : "Expand"}
          </button>
        )}
      </div>

      {/* Tool call: summary + query */}
      {isToolCall && step.tool_call && (
        <>
          <p className="text-xs text-gray-300 leading-relaxed">{step.tool_call.output_summary}</p>
          <div className="mt-1.5 bg-bio-bg rounded px-2 py-1.5">
            <code className="text-[10px] text-bio-accent/80 font-mono break-all">
              {step.tool_call.reproducible_query}
            </code>
          </div>
        </>
      )}

      {/* Reasoning: collapsed preview or full markdown */}
      {isReasoning && (
        expanded ? (
          <div className="text-xs leading-relaxed step-card-md">
            <Markdown>{step.reasoning}</Markdown>
          </div>
        ) : (
          <p className="text-xs text-gray-400 leading-relaxed">
            {plainPreview(step.reasoning)}
          </p>
        )
      )}
    </div>
  );
}
