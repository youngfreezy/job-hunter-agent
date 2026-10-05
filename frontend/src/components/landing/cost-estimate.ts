/** Illustrative comparison displayed by the landing-page calculator. */
export function estimateSearchCost(appsPerWeek: number, hoursPerApp: number, hourlyRate: number) {
  const weeklyHoursSaved = appsPerWeek * hoursPerApp;
  const weeklyCostManual = weeklyHoursSaved * hourlyRate;
  const creditCost = appsPerWeek <= 10 ? 24.99 : appsPerWeek <= 50 ? 99.99 : 149.99;
  const savings = weeklyCostManual - creditCost;
  const roi = Math.round((savings / creditCost) * 100);
  return { weeklyHoursSaved, weeklyCostManual, creditCost, savings, roi };
}
