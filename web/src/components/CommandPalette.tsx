import * as Dialog from "@radix-ui/react-dialog";
import { useQuery } from "@tanstack/react-query";
import { Command } from "cmdk";
import { api } from "../api/client";
import { saveReport } from "../lib/report";
import { useSim } from "../store/sim";
import { type Tab, useUi } from "../store/ui";

const TABS: [Tab, string][] = [
  ["reasoning", "Logic: facts, rules, Prove it"],
  ["search", "Search: compare, race, heuristic lab"],
  ["planning", "Plan: plan, planners, HTN, planning graph"],
  ["uncertainty", "Bayes: beliefs and inference lab"],
  ["optimize", "Optimize: rescue order and adversarial fire"],
  ["agent", "Agent: PEAS, environment, benchmark"],
  ["syllabus", "Syllabus coverage"],
];

/** Ctrl/Cmd+K: every main action by name. Each item calls the same store actions as the
 * buttons do, so nothing here computes anything of its own. */
export function CommandPalette() {
  const open = useUi((s) => s.palette);
  const setOpen = useUi((s) => s.setPalette);
  const ui = useUi();
  const sim = useSim();
  const scenarios = useQuery({ queryKey: ["scenarios"], queryFn: api.scenarios });
  const live = sim.head !== null;

  const run = (fn: () => unknown) => {
    setOpen(false);
    void fn();
  };

  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/60" />
        <Dialog.Content className="fixed top-24 left-1/2 z-50 w-[min(560px,92vw)] -translate-x-1/2 overflow-hidden rounded-lg border border-line bg-panel shadow-2xl">
          <Dialog.Title className="sr-only">Command palette</Dialog.Title>
          <Dialog.Description className="sr-only">Type to find an action</Dialog.Description>
          <Command
            label="Command palette"
            className="text-sm"
            // plain "contains every typed word" matching: cmdk's fuzzy score ranked unrelated
            // commands above exact ones (typing "triage" selected "Export run report")
            filter={(value, search) =>
              search
                .toLowerCase()
                .split(/\s+/)
                .every((w) => value.toLowerCase().includes(w))
                ? 1
                : 0
            }
          >
            <Command.Input
              autoFocus
              placeholder="Type a command…"
              className="w-full border-b border-line bg-transparent px-4 py-3 text-base text-ink outline-none"
            />
            <Command.List className="max-h-[60vh] overflow-y-auto p-2">
              <Command.Empty className="px-3 py-4 text-dim">No matching command.</Command.Empty>
              <Command.Group heading="Run" className="text-xs text-dim">
                {live && !sim.head?.finished && (
                  <Item onSelect={() => run(() => sim.setRunning(!sim.running))}>
                    {sim.running ? "Pause" : "Play"} <Kbd>space</Kbd>
                  </Item>
                )}
                {live && (
                  <Item onSelect={() => run(sim.step)}>
                    Step one tick <Kbd>→</Kbd>
                  </Item>
                )}
                {live && <Item onSelect={() => run(sim.reset)}>Reset to tick 0</Item>}
                {live && sim.head && sim.head.route.length > 3 && (
                  <Item
                    onSelect={() =>
                      run(() => {
                        const cell = sim.head?.route[2];
                        if (cell) return sim.inject("NEW_FIRE", { pos: cell });
                      })
                    }
                  >
                    Inject a fire on the route ahead
                  </Item>
                )}
                {live && sim.sessionId && (
                  <Item
                    onSelect={() =>
                      run(async () => saveReport(await api.report(sim.sessionId ?? "")))
                    }
                  >
                    Export run report (JSON + printable page)
                  </Item>
                )}
                <Item onSelect={() => run(() => ui.setMode("build"))}>
                  Open the scenario builder
                </Item>
              </Command.Group>
              <Command.Group heading="Panels" className="mt-2 text-xs text-dim">
                {TABS.map(([id, label]) => (
                  <Item key={id} onSelect={() => run(() => ui.setTab(id))}>
                    {label}
                  </Item>
                ))}
              </Command.Group>
              <Command.Group heading="Start a scenario" className="mt-2 text-xs text-dim">
                {scenarios.data?.map((s) => (
                  <Item
                    key={s.id}
                    value={`start scenario ${s.name}`}
                    onSelect={() =>
                      run(async () => {
                        await sim.start(s.id);
                        ui.setMode("run");
                      })
                    }
                  >
                    {s.name}
                    <span className="ml-2 text-dim">
                      {s.people} people · {s.rows}×{s.cols}
                    </span>
                  </Item>
                ))}
              </Command.Group>
            </Command.List>
          </Command>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function Item({
  children,
  onSelect,
  value,
}: {
  children: React.ReactNode;
  onSelect: () => void;
  value?: string;
}) {
  return (
    <Command.Item
      value={value}
      onSelect={onSelect}
      className="flex cursor-pointer items-center justify-between rounded px-3 py-2 text-sm text-ink data-[selected=true]:bg-accent/15 data-[selected=true]:text-accent"
    >
      {children}
    </Command.Item>
  );
}

function Kbd({ children }: { children: React.ReactNode }) {
  return (
    <kbd className="ml-auto rounded border border-line px-1.5 text-xs text-dim">{children}</kbd>
  );
}
