import { expect, it } from "vitest";
import { averageAnswerGrades } from "./grade-summary";
import type { Grade } from "../../lib/types/interview-prep";

it("shows a historical comparison only after multiple graded answers", () => {
  const first={relevance:6,specificity:4,star_structure:8,confidence:6} as Grade;
  const second={relevance:8,specificity:10,star_structure:6,confidence:10} as Grade;
  expect(averageAnswerGrades([])).toBeNull();
  expect(averageAnswerGrades([first])).toBeNull();
  const grades=Object.freeze([first,second]);
  expect(averageAnswerGrades([...grades])).toEqual({relevance:7,specificity:7,star_structure:7,confidence:8});
  expect(first.specificity).toBe(4);
});
