import { useCallback, useEffect, useRef, useState } from "react";
import type { DataMapResponse, HealthResponse, TraceEvent, TraceStep } from "./types";
import { fetchDataMap, fetchHealth, subscribeInvestigation } from "./api";
import { PHASE_META, type Phase } from "./phaseConfig";
import DataMapPanel from "./components/DataMapPanel";
import HowItWorksPanel from "./components/HowItWorksPanel";
import InvestigationPanel from "./components/InvestigationPanel";
import PhasePipeline from "./components/PhasePipeline";
import TracePanel from "./components/TracePanel";
import ReportPanel from "./components/ReportPanel";

type View = "investigate" | "how-it-works";

export default function App() {
  const [view, setView] = useState<View>("how-it-works");
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [dataMap, setDataMap] = useState<DataMapResponse | null>(null);
  const [question, setQuestion] = useState("");
  const [isInvestigating, setIsInvestigating] = useState(false);
  const [currentPhase, setCurrentPhase] = useState<string | null>(null);
  const [steps, setSteps] = useState<TraceStep[]>([]);
  const [report, setReport] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isThinking, setIsThinking] = useState(false);
  const cancelRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    fetchHealth().then(setHealth).catch(() => setHealth(null));
    fetchDataMap().then(setDataMap).catch(() => setDataMap(null));
  }, []);


  const handleCancel = useCallback(() => {
    cancelRef.current?.();
    cancelRef.current = null;
    setIsInvestigating(false);
    setIsThinking(false);
  }, []);

  const handleReset = useCallback(() => {
    handleCancel();
    setQuestion("");
    setSteps([]);
    setReport(null);
    setError(null);
    setCurrentPhase(null);
  }, [handleCancel]);

  const handleInvestigate = useCallback(() => {
    if (!question.trim() || isInvestigating) return;

    setIsInvestigating(true);
    setSteps([]);
    setReport(null);
    setError(null);
    setCurrentPhase("research");


    const cancel = subscribeInvestigation(
      question,
      (event: TraceEvent) => {
        if (event.event_type === "thinking") {
          setIsThinking(true);
        } else if (event.event_type === "phase_change" && event.data.phase) {
          setIsThinking(false);
          setCurrentPhase(event.data.phase);
        } else if (event.event_type === "trace_step") {
          setIsThinking(false);
          const step: TraceStep = {
            step_number: event.data.step_number ?? 0,
            phase: event.data.phase ?? "",
            description: event.data.description ?? "",
            reasoning: event.data.reasoning ?? "",
            timestamp: new Date().toISOString(),
            tool_call: event.data.tool_call ?? null,
          };
          setSteps((prev) => [...prev, step]);
        } else if (event.event_type === "report" && event.data.report) {
          setIsThinking(false);
          setReport(event.data.report);
        } else if (event.event_type === "error" && event.data.message) {
          setIsThinking(false);
          setError(event.data.message);
        }
      },
      (err) => {
        setError(err.message);
        setIsInvestigating(false);
      },
      () => setIsInvestigating(false),
    );
    cancelRef.current = cancel;
  }, [question, isInvestigating]);

  const sourceCount = health
    ? Object.values(health.sources).filter(Boolean).length
    : 0;

  return (
    <div className="min-h-screen flex flex-col">
      {/* Header */}
      <header className="border-b border-bio-border px-6 py-3 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-bio-accent/20 flex items-center justify-center">
            <span className="text-bio-accent font-bold text-sm">B</span>
          </div>
          <h1 className="text-lg font-semibold text-gray-100">
            BioAgent
          </h1>
        </div>

        {/* Tabs */}
        <nav className="flex items-center gap-1">
          <TabButton
            active={view === "how-it-works"}
            onClick={() => setView("how-it-works")}
          >
            How It Works
          </TabButton>
          <TabButton
            active={view === "investigate"}
            onClick={() => setView("investigate")}
          >
            Investigate
          </TabButton>
        </nav>

        <div className="flex items-center gap-4 text-sm">
          {health && (
            <div className="flex items-center gap-2">
              {Object.entries(health.sources).map(([name, ok]) => {
                const label = name === "alphaseq" ? "AlphaSeq" : name === "sabdab" ? "SAbDab" : "ChEMBL";
                return (
                  <span key={name} className="relative flex items-center gap-1 cursor-default group">
                    <span className={`w-1.5 h-1.5 rounded-full ${ok ? "bg-bio-accent" : "bg-yellow-500"}`} />
                    <span className={`text-xs ${ok ? "text-gray-400" : "text-yellow-500/70"}`}>
                      {label}
                    </span>
                    <span className="absolute top-full right-0 mt-1.5 px-2.5 py-1.5 rounded bg-bio-card border border-bio-border text-[11px] whitespace-nowrap opacity-0 pointer-events-none group-hover:opacity-100 transition-opacity z-50 shadow-lg">
                      {ok
                        ? <span className="text-bio-accent">Connected</span>
                        : <><span className="text-yellow-500">Unavailable</span><span className="text-gray-400"> &ndash; agent will use remaining sources</span></>
                      }
                    </span>
                  </span>
                );
              })}
            </div>
          )}
          {currentPhase && isInvestigating && (
            <div className="flex items-center gap-2">
              <span className={`animate-pulse uppercase text-xs tracking-wider ${PHASE_META[currentPhase as Phase]?.color ?? "text-bio-accent"}`}>
                {currentPhase}
              </span>
              <button
                onClick={handleCancel}
                className="text-xs text-red-400/70 hover:text-red-400 px-2 py-0.5 rounded border border-red-400/20 hover:border-red-400/40 transition-colors"
              >
                Stop
              </button>
            </div>
          )}
          {(steps.length > 0 || report) && !isInvestigating && (
            <button
              onClick={handleReset}
              className="text-xs text-bio-muted hover:text-gray-300 px-2.5 py-1 rounded-lg border border-bio-border hover:border-bio-muted/50 transition-colors"
            >
              New investigation
            </button>
          )}
        </div>
      </header>

      {/* View: How It Works */}
      {view === "how-it-works" && (
        <HowItWorksPanel />
      )}

      {/* View: Investigate */}
      {view === "investigate" && (
        <>
          {/* Phase progress pipeline — visible once investigation starts */}
          {(isInvestigating || steps.length > 0) && (
            <PhasePipeline
              currentPhase={currentPhase}
              isInvestigating={isInvestigating}
              steps={steps}
            />
          )}
          <div className="flex-1 flex overflow-hidden">
            {/* Left sidebar — Data Map */}
            <aside className="w-80 border-r border-bio-border overflow-y-auto p-4">
              <DataMapPanel dataMap={dataMap} health={health} />
            </aside>

            {/* Center — Investigation + Report */}
            <main className="flex-1 overflow-y-auto">
              <InvestigationPanel
                question={question}
                onQuestionChange={setQuestion}
                onInvestigate={handleInvestigate}
                isInvestigating={isInvestigating}
                isThinking={isThinking}
                currentPhase={currentPhase}
                steps={steps}
                error={error}
              />
              {report && <ReportPanel report={report} />}
            </main>

            {/* Right sidebar — Audit Trail */}
            {steps.length > 0 && (
              <aside className="w-80 border-l border-bio-border shrink-0">
                <TracePanel steps={steps} />
              </aside>
            )}
          </div>
        </>
      )}
    </div>
  );
}

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-colors ${
        active
          ? "bg-bio-accent/15 text-bio-accent"
          : "text-bio-muted hover:text-gray-300"
      }`}
    >
      {children}
    </button>
  );
}
