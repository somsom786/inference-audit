"use strict";

function gpuScenario({spend, gain, share, hourly, workers, util, reserve}) {
  const speed = 1 + gain / 100;
  const monthly = spend * (share / 100) * (1 - 1 / speed);
  return {
    capacity: gain,
    reduction: 100 * (1 - 1 / speed),
    monthly,
    annual: monthly * 12,
    normalizedCost: hourly / speed,
    workers: workers ? Math.max(1, Math.ceil(workers * util / 100 / speed / (1 - reserve / 100) - 1e-12)) : null,
  };
}

if (typeof module !== "undefined") module.exports = {gpuScenario};

if (typeof document !== "undefined") {
  const form = document.querySelector("#economics-model");
  const finance = document.querySelector("#estimate");
  const usd = new Intl.NumberFormat("en-US", {style: "currency", currency: "USD"});
  function update() {
    if (!form.checkValidity()) {
      finance.textContent = "Enter numbers within the stated limits to calculate an estimate.";
      return;
    }
    const values = Object.fromEntries([...new FormData(form)].map(([key, value]) => [key, Number(value)]));
    const result = gpuScenario(values);
    const lines = [
      ["Extra qualified capacity", "+" + result.capacity + "% at the same capacity baseline"],
      ["Fewer GPU-hours for the same useful work", result.reduction.toFixed(1) + "%"],
      ["Conditional savings per month", usd.format(result.monthly)],
      ["Conditional savings per year", usd.format(result.annual)],
      ["Hourly cost for one baseline GPU-hour of useful output", usd.format(result.normalizedCost)],
    ];
    if (result.workers !== null) lines.push(["Illustrative GPUs required at peak", String(result.workers) + " under the selected reserve"]);
    finance.replaceChildren(...lines.map(([label, value]) => {
      const row = document.createElement("p");
      const amount = document.createElement("strong");
      amount.textContent = value;
      row.append(amount, label);
      return row;
    }));
  }
  form.addEventListener("input", update);
  form.addEventListener("submit", event => event.preventDefault());
  update();

  const scales = {
    goodput: {title: "Correct answers on time", field: "on_time", max: 345, unit: " of 345"},
    first: {title: "Time to first token (p95)", field: "ttft_p95", max: 2, unit: " s"},
    complete: {title: "Completion latency (p95)", field: "completion_p95", max: 5, unit: " s"},
  };
  const controls = document.querySelector("#metric-controls");
  const chart = document.querySelector("#tradeoff");
  const title = document.querySelector("#metric-title");

  fetch("evidence/labs-results.json")
    .then(response => {
      if (!response.ok) throw new Error("Study data unavailable");
      return response.json();
    })
    .then(data => {
      function draw(key) {
        const metric = scales[key];
        title.textContent = metric.title;
        chart.replaceChildren(...[[2, "A1", "A2"], [4, "B1", "B2"]].map(([slots, a, b]) => {
          const values = [data.mixed[a][metric.field], data.mixed[b][metric.field]];
          const [low, high] = values.sort((x, y) => x - y);
          const row = document.createElement("div");
          row.className = "bar-row";
          const label = document.createElement("b");
          label.textContent = slots + " slots";
          const track = document.createElement("span");
          track.className = "bar-track";
          track.setAttribute("aria-hidden", "true");
          const bar = document.createElement("i");
          bar.style.width = Math.min(100, 100 * high / metric.max) + "%";
          track.append(bar);
          const range = document.createElement("span");
          range.textContent = (low === high ? low : low + "–" + high) + metric.unit;
          row.append(label, track, range);
          return row;
        }));
        controls.querySelectorAll("button").forEach(button => {
          button.setAttribute("aria-pressed", String(button.dataset.metric === key));
        });
      }
      controls.addEventListener("click", event => {
        if (event.target instanceof HTMLButtonElement) draw(event.target.dataset.metric);
      });
      draw("goodput");
      controls.hidden = false;
    })
    .catch(() => {
      // The HTML retains the source-linked goodput result without JavaScript.
    });
}
