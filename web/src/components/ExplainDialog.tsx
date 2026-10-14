import * as Dialog from "@radix-ui/react-dialog";
import { eventsOf, keyed } from "../lib/trace";
import { useView } from "../store/sim";
import { useUi } from "../store/ui";
import { Btn } from "./ui";

/** "Explain this decision": the exact engine trace behind the target, the route or a replan. */
export function ExplainDialog() {
  const view = useView();
  const explain = useUi((s) => s.explain);
  const setExplain = useUi((s) => s.setExplain);
  if (!view || !explain) return null;

  const about = (view.target ?? "").toLowerCase();
  const provenance = view.derived.filter(
    (d) =>
      `${d.fact} ${d.premises.join(" ")}`.toLowerCase().includes(`(${about})`) ||
      d.fact.toLowerCase().includes(`(${about},`) ||
      d.premises.some(
        (p) => p.toLowerCase().includes(`(${about},`) || p.toLowerCase().includes(`(${about})`),
      ),
  );

  const title = {
    decision: `Why ${view.target ?? "nobody"}?`,
    route: "Why this route?",
    replan: "Why did the plan change?",
  }[explain];

  const trace =
    explain === "decision"
      ? eventsOf(view, "TargetChosen", "PlanFound", "PlanAdopted")
      : explain === "route"
        ? eventsOf(view, "RouteComputed", "PlanFound")
        : eventsOf(
            view,
            "EventApplied",
            "EventRejected",
            "FireSpread",
            "PlanInvalidated",
            "PlanAdopted",
            "RouteComputed",
            "PlanFound",
            "NoValidPlan",
          );

  return (
    <Dialog.Root open onOpenChange={(open) => !open && setExplain(null)}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/60" />
        <Dialog.Content className="fixed top-1/2 left-1/2 z-50 max-h-[85vh] w-[min(720px,92vw)] -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-lg border border-line bg-panel p-5 shadow-2xl">
          <Dialog.Title className="text-lg font-semibold">{title}</Dialog.Title>
          <Dialog.Description className="mb-4 text-sm text-dim">
            Everything below is the engine's own trace for tick {view.tick}.
          </Dialog.Description>

          {explain === "decision" && (
            <>
              <h4 className="mb-1 text-[13px] font-semibold text-ink">Priority scores</h4>
              <ul className="mb-4 space-y-1 font-mono text-xs">
                {view.priorities.map((p) => (
                  <li key={p.person_id}>{p.breakdown}</li>
                ))}
              </ul>
              <h4 className="mb-1 text-[13px] font-semibold text-ink">
                Facts the knowledge base derived about {view.target ?? "the target"}
              </h4>
              {provenance.length === 0 ? (
                <p className="mb-4 text-sm text-dim">None.</p>
              ) : (
                <ul className="mb-4 space-y-1.5 font-mono text-xs">
                  {provenance.map((d) => (
                    <li key={d.fact}>
                      <span className="text-go">{d.fact}</span>{" "}
                      <span className="text-dim">
                        ← {d.premises.join(" & ")} [{d.rule}, pass {d.iteration}]
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </>
          )}

          {explain === "replan" && view.plan_change && (
            <div className="mb-4 rounded border border-warn/50 bg-warn/5 p-3 text-sm">
              <div className="font-semibold text-warn">
                {view.plan_change.kind.replace("_", " ")}
              </div>
              <div>{view.plan_change.reason}</div>
              <div className="mt-2 font-mono text-xs text-dim">
                before: {view.plan_change.old_steps.join(" → ") || "no plan"}
                <br />
                after:{" "}
                {view.plan
                  .map((s) =>
                    s.route.length > 1 ? `${s.label} [${s.route.length - 1} moves]` : s.label,
                  )
                  .join(" → ") || "no plan"}
              </div>
              {view.plan.map((s) => s.label).join() === view.plan_change.old_steps.join() && (
                <p className="mt-2 text-xs text-dim">
                  Same waypoints as before: the plan was kept but the route between them changed.
                </p>
              )}
            </div>
          )}

          <h4 className="mb-1 text-[13px] font-semibold text-ink">Engine trace</h4>
          {trace.length === 0 ? (
            <p className="text-sm text-dim">
              The agent did not search or decide anything this tick.
            </p>
          ) : (
            <ol className="space-y-1 font-mono text-xs">
              {keyed(trace).map((l) => (
                <li key={l.key} className="text-dim">
                  <span className="text-ink">{l.event.kind}</span> {l.text}
                </li>
              ))}
            </ol>
          )}
          <div className="mt-5 text-right">
            <Dialog.Close asChild>
              <Btn>Close</Btn>
            </Dialog.Close>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
