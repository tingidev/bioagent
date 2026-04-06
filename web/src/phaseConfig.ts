export const PHASES = ["research", "plan", "execute", "synthesize"] as const;
export type Phase = (typeof PHASES)[number];

export const PHASE_META: Record<
  Phase,
  { label: string; shortLabel: string; color: string; bg: string; border: string }
> = {
  research: {
    label: "Research Agent",
    shortLabel: "R",
    color: "text-phase-research",
    bg: "bg-phase-research",
    border: "border-phase-research",
  },
  plan: {
    label: "Plan Agent",
    shortLabel: "P",
    color: "text-phase-plan",
    bg: "bg-phase-plan",
    border: "border-phase-plan",
  },
  execute: {
    label: "Execute Agent",
    shortLabel: "E",
    color: "text-phase-execute",
    bg: "bg-phase-execute",
    border: "border-phase-execute",
  },
  synthesize: {
    label: "Synthesis Agent",
    shortLabel: "S",
    color: "text-phase-synthesize",
    bg: "bg-phase-synthesize",
    border: "border-phase-synthesize",
  },
};

export function phaseIndex(phase: string): number {
  return PHASES.indexOf(phase as Phase);
}
