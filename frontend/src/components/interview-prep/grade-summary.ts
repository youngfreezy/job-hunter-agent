import type { Grade } from "../../lib/types/interview-prep";

export function averageAnswerGrades(grades: Grade[]) {
  if (grades.length <= 1) return null;
  return {
    relevance: grades.reduce((sum, grade) => sum + grade.relevance, 0) / grades.length,
    specificity: grades.reduce((sum, grade) => sum + grade.specificity, 0) / grades.length,
    star_structure: grades.reduce((sum, grade) => sum + grade.star_structure, 0) / grades.length,
    confidence: grades.reduce((sum, grade) => sum + grade.confidence, 0) / grades.length,
  };
}
