import { useMutation } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api, type ProofNode } from "../api/client";
import { Btn, Chip, Section } from "../components/ui";
import { cellsIn } from "../lib/cells";
import { useSim, useView } from "../store/sim";
import { useUi } from "../store/ui";

function Tree({ node, depth = 0 }: { node: ProofNode; depth?: number }) {
  const setHighlight = useSim((s) => s.setHighlight);
  return (
    <li>
      <button
        type="button"
        className="rounded px-1 text-left font-mono text-xs hover:bg-raised"
        onClick={() => setHighlight(cellsIn(node.goal))}
      >
        <span className={node.rule ? "text-go" : "text-ink"}>{node.goal}</span>
        <span className="ml-2 text-dim">{node.rule ? `by ${node.rule}` : "base fact"}</span>
      </button>
      {node.children.length > 0 && (
        <ul className="ml-3 border-l border-line pl-2">
          {node.children.map((c, i) => (
            // biome-ignore lint/suspicious/noArrayIndexKey: premises are positional in a rule body
            <Tree key={`${c.goal}-${i}`} node={c} depth={depth + 1} />
          ))}
        </ul>
      )}
    </li>
  );
}

/** "Prove it": one goal answered by forward chaining, backward chaining and resolution. */
export function ProveIt() {
  const view = useView();
  const sessionId = useSim((s) => s.sessionId);
  const focus = useUi((s) => s.focus);
  const setFocus = useUi((s) => s.setFocus);
  const [goal, setGoal] = useState("AtRisk(P)");
  const ask = useMutation({
    mutationFn: (g: string) => api.kbQuery(sessionId ?? "", g, view?.tick),
  });

  // biome-ignore lint/correctness/useExhaustiveDependencies: fire once per focus request
  useEffect(() => {
    if (focus?.startsWith("prove:") && sessionId) {
      const g = focus.slice(6);
      setFocus(null);
      setGoal(g);
      ask.mutate(g);
    }
  }, [focus, sessionId]);

  if (!view || !sessionId) return null;
  const target = view.target ?? view.state.people[0]?.id ?? "p1";
  const examples = [`AtRisk(${target})`, "Eligible(P)", `RescueNow(${target})`, "Unsafe(X)"];
  const out = ask.data;

  return (
    <Section title="Prove it">
      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          ask.mutate(goal);
        }}
      >
        <input
          aria-label="Goal to prove"
          className="min-w-0 flex-1 rounded-md border border-line bg-raised px-2 py-1.5 font-mono text-sm"
          value={goal}
          onChange={(e) => setGoal(e.target.value)}
          placeholder="AtRisk(p2)  or  Eligible(P)"
          spellCheck={false}
        />
        <Btn tone="primary" type="submit" disabled={ask.isPending || !goal.trim()}>
          Prove
        </Btn>
      </form>
      <div className="mt-1.5 flex flex-wrap gap-1.5">
        {examples.map((g) => (
          <button
            key={g}
            type="button"
            className="rounded border border-line px-1.5 py-0.5 font-mono text-xs text-dim hover:text-accent"
            onClick={() => {
              setGoal(g);
              ask.mutate(g);
            }}
          >
            {g}
          </button>
        ))}
      </div>
      <p className="mt-1.5 text-xs text-dim">
        Uppercase arguments are variables; lowercase are constants.
      </p>
      {ask.isError && <p className="mt-2 text-sm text-bad">{ask.error.message}</p>}

      {out && (
        <div className="mt-3 space-y-3">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="font-mono text-sm">{out.goal}</span>
            <Chip tone={out.forward.holds ? "go" : "bad"}>
              {out.forward.holds ? "✓ holds" : "✗ does not hold"}
            </Chip>
            <Chip tone={out.agree ? "go" : "bad"}>
              {out.agree ? "all methods agree" : "METHODS DISAGREE"}
            </Chip>
          </div>

          <div>
            <h4 className="text-xs font-semibold text-dim">
              1 · Forward chaining ({out.forward.passes} passes to the fixpoint)
            </h4>
            {!out.ground && out.forward.answers.length > 0 && (
              <p className="font-mono text-xs">
                {out.forward.answers
                  .map((a) =>
                    Object.entries(a)
                      .map(([k, v]) => `${k}=${v}`)
                      .join(", "),
                  )
                  .join("  |  ")}
              </p>
            )}
            {out.forward.derivations.length > 0 ? (
              <ol className="mt-1 space-y-0.5 font-mono text-xs">
                {out.forward.derivations.map((d) => (
                  <li key={d.fact}>
                    <span className="text-dim">pass {d.iteration}:</span>{" "}
                    <span className="text-go">{d.fact}</span>{" "}
                    <span className="text-dim">
                      ← {d.premises.join(" & ")} [{d.rule}]
                    </span>
                  </li>
                ))}
              </ol>
            ) : (
              out.ground && (
                <p className="text-xs text-dim">
                  {out.forward.holds
                    ? "A base fact: true because the state says so."
                    : "Not in the fixpoint."}
                </p>
              )
            )}
          </div>

          <div>
            <h4 className="text-xs font-semibold text-dim">
              2 · Backward chaining ({out.backward.length} proof
              {out.backward.length === 1 ? "" : "s"}, {out.backward_steps} goals tried)
            </h4>
            {out.backward.length === 0 && (
              <p className="text-xs text-dim">No proof: every branch failed.</p>
            )}
            {out.backward.slice(0, 6).map((p) => (
              <div key={JSON.stringify(p.bindings)} className="mt-1">
                {Object.keys(p.bindings).length > 0 && (
                  <div className="font-mono text-xs text-accent">
                    {Object.entries(p.bindings)
                      .map(([k, v]) => `${k} = ${v}`)
                      .join(", ")}
                  </div>
                )}
                <ul>
                  <Tree node={p.tree} />
                </ul>
              </div>
            ))}
            {out.backward.length > 6 && (
              <p className="mt-1 text-xs text-dim">…and {out.backward.length - 6} more answers.</p>
            )}
          </div>

          <div>
            <h4 className="text-xs font-semibold text-dim">3 · Resolution refutation</h4>
            {!out.resolution ? (
              <p className="text-xs text-dim">Needs a ground goal (no variables).</p>
            ) : out.resolution.entailed ? (
              <ol className="mt-1 space-y-1 font-mono text-xs">
                {out.resolution.steps.map((s, i) => (
                  // biome-ignore lint/suspicious/noArrayIndexKey: steps are an ordered derivation
                  <li key={i}>
                    <span className="text-dim">{i + 1}.</span>{" "}
                    <span className={s.clause === "□" ? "text-go" : ""}>{s.clause}</span>
                    {s.side ? (
                      <span className="block pl-5 text-dim">
                        resolve with {s.side} [{s.side_name}]
                      </span>
                    ) : (
                      <span className="block pl-5 text-dim">negated goal (assume it is false)</span>
                    )}
                  </li>
                ))}
                <li className="text-go">
                  Empty clause □ reached: contradiction, so the goal holds.
                </li>
              </ol>
            ) : (
              <p className="text-xs text-dim">
                No refutation after {out.resolution.resolvents} resolvents: {out.resolution.reason}.
              </p>
            )}
          </div>
        </div>
      )}
    </Section>
  );
}
