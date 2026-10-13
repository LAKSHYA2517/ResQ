import { create } from "zustand";
import type { Cell, Compare } from "../api/client";

export type Mode = "build" | "run";
export type Tab = "reasoning" | "search" | "planning";
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
  compare: Compare | null; // last search comparison (shared by the panel and the guided demo)
  explain: Explain | null;
  showState: boolean; // the "state as structured data" section in Reasoning
  demoStep: number | null; // null = guided demo is off
  setMode: (m: Mode) => void;
  setTab: (t: Tab) => void;
  setOverlay: (o: Overlay | null) => void;
  setCompare: (c: Compare | null) => void;
  setExplain: (e: Explain | null) => void;
  setShowState: (on: boolean) => void;
  setDemoStep: (n: number | null) => void;
}

export const useUi = create<UiStore>((set) => ({
  mode: "build",
  tab: "reasoning",
  overlay: null,
  compare: null,
  explain: null,
  showState: false,
  demoStep: null,
  setMode: (mode) => set({ mode }),
  setTab: (tab) => set({ tab }),
  setOverlay: (overlay) => set({ overlay }),
  setCompare: (compare) => set({ compare }),
  setExplain: (explain) => set({ explain }),
  setShowState: (showState) => set({ showState }),
  setDemoStep: (demoStep) => set({ demoStep }),
}));
