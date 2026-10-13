import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { api } from "../api/client";
import { MAX_SIDE, MIN_SIDE, parseImported, type Tool } from "../lib/draft";
import { useBuilder } from "../store/builder";
import { useSim } from "../store/sim";
import { useUi } from "../store/ui";
import { Btn, Chip, Section } from "./ui";

const TOOLS: { id: Tool; label: string; glyph: string }[] = [
  { id: "select", label: "Select", glyph: "⌖" },
  { id: "floor", label: "Floor", glyph: "·" },
  { id: "rubble", label: "Rubble", glyph: "▨" },
  { id: "wall", label: "Wall", glyph: "▦" },
  { id: "fire", label: "Fire", glyph: "♨" },
  { id: "person", label: "Person", glyph: "☺" },
  { id: "exit", label: "Exit", glyph: "⇥" },
  { id: "agent", label: "Agent", glyph: "◈" },
  { id: "erase", label: "Erase", glyph: "✕" },
];

const num = (v: string, lo: number, hi: number, fallback: number) => {
  const n = Number(v);
  return Number.isFinite(n) ? Math.min(hi, Math.max(lo, Math.round(n))) : fallback;
};

export function Builder() {
  const b = useBuilder();
  const { start, startDraft, busy } = useSim();
  const setMode = useUi((s) => s.setMode);
  const file = useRef<HTMLInputElement>(null);
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

  const exportJson = () => {
    const blob = new Blob([JSON.stringify(b.draft, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `${b.draft.name.replace(/\W+/g, "_") || "scenario"}.json`;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  const importJson = async (f: File | undefined) => {
    if (!f) return;
    try {
      b.load(parseImported(await f.text()));
    } catch (e) {
      useSim.setState({ error: `Could not import ${f.name}: ${(e as Error).message}` });
    }
    if (file.current) file.current.value = "";
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
          <div className="mt-2 flex flex-wrap gap-2">
            <Btn onClick={() => file.current?.click()}>Import JSON</Btn>
            <Btn onClick={exportJson}>Export JSON</Btn>
            <Btn onClick={b.save}>Save here</Btn>
            <input
              ref={file}
              type="file"
              accept="application/json,.json"
              className="hidden"
              aria-label="Import scenario file"
              onChange={(e) => void importJson(e.target.files?.[0])}
            />
          </div>
          {b.library.length > 0 && (
            <ul className="mt-2 space-y-1">
              {b.library.map((l) => (
                <li key={l.name} className="flex items-center gap-2 text-sm">
                  <button
                    type="button"
                    className="min-w-0 flex-1 truncate text-left text-accent hover:underline"
                    onClick={() => b.load(l.scenario)}
                  >
                    {l.name}
                  </button>
                  <button
                    type="button"
                    aria-label={`Delete saved ${l.name}`}
                    className="text-dim hover:text-bad"
                    onClick={() => b.remove(l.name)}
                  >
                    ✕
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Section>

        <Section
          title="Paint"
          right={
            <div className="flex gap-1">
              <Btn aria-label="Undo" disabled={!b.past.length} onClick={b.undo}>
                ↶
              </Btn>
              <Btn aria-label="Redo" disabled={!b.future.length} onClick={b.redo}>
                ↷
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
                className={`rounded-md border px-1 py-1.5 text-xs ${
                  b.tool === t.id
                    ? "border-accent bg-accent/15 text-accent"
                    : "border-line bg-raised"
                }`}
              >
                <span className="mr-1 text-base">{t.glyph}</span>
                {t.label}
              </button>
            ))}
          </div>
          <p className="mt-2 text-xs text-dim">Drag on the grid to paint terrain, fire or erase.</p>
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
