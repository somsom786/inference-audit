"use strict";

// Keep published fragments working after the full paper moved to research.html.
const researchSections = new Set([
  "more-tokens-less-useful-work", "abstract", "hypotheses", "hardware-and-serving-contracts",
  "measurement-design", "phase-1-establishing-the-right-baseline", "phase-2-slots-batching-and-queueing",
  "phase-3-transfer-across-models", "phase-3-sustained-load-and-recovery",
  "phase-4-a-fresh-workload-changes-the-answer", "from-the-experiment-to-inference-audit",
  "reproduction-and-limitations", "conclusion",
]);
if (location.pathname.endsWith("/case-study.html") && researchSections.has(location.hash.slice(1))) {
  location.replace("research.html" + location.hash);
}

// All chart values come from the audited public projection.
// The page ships a readable first view while the data loads.
const nav = (group, attribute, draw) => {
  const controls = [...group.querySelectorAll(`button[data-${attribute}]`)];
  const select = (picked) => {
    for (const control of controls) control.setAttribute("aria-pressed", String(control === picked));
    draw(picked.dataset[attribute]);
  };
  for (const control of controls) {
    control.disabled = false;
    control.addEventListener("click", () => select(control));
  }
  select(controls.find((control) => control.getAttribute("aria-pressed") === "true") || controls[0]);
};

const el = (tag, text = "", className = "") => {
  const node = document.createElement(tag);
  node.textContent = text;
  if (className) node.className = className;
  return node;
};

const fixed = (value, digits = 3) => value.toFixed(digits);
const count = new Intl.NumberFormat("en-US").format;
const percent = (value) => fixed(100 * value, 1) + "%";
const rates = {1: "0.80", 2: "1.00", 3: "1.15"};
const range = (values) => [Math.min(...values), Math.max(...values)];
const span = ([lo, hi], render) => render(lo) === render(hi) ? render(hi) : `${render(lo)}–${render(hi)}`;
const groups = (rows) => ["A", "B"].map((arm) => rows.filter((row) => row.stage.startsWith(arm)));
const slotNames = ["2 slots", "4 slots"];

function row(index, readings, max, format, suffix, tooltip, threshold = false) {
  const wrapper = el("div", "", "plot-row");
  const bar = el("div", "", "track");
  const meter = el("meter", "", index === 0 ? "two" : "four");
  meter.min = 0;
  meter.max = max;
  meter.value = readings[1];
  meter.setAttribute("aria-label", `${slotNames[index]}, upper reading`);
  const label = `${span(readings, format)}${suffix}`;
  wrapper.title = tooltip;
  bar.append(meter);
  if (readings[1] > readings[0]) {
    const marker = el("span", "", "low-reading");
    marker.style.left = `${100 * readings[0] / max}%`;
    marker.setAttribute("aria-hidden", "true");
    bar.append(marker);
  }
  if (threshold) bar.append(el("span", "", "target"));
  wrapper.append(el("span", slotNames[index]), bar, el("strong", label));
  return wrapper;
}

function labels(left, right) {
  const line = el("div", "", "plot-meta");
  line.append(el("span", left), el("span", right));
  return line;
}

function axis(unit, middle, end) {
  const wrapper = el("div", "", "plot-axis");
  wrapper.append(el("span", "0"), el("span", middle), el("span", `${end} ${unit}`));
  wrapper.setAttribute("aria-hidden", "true");
  return wrapper;
}

const metrics = {
  ttft_p95: {
    label: "p95 first-token latency", direction: "Lower is better", unit: "s", max: 2, source: "p4-tail",
    note: "Four slots started faster at 1.15 offered transactions/s. The whisker marks the lower launch result.",
  },
  e2e_p95: {
    label: "p95 completion latency", direction: "Lower is better", unit: "s", max: 5, source: "p4-tail",
    note: "At the same load, four slots took longer to finish. The p95 is the time within which 95% of completed transactions finished.",
  },
  output_tps: {
    label: "Output tokens per second", direction: "Higher is better", unit: "tok/s", max: 120, source: "p4-tail",
    note: "Both profiles generated about 104 tokens/s on the same traffic. Switch to Goodput to see how much work was correct and on time.",
  },
  goodput_rps: {
    label: "Correct and on time", direction: "Higher is better", unit: "txn/s", max: 1.2, source: "p4-goodput",
    note: "Two slots delivered more correct, on-time transactions per second. The count includes only offers passing both checks.",
  },
  context: {
    label: "Context positions per slot", direction: "Same total f16 KV allocation", unit: "positions", max: 8192, source: "env",
    note: "The same 16,384 positions were split across more sequences. Each four-slot request had half the room for its prompt and generated answer.",
  },
};

function comparisons(data) {
  const observed = groups(data.phase4.rows.filter((r) => r.window === 3 && r.family === "all"));
  const total = data.transfer.find((item) => item.model === "Qwen3-8B").total_context;
  for (const section of document.querySelectorAll("[data-comparison]")) {
    const plot = section.querySelector("[data-plot]");
    const source = section.querySelector("[data-source]");
    nav(section, "metric", (key) => {
      const m = metrics[key];
      const context = key === "context";
      const readings = context ? [[total / 2, total / 2], [total / 4, total / 4]]
        : observed.map((arm) => range(arm.map((r) => r[key])));
      const format = context ? count : key === "output_tps" ? (value) => fixed(value, 2) : fixed;
      plot.replaceChildren(
        labels(m.label, m.direction),
        ...readings.map((values, index) => row(index, values, m.max, format, context || key === "output_tps" ? "" : ` ${m.unit}`,
          context ? `${count(values[0])} positions per slot; ${count(total)} total`
            : observed[index].map((r) => `${r.stage}: ${fixed(r[key])} ${m.unit} (${r.offered} offered)`).join(" · ")
        )),
        axis(m.unit, count(m.max / 2), count(m.max)),
        el("p", m.note, "chart-note"),
      );
      source.href = `claims.html#${m.source}`;
    });
  }
}

function mix(data) {
  const section = document.querySelector("[data-mix]");
  if (!section) return;
  const panel = section.querySelector("[data-families]");
  const names = {chat: "Chat", coding: "Coding", rag: "Retrieval", agent: "Agent"};
  nav(section, "window", (windowNumber) => {
    const results = data.phase4.rows.filter((r) => r.window === Number(windowNumber));
    const wrapper = el("div", "", "family-rows");
    for (const [family, name] of Object.entries(names)) {
      const cohort = results.filter((r) => r.family === family);
      const card = el("div", "", "family-card");
      card.append(el("h4", name), el("p", `${cohort[0].offered} offers per launch at ${rates[windowNumber]} txn/s`));
      for (const [index, arm] of groups(cohort).entries()) {
        card.append(row(index, range(arm.map((r) => r.share)), 1, percent, "",
          arm.map((r) => `${r.stage}: ${r.on_time}/${r.offered} correct and on time`).join(" · "), true));
      }
      wrapper.append(card);
    }
    panel.replaceChildren(wrapper);
  });
}

function models(data) {
  const section = document.querySelector("[data-models]");
  if (!section) return;
  const panel = section.querySelector("[data-model-plot]");
  nav(section, "model", (index) => {
    const item = data.transfer[index];
    const arms = groups(item.launches);
    const values = [item.two_slots_median, item.four_slots_median];
    const rate = fixed(item.launches[0].offered_rps);
    const context = [count(item.total_context / 2), count(item.total_context / 4)];
    const qualified = arms[1].every((r) => (r.on_time / r.offered) >= .95);
    panel.replaceChildren(
      el("div", `${item.delta_pct > 0 ? "+" : ""}${fixed(item.delta_pct, 1)}%`, "model-delta"),
      labels("Median output throughput", `${rate} offered txn/s`),
      ...values.map((value, i) => row(i, [value, value], 150, (x) => fixed(x, 2), "",
        arms[i].map((r) => `${r.stage}: ${fixed(r.output_tps, 2)} tok/s (${r.offered} offered)`).join(" · ")
      )),
      axis("tok/s", "75", "150"),
      el("p", `${arms[0].length} control and ${arms[1].length} candidate launches. ${item.launches[0].offered} offers per launch. Context fell from ${context[0]} to ${context[1]} positions per slot.`, "chart-note"),
      el("p", qualified ? "Four slots met the aggregate 95% deadline threshold in these windows." : "Four slots fell short of the aggregate 95% deadline threshold in these windows.", "chart-note"),
    );
  });
}

for (const list of document.querySelectorAll("[data-panel-list]")) {
  const group = list.parentElement;
  nav(group, "show", (id) => {
    for (const panel of list.children) panel.hidden = panel.id !== id;
  });
}
const demos = document.querySelectorAll("[data-audit-demo]");
if (demos.length) {
  fetch("reports/qwen3-8b-audit.json").then((response) => {
    if (!response.ok) throw new Error("Archived audit unavailable");
    return response.json();
  }).then((audit) => {
    const stages = new Map(audit.stages.map((stage) => [stage.name, stage]));
    for (const demo of demos) {
      const result = demo.querySelector("[data-replay-result]");
      nav(demo, "replay", (name) => {
        const stage = stages.get(name);
        const { on_time, offered } = stage.metrics;
        const agent = stage.families.agent;
        const score = el("div", "", "demo-score");
        score.append(el("strong", `${on_time} / ${offered}`), el("span", "correct and on time"));
        const note = el("div", "", "demo-reading");
        note.append(
          el("span", stage.strict_qualifies ? "Met the audit’s strict target" : "Below the audit’s strict target"),
          el("p", `Agent tasks passed ${agent.on_time} of ${agent.offered} offers. p95 completion was ${fixed(stage.metrics.latency_s.p95, 2)} s.`),
        );
        result.replaceChildren(score, note);
      });
    }
  }).catch(() => {
    for (const demo of demos) demo.querySelector(".demo-link").textContent = "See the archived audit results";
  });
}
if (document.querySelector("[data-comparison], [data-mix], [data-models]")) {
  fetch("evidence/measurements.json")
    .then((response) => {
      if (!response.ok) throw new Error("Measurement data unavailable");
      return response.json();
    }).then((data) => {
      if (data.schema !== 1) throw new Error("Unsupported measurement data");
      comparisons(data);
      mix(data);
      models(data);
    }).catch(() => {
      for (const group of document.querySelectorAll("[data-comparison], [data-mix], [data-models]")) {
        group.append(el("p", "Interactive data is unavailable. See the full research for the measured results.", "data-placeholder"));
      }
    });
}
