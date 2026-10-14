import { useQuery } from "@tanstack/react-query";
import {
  Bot,
  BrickWall,
  DoorOpen,
  Eraser,
  Flame,
  Grip,
  type LucideIcon,
  MousePointer2,
  Redo2,
  Square,
  Undo2,
  User,
} from "lucide-react";
import { useEffect } from "react";
import { api } from "../api/client";
import { MAX_SIDE, MIN_SIDE, type Tool } from "../lib/draft";
import { useBuilder } from "../store/builder";
import { useSim } from "../store/sim";
import { useUi } from "../store/ui";
import { Btn, Chip, Section } from "./ui";

const TOOLS: { id: Tool; label: string; icon: LucideIcon }[] = [
  { id: "select", label: "Select", icon: MousePointer2 },
  { id: "floor", label: "Floor", icon: Square },
  { id: "rubble", label: "Rubble", icon: Grip },
  { id: "wall", label: "Wall", icon: BrickWall },
  { id: "fire", label: "Fire", icon: Flame },
  { id: "person", label: "Person", icon: User },
  { id: "exit", label: "Exit", icon: DoorOpen },
  { id: "agent", label: "Agent", icon: Bot },
  { id: "erase", label: "Erase", icon: Eraser },
];

const num = (v: string, lo: number, hi: number, fallback: number) => {
  const n = Number(v);
  return Number.isFinite(n) ? Math.min(hi, Math.max(lo, Math.round(n))) : fallback;
};

export function Builder() {
  const b = useBuilder();
  const { start, startDraft, busy } = useSim();
  const setMode = useUi((s) => s.setMode);
  const scenarios = useQuery({ queryKey: ["scenarios"], queryFn: api.scenarios });
  const [rows, cols] = b.draft.grid_size;
  const person = b.draft.people.find((p) => p.id === b.selected);

  // Inline validation: the engine checks the draft; its issues come back with cell positions.
  const { draft, setIssues } = b;
  useEffect(() => {
    let live = true;
    const id = setTimeout(() => {
      api
        .validate(draft)
        .then((v) => live && setIssues(v.issues))
        .catch(() => live && setIssues([]));
    }, 250);
    return () => {
      live = false;
      clearTimeout(id);
    };
  }, [draft, setIssues]);

  const loadPredefined = async (id: string) => {
    const out = await api.scenario(id);
    b.load(out.scenario);
  };

  const go = async () => {
    if (await startDraft(b.draft)) setMode("run");
  };

  return (
    <div className="flex h-full flex-col">
      <div className="min-h-0 flex-1 overflow-y-auto">
        <Section title="Load scenario">
          <div className="flex gap-2">
            <select
              aria-label="Predefined scenario"
              className="min-w-0 flex-1 rounded-md border border-line bg-raised px-2 py-1.5"
              value=""
              onChange={(e) => e.target.value && void loadPredefined(e.target.value)}
            >
              <option value="">Predefined…</option>
              {scenarios.data
                ?.filter((s) => s.predefined)
                .map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
            </select>
          </div>
        </Section>

        <Section
          title="Paint"
          right={
            <div className="flex gap-1">
              <Btn tone="ghost" aria-label="Undo" disabled={!b.past.length} onClick={b.undo}>
                <Undo2 size={15} />
              </Btn>
              <Btn tone="ghost" aria-label="Redo" disabled={!b.future.length} onClick={b.redo}>
                <Redo2 size={15} />
              </Btn>
            </div>
          }
        >
          <div className="grid grid-cols-3 gap-1.5">
            {TOOLS.map((t) => (
              <button
                key={t.id}
                type="button"
                aria-pressed={b.tool === t.id}
                onClick={() => b.setTool(t.id)}
                className={`flex flex-col items-center gap-1 rounded-md border py-2 text-xs ${
                  b.tool === t.id
                    ? "border-accent bg-accent/10 text-accent"
                    : "border-line bg-panel hover:bg-raised"
                }`}
              >
                <t.icon size={16} strokeWidth={1.75} />
                {t.label}
              </button>
            ))}
          </div>
        </Section>

        <Section title="Scenario">
          <label className="mb-2 block text-xs text-dim">
            Name
            <input
              className="mt-1 w-full rounded-md border border-line bg-raised px-2 py-1.5 text-sm text-ink"
              value={b.draft.name}
              onChange={(e) => b.edit((d) => ({ ...d, name: e.target.value }))}
            />
          </label>
          <div className="grid grid-cols-2 gap-2 text-xs text-dim">
            <label>
              Rows
              <input
                type="number"
                min={MIN_SIDE}
                max={MAX_SIDE}
                className="mt-1 w-full rounded-md border border-line bg-raised px-2 py-1.5 text-sm text-ink"
                value={rows}
                onChange={(e) => b.resize(num(e.target.value, MIN_SIDE, MAX_SIDE, rows), cols)}
              />
            </label>
            <label>
              Columns
              <input
                type="number"
                min={MIN_SIDE}
                max={MAX_SIDE}
                className="mt-1 w-full rounded-md border border-line bg-raised px-2 py-1.5 text-sm text-ink"
                value={cols}
                onChange={(e) => b.resize(rows, num(e.target.value, MIN_SIDE, MAX_SIDE, cols))}
              />
            </label>
            <label>
              Fire spread / tick
              <input
                type="number"
                min={0}
                max={1}
                step={0.01}
                className="mt-1 w-full rounded-md border border-line bg-raised px-2 py-1.5 text-sm text-ink"
                value={b.draft.params.p_spread}
                onChange={(e) =>
                  b.edit((d) => ({
                    ...d,
                    params: {
                      ...d.params,
                      p_spread: Math.min(1, Math.max(0, Number(e.target.value) || 0)),
                    },
                  }))
                }
              />
            </label>
            <label>
              Seed
              <input
                type="number"
                className="mt-1 w-full rounded-md border border-line bg-raised px-2 py-1.5 text-sm text-ink"
                value={b.draft.seed}
                onChange={(e) =>
                  b.edit((d) => ({ ...d, seed: Math.round(Number(e.target.value) || 0) }))
                }
              />
            </label>
          </div>
          {b.draft.scripted_events.length > 0 && (
            <p className="mt-2 text-xs text-dim">
              {b.draft.scripted_events.length} scripted event(s):{" "}
              {b.draft.scripted_events.map((e) => `t${e.tick} ${e.type}`).join(", ")}
            </p>
          )}
        </Section>

        {person && (
          <Section
            title={`Person ${person.id}`}
            right={
              <Btn
                tone="danger"
                onClick={() => {
                  b.edit((d) => ({ ...d, people: d.people.filter((p) => p.id !== person.id) }));
                  b.select(null);
                }}
              >
                Delete
              </Btn>
            }
          >
            <div className="grid grid-cols-2 gap-2 text-xs text-dim">
              {(["risk", "urgency"] as const).map((f) => (
                <label key={f}>
                  {f === "risk" ? "Risk (0–5)" : "Urgency (0–5)"}
                  <input
                    type="number"
                    min={0}
                    max={5}
                    className="mt-1 w-full rounded-md border border-line bg-raised px-2 py-1.5 text-sm text-ink"
                    value={person[f]}
                    onChange={(e) => {
                      const v = num(e.target.value, 0, 5, person[f]);
                      b.edit((d) => ({
                        ...d,
                        people: d.people.map((p) => (p.id === person.id ? { ...p, [f]: v } : p)),
                      }));
                    }}
                  />
                </label>
              ))}
            </div>
          </Section>
        )}

        <Section
          title="Validation"
          right={
            b.issues.length === 0 ? (
              <Chip tone="go">valid</Chip>
            ) : (
              <Chip tone="bad">{b.issues.length}</Chip>
            )
          }
        >
          {b.issues.length === 0 ? (
            <p className="text-sm text-dim">Ready to start. The engine found no problems.</p>
          ) : (
            <ul className="space-y-1.5 text-sm">
              {b.issues.map((i) => (
                <li key={`${i.field}:${i.message}:${i.cell?.join(",")}`} className="text-bad">
                  {i.message}
                  {i.cell && (
                    <span className="text-dim">
                      {" "}
                      — ({i.cell[0]}, {i.cell[1]})
                    </span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </Section>
      </div>
      {b.issues.length > 0 && (
        <p className="border-t border-line px-3 pt-2 text-xs text-bad">
          {b.issues.length} problem{b.issues.length > 1 ? "s" : ""}: {b.issues[0]?.message}
        </p>
      )}
      <div className="flex gap-2 border-t border-line p-3">
        <Btn tone="primary" className="flex-1" disabled={busy || b.issues.length > 0} onClick={go}>
          Validate → Start
        </Btn>
        <Btn
          disabled={busy}
          onClick={() => {
            void start("showcase").then(() => setMode("run"));
          }}
        >
          Showcase
        </Btn>
      </div>
    </div>
  );
}
