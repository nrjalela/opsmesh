import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { loadDecisions, saveDecisions, withDecisions } from "./model";
import type { Batch, Decision, Run } from "./types";

interface AppState {
  batch: Batch;
  runs: Run[];
  byId: Record<string, Run>;
  decisions: Record<string, Decision>;
  decide: (docId: string, decision: Decision["decision"], note: string, reviewer: string) => void;
  undo: (docId: string) => void;
  resetAll: () => void;
}

const Ctx = createContext<AppState | null>(null);

export function AppProvider({ batch, children }: { batch: Batch; children: ReactNode }) {
  const [decisions, setDecisions] = useState<Record<string, Decision>>(() => loadDecisions());

  const update = useCallback((next: Record<string, Decision>) => {
    setDecisions(next);
    saveDecisions(next);
  }, []);

  const decide = useCallback<AppState["decide"]>(
    (docId, decision, note, reviewer) =>
      update({ ...decisions, [docId]: { decision, note, reviewer, decidedAt: new Date().toISOString() } }),
    [decisions, update],
  );
  const undo = useCallback(
    (docId: string) => {
      const next = { ...decisions };
      delete next[docId];
      update(next);
    },
    [decisions, update],
  );
  const resetAll = useCallback(() => update({}), [update]);

  const value = useMemo<AppState>(() => {
    const runs = withDecisions(batch, decisions);
    return { batch, runs, byId: Object.fromEntries(runs.map((r) => [r.doc_id, r])), decisions, decide, undo, resetAll };
  }, [batch, decisions, decide, undo, resetAll]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useApp(): AppState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useApp outside AppProvider");
  return v;
}
