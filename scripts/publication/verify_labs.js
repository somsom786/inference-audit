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
console.log("Economics invariants passed for gain, annualization, fixed cost, normalization and worker rounding.");
