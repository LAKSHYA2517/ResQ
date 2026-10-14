# Ethics and limits of ResQ-AI

ResQ-AI is a teaching simulator. It decides which simulated person a simulated agent rescues
first. This note says what those decisions rest on, where they would be wrong to trust, and what
a real system would need that this one does not have.

## 1. The priority rule is a value judgement, not a fact

The agent ranks people with

```
Priority(P) = w_r · Risk(P) + w_u · Urgency(P, t) − w_d · PathCost(agent → P)
```

The weights (5, 3, 1 by default) were chosen so that the trade-off is visible on a small grid.
They are not derived from medicine, fire science or any triage standard. Changing them changes
who is rescued first, and no setting is "correct": the formula states a preference about how
much danger outweighs distance.

The interface shows the full breakdown for every person, at every tick, so the judgement is
open to inspection. That is the point of the design. It is not evidence that the judgement is
right.

**The weights can cost lives in the simulation.** In the Triage Dilemma scenario the agent
walks past a nearby safe person to reach a distant one in danger. With these weights both are
saved. With the fire spreading faster, the nearby person can be lost while the agent is away.
The benchmark (`docs/BENCHMARK.md`) shows the same trade-off in numbers: the utility-based
agent rescues the most people overall but pays more path per rescue than an agent that always
takes the nearest person.

## 2. What real triage has that this does not

Real mass-casualty triage (START, SALT and similar protocols) is built on clinical signs,
trained judgement and accountability. Compared with that, ResQ-AI:

- reduces a person to two numbers, risk and urgency, both invented for the scenario;
- treats everyone as identical otherwise: no age, mobility, injury or ability to walk out alone;
- rescues one person at a time and never asks for help;
- has no notion of consent, of a person's own choices, or of responders' safety;
- cannot be held responsible for an outcome.

It must not be used, adapted or cited as a triage system.

## 3. The sensor model is illustrative

Risk comes from a small Bayesian network over simulated smoke, heat and voice sensors. Its
probabilities were picked so that both the prior and the evidence visibly move the answer. They
are not calibrated against real fires or real detectors. A wrong sensor model produces confident
wrong risks, and the exact arithmetic of Bayes' rule does nothing to fix wrong inputs. The
optional sensor-noise parameter shows this directly: with noisy readings the agent's risk
estimate jumps between ticks.

## 4. Worst-case thinking has a cost

The adversarial mode models the fire as an opponent that always makes the most damaging move.
That is a pessimistic assumption, not a prediction. In every shipped scenario with fire the
adversarial fire defeats the agent. An agent that planned only for that worst case would often
give up on rescues that would in fact succeed. Choosing between expected-case and worst-case
planning is itself an ethical choice about which mistakes are more acceptable.

## 5. Why classical AI was used, and what it gives up

Every decision here can be traced: a derived fact has the rule and premises that produced it, a
route has the nodes the search expanded, a replan has the precondition that failed. That
traceability is the reason for using search, logic and planning over learned models in this
project.

The price is brittleness:

- the agent knows only what its ten rules and its cost model say; anything not encoded does
  not exist for it;
- it needs a complete, correct map, which no real building fire provides;
- it does not learn from outcomes, so it repeats a bad policy indefinitely;
- its world is a grid with unit time steps.

A learned system could cope with messier perception but would be harder to audit, could inherit
bias from its training data, and could fail in ways nobody anticipated. Neither approach removes
the need for a human who is responsible for the decision. An explanation of *how* a choice was
computed is not a justification that the choice was *right*.

## 6. Limits of this project, stated plainly

- Simulation only. No real fire detection, no real sensors, no real people.
- All risk, urgency, cost and probability values are made up for demonstration.
- "Optimal" always means optimal for the stated cost model on this grid, verified against
  uniform-cost search. It never means best for the people involved.
- Fire spread is a seeded random process (or a game-playing opponent), not a physical model.
- Perception and language (syllabus Module 7) are out of scope.

## 7. If something like this were ever built for real

It would need, at least: domain experts setting and owning the priorities; validated sensing
with known error rates; a human in command with the system advising, not deciding; testing
against failures of sensing and communication; logs that let every decision be reviewed
afterwards; and clear answers about who is accountable when it is wrong.
