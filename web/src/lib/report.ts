/** Run report export: the engine's report as JSON, plus a printable HTML page built from it.
 * Formatting only; every value comes from GET /simulation/report. */

import type { Report } from "../api/client";

const esc = (s: unknown) =>
  String(s).replace(
    /[&<>"]/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c] ?? c,
  );

const fmt = (n: number) => (Number.isInteger(n) ? String(n) : n.toFixed(2));

export function reportHtml(r: Report): string {
  const m = r.metrics;
  const rescued = r.people.filter((p) => p.status === "EVACUATED").length;
  const rows = (pairs: [string, string | number][]) =>
    pairs.map(([k, v]) => `<tr><th>${esc(k)}</th><td>${esc(v)}</td></tr>`).join("");
  return `<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>ResQ-AI run report: ${esc(r.scenario.name)}</title>
<style>
body{font:14px/1.5 system-ui,sans-serif;max-width:820px;margin:32px auto;padding:0 16px;color:#111}
h1{font-size:22px;margin:0 0 4px}h2{font-size:16px;margin:24px 0 8px;border-bottom:1px solid #ccc}
table{border-collapse:collapse;width:100%}th,td{text-align:left;padding:4px 8px;border-bottom:1px solid #eee;vertical-align:top}
th{width:34%;font-weight:600}code,pre{font:12px ui-monospace,monospace}pre{background:#f5f5f5;padding:8px;line-height:1.1}
.muted{color:#666}.ok{color:#0a7a2f}.bad{color:#b00020}
</style></head><body>
<h1>ResQ-AI run report: ${esc(r.scenario.name)}</h1>
<p class="muted">Scenario <code>${esc(r.scenario_id)}</code>, seed ${r.seed}, fire mode ${esc(r.fire_mode)}.
Every figure below was produced by the engine (GET /simulation/report).</p>
<h2>Outcome</h2><table>${rows([
    ["Status", `${r.status}${r.finished ? " (finished)" : " (still running)"}`],
    ["People rescued", `${rescued} / ${r.people.length}`],
    ["Ticks", r.ticks],
    [
      "Replay check",
      r.replay_identical
        ? "identical: every tick rebuilt from scenario + seed + event log"
        : "MISMATCH",
    ],
  ])}</table>
<table>${r.people.map((p) => `<tr><th>${esc(p.id)}</th><td class="${p.status === "EVACUATED" ? "ok" : "bad"}">${esc(p.status)} at (${p.pos.join(", ")})</td></tr>`).join("")}</table>
<h2>Measured metrics</h2><table>${rows([
    ["Moves", m.moves],
    ["Path cost paid", fmt(m.path_cost)],
    ["Plans adopted / replans", `${m.plans} / ${m.replans}`],
    ["A* searches", m.searches],
    ["Cells expanded by A*", m.nodes_expanded],
    ["Planning states expanded", m.plan_nodes_expanded],
    [
      "Knowledge base (last tick)",
      `${m.kb_base} base facts, ${m.kb_derived} derived, ${m.kb_iterations} passes`,
    ],
  ])}</table>
<h2>Replans and why</h2>${
    r.replans.length === 0
      ? "<p>None.</p>"
      : `<table>${r.replans.map((x) => `<tr><th>tick ${x.tick} · ${esc(x.kind)}</th><td>${esc(x.reason)}</td></tr>`).join("")}</table>`
  }
<h2>User events</h2>${
    r.user_events.length === 0
      ? "<p>None.</p>"
      : `<table>${r.user_events.map((e) => `<tr><th>tick ${e.tick}</th><td>${esc(e.type)} <code>${esc(JSON.stringify(e.args))}</code></td></tr>`).join("")}</table>`
  }
<h2>Trace highlights</h2><table>${r.highlights
    .map(
      (h) =>
        `<tr><th>tick ${h.tick} · ${esc(h.kind)}</th><td>${esc(h.text)}${h.reason ? `<br><span class="muted">${esc(h.reason)}</span>` : ""}</td></tr>`,
    )
    .join("")}</table>
<h2>Scenario</h2><pre>${esc(r.scenario.terrain.join("\n"))}</pre>
<p class="muted">Simulation values only. This is a teaching simulator, not a triage system (see docs/ETHICS.md).</p>
</body></html>`;
}

function download(name: string, type: string, text: string) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([text], { type }));
  a.download = name;
  a.click();
  URL.revokeObjectURL(a.href);
}

export function saveReport(r: Report) {
  const base = `resq-report-${r.scenario_id}-t${r.ticks}`;
  download(`${base}.json`, "application/json", JSON.stringify(r, null, 2));
  download(`${base}.html`, "text/html", reportHtml(r));
}
