// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

import AnswerGradeRadar from "@/components/charts/AnswerGradeRadar";
import type {
  Grade
} from "@/lib/types/interview-prep";

import { averageAnswerGrades } from "./grade-summary";

type Props = {
  lastGrade: Grade | null;
  grades: Grade[];
};

export function InterviewAnswerGrade({ lastGrade, grades }: Props) {
  return <>
    {/* Last Grade */}
    {lastGrade && (
      <div className="bg-card border rounded-lg p-6 space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="font-medium">Score: {lastGrade.overall}/10</h3>
          <div className="w-32 bg-muted rounded-full h-2">
            <div
              className="bg-primary h-2 rounded-full"
              style={{ width: `${lastGrade.overall * 10}%` }}
            />
          </div>
        </div>
        <AnswerGradeRadar
          grade={lastGrade}
          averageGrades={averageAnswerGrades(grades)}
        />
        <p className="text-sm text-muted-foreground">{lastGrade.feedback}</p>
        {lastGrade.strong_answer_example && (
          <details className="text-sm">
            <summary className="cursor-pointer text-primary">View strong answer example</summary>
            <p className="mt-2 text-muted-foreground">{lastGrade.strong_answer_example}</p>
          </details>
        )}
      </div>
    )}

  </>;
}
