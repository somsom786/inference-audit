"use strict";

const assert = require("node:assert/strict");
const {gpuScenario} = require("../../public/assets/labs.js");
const base = {spend: 10000, share: 100, hourly: 2, workers: 0, util: 80, reserve: 20};
const scenario = (gain, extra = {}) => gpuScenario({...base, gain, ...extra});
const close = (value, expected) => assert.ok(Math.abs(value - expected) < 1e-8, [value, expected]);

for (const [gain, ratio] of [[0, 0], [30, 3 / 13], [50, 1 / 3], [100, 1 / 2]]) {
  const result = scenario(gain);
  close(result.monthly, 10000 * ratio);
  close(result.annual, 120000 * ratio);
  close(result.normalizedCost, 2 * (1 - ratio));
  assert.equal(result.capacity, gain);
  assert.equal(result.workers, null);
}
assert.equal(scenario(100, {share: 0}).monthly, 0);
assert.equal(scenario(25, {workers: 10}).workers, 8);
assert.equal(scenario(30, {workers: 10}).workers, 8);
assert.equal(scenario(0, {workers: 10, util: 100}).workers, 13);
assert.equal(scenario(100, {workers: 1}).workers, 1);
close(scenario(30, {share: 50}).monthly, 15000 / 13);

// Homepage default: $50,000/month, +30% qualified throughput, 100% scalable.
const flagship = gpuScenario({spend: 50000, gain: 30, share: 100, hourly: 2, workers: 0, util: 80, reserve: 20});
close(flagship.monthly, 11538.461538461539);
close(flagship.annual, 138461.53846153847);
assert.equal(flagship.monthly.toFixed(2), "11538.46");
assert.equal(flagship.annual.toFixed(2), "138461.54");
close(flagship.reduction, 100 * 3 / 13);
assert.equal(flagship.reduction.toFixed(1), "23.1");
// Reference table on economics.html: annual conditional savings at $50,000/month, 100% scalable.
for (const [gain, pct, annual] of [[30, "23.1", 138462], [50, "33.3", 200000], [100, "50.0", 300000], [200, "66.7", 400000], [400, "80.0", 480000]]) {
  const row = gpuScenario({spend: 50000, gain, share: 100, hourly: 2, workers: 0, util: 80, reserve: 20});
  assert.equal(row.reduction.toFixed(1), pct);
  assert.equal(Math.round(row.annual), annual);
}
// Scalable share scales savings linearly, and zero share yields zero.
close(gpuScenario({spend: 50000, gain: 30, share: 50, hourly: 2, workers: 0, util: 80, reserve: 20}).annual, 138461.53846153847 / 2);
assert.equal(gpuScenario({spend: 50000, gain: 30, share: 0, hourly: 2, workers: 0, util: 80, reserve: 20}).monthly, 0);
assert.equal(gpuScenario({spend: 50000, gain: 0, share: 100, hourly: 2, workers: 0, util: 80, reserve: 20}).monthly, 0);
console.log("Economics invariants passed for gain, annualization, fixed cost, normalization and worker rounding.");
