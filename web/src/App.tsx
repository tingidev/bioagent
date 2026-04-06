import { useCallback, useEffect, useState } from "react";
import type { DataMapResponse, HealthResponse, TraceEvent, TraceStep } from "./types";
import { fetchDataMap, fetchHealth, subscribeInvestigation } from "./api";
import DataMapPanel from "./components/DataMapPanel";
import HowItWorksPanel from "./components/HowItWorksPanel";
import InvestigationPanel from "./components/InvestigationPanel";
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

  useEffect(() => {
    fetchHealth().then(setHealth).catch(() => setHealth(null));
    fetchDataMap().then(setDataMap).catch(() => setDataMap(null));
  }, []);

  const handleInvestigate = useCallback(() => {
    if (!question.trim() || isInvestigating) return;

    setIsInvestigating(true);
    setSteps([]);
    setReport(null);
    setError(null);
    setCurrentPhase("research");

    subscribeInvestigation(
      question,
      (event: TraceEvent) => {
        if (event.event_type === "phase_change" && event.data.phase) {
          setCurrentPhase(event.data.phase);
        } else if (event.event_type === "trace_step") {
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
          setReport(event.data.report);
        } else if (event.event_type === "error" && event.data.message) {
          setError(event.data.message);
        }
      },
      (err) => {
        setError(err.message);
        setIsInvestigating(false);
      },
      () => setIsInvestigating(false),
    );
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
            <span className={health.status === "ok" ? "text-bio-accent" : "text-yellow-400"}>
              {sourceCount}/3 sources
            </span>
          )}
          {currentPhase && isInvestigating && (
            <span className="text-bio-accent animate-pulse uppercase text-xs tracking-wider">
              {currentPhase}
            </span>
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
          <div className="flex-1 flex overflow-hidden">
            {/* Left sidebar — Data Map */}
            <aside className="w-80 border-r border-bio-border overflow-y-auto p-4">
              <DataMapPanel dataMap={dataMap} health={health} />
            </aside>

            {/* Center — Investigation + Report */}
            <main className="flex-1 flex flex-col overflow-hidden">
              <InvestigationPanel
                question={question}
                onQuestionChange={setQuestion}
                onInvestigate={handleInvestigate}
                isInvestigating={isInvestigating}
                currentPhase={currentPhase}
                steps={steps}
                error={error}
              />
              {report && <ReportPanel report={report} />}
            </main>
          </div>

          {/* Bottom — Audit Trail */}
          {steps.length > 0 && (
            <div className="border-t border-bio-border max-h-64 overflow-y-auto">
              <TracePanel steps={steps} />
            </div>
          )}
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
