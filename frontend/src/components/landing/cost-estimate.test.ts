import { expect, it } from "vitest";
import { estimateSearchCost } from "./cost-estimate";

it("retains the calculator's pack boundaries and fractional time input", () => {
  for (const [apps, expected] of [[10,24.99],[11,99.99],[50,99.99],[51,149.99]]) {
    expect(estimateSearchCost(apps,0.25,15).creditCost).toBe(expected);
  }
  expect(estimateSearchCost(20,0.5,50)).toEqual({weeklyHoursSaved:10,weeklyCostManual:500,creditCost:99.99,savings:400.01,roi:400});
});

it("retains negative estimates so presentation can show a neutral comparison", () => {
  const estimate=estimateSearchCost(11,0.25,15);
  expect(estimate.savings).toBeLessThan(0);
  expect(estimate.roi).toBeLessThan(0);
});
