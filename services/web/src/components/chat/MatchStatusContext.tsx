"use client";

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

export type PipelineStage = {
  key: string;
  stage: string;
  status: "pending" | "active" | "complete" | "error";
  iteration?: number;
  details?: unknown;
};

type MatchStatusContextValue = {
  stages: PipelineStage[];
  running: boolean;
  resetStages: () => void;
  setOptimisticStart: () => void;
  applyEvent: (event: Record<string, unknown>) => void;
  setRunning: (v: boolean) => void;
};

const MatchStatusContext = createContext<MatchStatusContextValue | null>(null);

const STAGE_ORDER = [
  "collecting_context",
  "rewriting",
  "orchestrating",
  "tool_planning",
  "retrieving",
  "drafting",
  "judging",
  "responding",
];

function normalizeStatus(status: unknown): PipelineStage["status"] {
  if (status === "active" || status === "complete" || status === "error") {
    return status;
  }
  return "pending";
}

export function MatchStatusProvider({ children }: { children: ReactNode }) {
  const [stages, setStages] = useState<PipelineStage[]>([]);
  const [running, setRunning] = useState(false);

  const resetStages = useCallback(() => {
    setStages([]);
    setRunning(false);
  }, []);

  const setOptimisticStart = useCallback(() => {
    setRunning(true);
    setStages([
      {
        key: "collecting_context",
        stage: "collecting_context",
        status: "active",
        iteration: 1,
      },
    ]);
  }, []);

  const applyEvent = useCallback((event: Record<string, unknown>) => {
    const type = event.type;
    if (type === "pipeline_start") {
      setRunning(true);
      return;
    }
    if (type === "pipeline_complete" || type === "pipeline_error") {
      setRunning(false);
      setStages((prev) =>
        prev.map((s) =>
          s.status === "active"
            ? { ...s, status: type === "pipeline_error" ? "error" : "complete" }
            : s,
        ),
      );
      return;
    }
    if (type !== "stage_update") return;

    const stage = String(event.stage || "unknown");
    const status = normalizeStatus(event.status);
    const key = stage;
    setStages((prev) => {
      const idx = prev.findIndex((s) => s.key === key);
      const next: PipelineStage = {
        key,
        stage,
        status,
        iteration: typeof event.iteration === "number" ? event.iteration : undefined,
        details: event.details,
      };
      if (idx >= 0) {
        const copy = [...prev];
        copy[idx] = next;
        return copy;
      }
      return [...prev, next];
    });
  }, []);

  const value = useMemo(
    () => ({
      stages,
      running,
      resetStages,
      setOptimisticStart,
      applyEvent,
      setRunning,
    }),
    [stages, running, resetStages, setOptimisticStart, applyEvent],
  );

  return (
    <MatchStatusContext.Provider value={value}>{children}</MatchStatusContext.Provider>
  );
}

export function useMatchStatus(): MatchStatusContextValue {
  const ctx = useContext(MatchStatusContext);
  if (!ctx) {
    throw new Error("useMatchStatus must be used within MatchStatusProvider");
  }
  return ctx;
}

export function stageLabel(stage: string): string {
  if (stage.startsWith("tool:")) {
    return stage.replace("tool:", "Tool · ");
  }
  const map: Record<string, string> = {
    collecting_context: "Collecting context",
    rewriting: "Rewriting query",
    orchestrating: "Orchestrating",
    tool_planning: "Planning tools",
    retrieving: "Retrieving",
    drafting: "Drafting",
    judging: "Judging",
    responding: "Responding",
  };
  return map[stage] || stage.replace(/_/g, " ");
}

export function sortStages(stages: PipelineStage[]): PipelineStage[] {
  return [...stages].sort((a, b) => {
    const ai = STAGE_ORDER.indexOf(a.stage);
    const bi = STAGE_ORDER.indexOf(b.stage);
    const aRank = ai === -1 ? 1000 : ai;
    const bRank = bi === -1 ? 1000 : bi;
    if (aRank !== bRank) return aRank - bRank;
    return a.stage.localeCompare(b.stage);
  });
}
