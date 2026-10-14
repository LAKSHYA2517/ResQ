# Demo script (about 12 minutes)

For the presenter. The guided demo does most of the clicking; this script says what to say and
what to point at.

## Before the session

1. `make dev`, open <http://localhost:5173>, check the header says **engine v0.1.0** in green.
2. Optional dry run: `make demo` in a terminal prints the same workflow without a browser.

If the API is down, the header shows **engine API unreachable** in red. Restart `make dev`.

## The walkthrough

Press **▶ Guided demo**. Use **Next →** to advance. Each step makes real engine calls.

| Step | Point at | Say |
|---|---|---|
| 1 Load Showcase | The grid | One agent, three people, rubble, walls, a spreading fire, two exits. |
| 2 State as data | Logic tab, structured state | The picture is just a view of this data. |
| 3 Facts and rules | Base facts, rules list | The state becomes facts; ten Horn rules say what follows. Closed world. |
| 4 Forward chaining | Derived facts by pass, highlighted cells | Rules fire to a fixpoint. Click AtRisk(p2): rule, bindings, premises. |
| 5 Prove it | The three result blocks | Same question three ways; they must agree. Point at the empty clause. |
| 6 Bayes | Bayes tab, beliefs | p2's sensors all fire: posterior ≈ 0.91, Risk 5. The others read clear. |
| 7 Priority | Plan tab, breakdown lines | Far, critical p2 outranks near, safe p1. These are simulation weights. |
| 8 Algorithm race | The race dialog | Same problem, same pace. A* expands fewer cells than UCS for the same cost; DFS is costlier. Close the dialog to continue. |
| 9 Order optimizer | Optimize tab | Three people only, so all methods find the optimum. Mass Evacuation shows the gaps. |
| 10 Plan | Plan tab, planner comparison | Forward and regression planners agree on cost. Below: HTN tree and planning graph. |
| 11 Execute | The grid | One validated action per tick while the fire spreads. |
| 12 Fire on the route | The replan | A fire two cells ahead. The plan's precondition fails. |
| 13 Fact diff | Logic tab diff, Plan tab replan card | Exactly which facts changed, and the stated reason. |
| 14 Adversarial fire | Optimize tab | Minimax vs alpha-beta: same move, about half the nodes. |
| 15 Final outcome | Sidebar metrics, timeline | Run to the end. Scrub back: every tick is rebuilt from seed and log. |
| 16 Benchmark | Agent tab | Reflex vs goal-based vs utility-based, measured. Utility rescues most, at a higher cost per rescue. |
| 17 Impossible | Plan tab, reasons | No route exists. The agent says so and why; it never invents one. |

Finish on **⤓ Report** to show the exportable run report, and on the Syllabus tab to show that
every module is covered.

## Likely live questions

Keep [VIVA_QA.md](VIVA_QA.md) open. The most common: why A* is optimal here (Q7), why UCS differs
from BFS (Q6), why alpha-beta picks the same move (Q17), and what the Bayes net conditions on
(Q24).

## If something goes wrong

- **Step stuck on "Working…"**: the engine is still computing; wait a few seconds.
- **Race dialog covers the Next button**: close it; the demo continues.
- **Wrong scenario loaded**: open the palette (Ctrl/Cmd+K), type the scenario name, press
  Enter, then restart the guided demo.
- **Results differ from this script**: they are computed live. If an agent change altered a
  run, the numbers on screen are the true ones; the script's examples may be stale.
