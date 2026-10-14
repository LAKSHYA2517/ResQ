import { create } from "zustand";
import type { Cell, Issue, Scenario } from "../api/client";
import { blankDraft, paint, resize, type Tool } from "../lib/draft";

const HISTORY_LIMIT = 100;

interface BuilderStore {
  draft: Scenario;
  past: Scenario[];
  future: Scenario[];
  tool: Tool;
  selected: string | null; // person id shown in the inspector
  issues: Issue[];
  stroking: boolean; // a drag started and has not changed anything yet

  setTool: (tool: Tool) => void;
  load: (scenario: Scenario) => void; // replaces the draft; undoable
  beginStroke: () => void; // one undo step per drag
  paintAt: (cell: Cell) => void;
  edit: (fn: (d: Scenario) => Scenario) => void;
  resize: (rows: number, cols: number) => void;
  select: (personId: string | null) => void;
  undo: () => void;
  redo: () => void;
  setIssues: (issues: Issue[]) => void;
}

export const useBuilder = create<BuilderStore>((set, get) => {
  const commit = (next: Scenario) =>
    set((s) => ({
      draft: next,
      past: [...s.past, s.draft].slice(-HISTORY_LIMIT),
      future: [],
    }));

  return {
    draft: blankDraft(),
    past: [],
    future: [],
    tool: "wall",
    selected: null,
    issues: [],
    stroking: false,

    setTool: (tool) => set({ tool }),
    load: (scenario) => {
      commit(scenario);
      set({ selected: null, issues: [] });
    },

    beginStroke: () => set({ stroking: true }),

    paintAt: (cell) => {
      const { draft, tool, stroking } = get();
      if (tool === "select") {
        const hit = draft.people.find((p) => p.pos[0] === cell[0] && p.pos[1] === cell[1]);
        set({ selected: hit?.id ?? null });
        return;
      }
      const next = paint(draft, cell, tool);
      if (next !== draft) {
        // one undo step per drag, recorded at its first real change
        set((s) => ({
          draft: next,
          past: stroking ? [...s.past, s.draft].slice(-HISTORY_LIMIT) : s.past,
          future: stroking ? [] : s.future,
          stroking: false,
        }));
      }
      if (tool === "person") {
        const hit = next.people.find((p) => p.pos[0] === cell[0] && p.pos[1] === cell[1]);
        set({ selected: hit?.id ?? null });
      }
    },

    edit: (fn) => commit(fn(get().draft)),
    resize: (rows, cols) => commit(resize(get().draft, rows, cols)),
    select: (selected) => set({ selected }),

    undo: () =>
      set((s) => {
        const prev = s.past[s.past.length - 1];
        if (!prev) return s;
        return { draft: prev, past: s.past.slice(0, -1), future: [s.draft, ...s.future] };
      }),
    redo: () =>
      set((s) => {
        const [next, ...rest] = s.future;
        if (!next) return s;
        return { draft: next, past: [...s.past, s.draft], future: rest };
      }),

    setIssues: (issues) => set({ issues }),
  };
});
