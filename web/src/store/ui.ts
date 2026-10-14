import { create } from "zustand";
import type { Cell, Compare } from "../api/client";

export type Mode = "build" | "run";
export type Tab =
  | "reasoning"
  | "search"
  | "planning"
  | "uncertainty"
  | "optimize"
  | "agent"
  | "syllabus";
export type Explain = "decision" | "route" | "replan";

export interface Overlay {
  label: string;
  explored: Cell[];
  path: Cell[];
}

interface UiStore {
  mode: Mode;
  tab: Tab;
  overlay: Overlay | null;
  compare: Compare | null; // last search comparison (shared by the Search panel and its results)
  explain: Explain | null;
  showState: boolean; // the "state as structured data" section in Reasoning
  focus: string | null;
  palette: boolean; // command palette open // a section a "Run it" link or demo step asks a panel to act on
  setMode: (m: Mode) => void;
  setTab: (t: Tab) => void;
  setOverlay: (o: Overlay | null) => void;
  setCompare: (c: Compare | null) => void;
  setExplain: (e: Explain | null) => void;
  setShowState: (on: boolean) => void;
  setFocus: (f: string | null) => void;
  setPalette: (on: boolean) => void;
}

export const useUi = create<UiStore>((set) => ({
  mode: "build",
  tab: "reasoning",
  overlay: null,
  compare: null,
  explain: null,
  showState: false,
  focus: null,
  palette: false,
  setMode: (mode) => set({ mode }),
  setTab: (tab) => set({ tab }),
  setOverlay: (overlay) => set({ overlay }),
  setCompare: (compare) => set({ compare }),
  setExplain: (explain) => set({ explain }),
  setShowState: (showState) => set({ showState }),
  setFocus: (focus) => set({ focus }),
  setPalette: (palette) => set({ palette }),
}));
