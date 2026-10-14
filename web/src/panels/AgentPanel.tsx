import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { Empty, Section } from "../components/ui";
import { useSim } from "../store/sim";
import { Benchmark } from "./Benchmark";

export function AgentPanel() {
  const sessionId = useSim((s) => s.sessionId);
  const profile = useQuery({
    queryKey: ["profile", sessionId],
    queryFn: () => api.profile(sessionId ?? ""),
    enabled: !!sessionId,
  });
  if (!sessionId) return <Empty>Start a scenario to see the agent and its environment.</Empty>;
  if (profile.isError) return <Empty>Could not load the agent profile.</Empty>;
  const p = profile.data;
  if (!p) return <Empty>Loading…</Empty>;
  return (
    <div className="h-full overflow-y-auto">
      <Section title="Agent type">
        <p className="text-sm">{p.agent_type}</p>
      </Section>
      <Section title="PEAS">
        <dl className="space-y-2 text-sm">
          {Object.entries(p.peas).map(([k, items]) => (
            <div key={k}>
              <dt className="font-semibold text-accent">{k}</dt>
              <dd className="text-dim">{items.join(" · ")}</dd>
            </div>
          ))}
        </dl>
      </Section>
      <Section title="Environment properties (for this scenario and mode)">
        <table className="w-full text-left text-sm">
          <tbody>
            {p.environment.map((e) => (
              <tr key={e.dimension} className="border-t border-line align-top">
                <th className="w-28 py-2 pr-2 text-xs font-medium text-dim">{e.dimension}</th>
                <td className="py-2">
                  <div className="font-semibold">{e.value}</div>
                  <div className="text-xs text-dim">{e.why}</div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="mt-2 text-xs text-dim">
          Derived from the scenario's parameters: change the fire spread, add sensor noise or switch
          to worst-case fire and these rows change.
        </p>
      </Section>
      <Benchmark />
    </div>
  );
}
