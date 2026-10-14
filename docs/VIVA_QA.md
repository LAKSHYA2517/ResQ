# Viva questions and answers

Short answers, each tied to what the project actually does. File paths are under
`engine/resq/`.

## Agents and environments

**1. What kind of agent is this?**
A utility-based, goal-driven agent with an internal model. It keeps a knowledge base, picks a
goal with a priority (utility) function, plans to reach it, and monitors execution
(`agent/loop.py`).

**2. Give the PEAS description.**
Performance: people evacuated, path cost, ticks, replans. Environment: grid with floor, rubble,
walls, fire, people, exits. Actuators: move one cell, pick up, drop off. Sensors: the map plus
smoke, heat and voice readings per person.

**3. Is the environment deterministic?**
It depends on the scenario, and the Agent tab derives it. With `p_spread = 0` and no sensor
noise it is deterministic. With spreading fire or noisy sensors it is stochastic, though seeded,
so every run is reproducible. In worst-case mode the fire is an opponent: strategic, not random.

**4. Static or dynamic? Episodic or sequential?**
Dynamic whenever fire spreads or scripted events exist, static otherwise. Always sequential:
each move changes who can still be reached.

**5. Why build reflex and goal-based agents too?**
To measure what the extra machinery buys. On the 10 predefined and 20 random scenarios the
utility agent rescues 90.2%, goal-based 87.8%, reflex 53.7%. The utility agent pays more path
per rescue because it goes for the most endangered person first (`docs/BENCHMARK.md`).

## Search

**6. Why are BFS and UCS different here?**
Step costs differ: floor 1, rubble 3, and +4 for a cell next to fire. BFS finds the fewest
steps, UCS the cheapest path. On Showcase towards p1, BFS costs 8 and UCS 6.

**7. Why is A* optimal here?**
The heuristic is Manhattan distance times the cheapest possible step cost. It never
overestimates (admissible) and satisfies h(n) ≤ c(n, n′) + h(n′) (consistent), because one move
changes Manhattan distance by at most 1 and costs at least the cheapest step. The heuristic lab
checks both conditions on every cell, and a property test checks A* cost = UCS cost on random
grids.

**8. How is "optimal" shown in the UI?**
It is computed. Every comparison runs a reference UCS and marks each algorithm optimal only if
its cost equals UCS's.

**9. What happens with an inadmissible heuristic?**
Weighted A* (w × h with w > 1) expands fewer nodes but can return a costlier path, at most w
times optimal when h is admissible. The lab reports the cells where it overestimates.

**10. Why is IDDFS's "expanded" count so high?**
It redoes every shallower depth on each iteration. It finds the fewest-steps path like BFS while
storing only a path's worth of frontier.

**11. How do DLS and IDDFS avoid cycles?**
A depth-stamped explored set: a cell is expanded again only if reached at a shallower depth. A
plain explored set would make IDDFS incomplete; checking only the current path would be
exponential on an open grid.

**12. How are ties broken?**
Successors in the order up, down, left, right. Best-first ties go to lowest f, then lowest h,
then first generated. So every run is reproducible.

## Local and adversarial search

**13. What does the order optimiser minimise?**
The sum over people of weight × completion time, with weight = 5·Risk + 3·Urgency and real A*
leg costs. Exhaustive search over all orders gives the true optimum for up to 7 people
(5040 orders), so we can measure how close hill climbing, annealing and the GA get.

**14. Why use random restarts and annealing?**
Hill climbing stops at the first local optimum. Restarts try other starting points. Annealing
accepts a worse move with probability exp(−Δ/T), where T cools geometrically, so it can escape
early and settles later.

**15. How does the genetic algorithm keep orders valid?**
Order crossover keeps a slice of one parent and fills the rest in the other parent's order, so
every child is a permutation. Mutation swaps two positions; the best individual is always kept.

**16. Who are MAX and MIN in the fire game?**
The agent is MIN, minimising the cost to finish its current leg. The fire is MAX, igniting
frontier cells to raise that cost, ideally to infinity by cutting the agent off.

**17. Why do minimax and alpha-beta choose the same move?**
Alpha-beta only skips subtrees that cannot change the result. Both use a strict "better than"
comparison in the same move order, so on ties the first move wins in both. A property test
checks same value and same move on random trees; on Showcase alpha-beta visits 29 nodes against
58.

## Logic

**18. What is the closed-world assumption here?**
Anything not stated or derivable is false. Rules contain no negation. "Exit e1 is open" is
answered by failing to find `Unavailable(e1)`.

**19. How do forward and backward chaining differ?**
Forward chaining starts from the facts and fires every rule until nothing new appears (data
driven; it derives everything). Backward chaining starts from a goal and works back through
rules to base facts (goal driven; it touches only what the goal needs).

**20. How do you know the reasoning is right?**
The same goal is answered three independent ways in "Prove it": forward chaining, backward
chaining from base facts only, and resolution refutation. Tests check that they agree on every
goal in every scenario.

**21. What is unification, and why the occurs check?**
Finding the most general substitution that makes two terms identical. The occurs check rejects
binding X to a term containing X, such as f(X), which would build an infinite term.

**22. How does resolution prove a goal?**
Add the negated goal to the clauses and resolve until the empty clause appears: a
contradiction, so the goal must hold. The strategy is set of support with input resolution,
which is complete for Horn clauses.

**23. Why are Reachable and Urgent base facts and not rules?**
They need search and arithmetic, which Horn clauses over symbols cannot do. A* decides
reachability and the urgency formula decides urgency; the results enter the KB as facts, and
`Eligible(P)` is then derived. That is the loop between search and reasoning.

## Uncertainty

**24. What does the Bayesian network condition on?**
Per person: Fire causes Smoke, Heat and Trapped; Trapped causes Voice. We observe Smoke, Heat
and Voice and query Trapped. The prior P(Fire) comes from the scenario's baseline risk. Then
Risk(P) = round(5 × P(Trapped | readings)).

**25. Enumeration vs variable elimination?**
Same answer. Enumeration sums the full joint over hidden variables, exponential in their
number. Elimination multiplies only the factors that mention a variable and sums it out. A test
on a 12-node chain shows 2048 terms against under 200 table rows.

**26. Why does rejection sampling do badly with unlikely evidence?**
It discards every sample that contradicts the evidence; with rare evidence most are thrown away.
Likelihood weighting fixes the evidence and weights each sample instead. Gibbs sampling walks a
Markov chain, resampling one variable at a time given its Markov blanket.

## Planning

**27. Forward vs regression planning?**
Forward search expands world states from the start. Regression expands sets of sub-goals from
the goal, replacing what an action achieves by its preconditions. Both use uniform cost or an
admissible heuristic, so both are optimal and their costs must match (a property test checks
this).

**28. What is the planning graph's level for?**
The first level where all goals appear without a mutex is a lower bound on plan length. It is
polynomial to build, while the state space can be exponential.

**29. When does the agent replan?**
When the plan is invalid (a route cell burns, an exit is blocked, a person is trapped), when
another person beats the current target by more than delta, or when the world changed and a
strictly cheaper plan exists. Each replan is logged with its reason.

**30. Why have hysteresis (delta)?**
Priorities are recomputed every tick. Without a margin, small changes would make the agent
switch targets back and forth and finish nobody.

## Engineering

**31. How can you rebuild any past tick?**
A run is the scenario, its seed and the log of user events. Fire spread uses an RNG seeded per
tick. Replaying from scratch gives identical snapshots, which the scrubber, tests and the run
report all check.

**32. How do you know the UI is not faking results?**
The engine has no web code; the API copies engine values; the frontend only renders. A browser
test steps through a whole run and compares every tick on screen with the engine's response, and
a source audit finds no hardcoded results.
