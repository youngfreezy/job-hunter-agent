// Copyright (c) 2026 V2 Software LLC. All rights reserved.

export interface TaskBreakdown {
  task: string;
  risk_pct: number;
  onet_activity_id?: string;
}

export interface LearningResource {
  name: string;
  hours: number;
  cost: string;
}

export interface LearningWeek {
  week: string | number;
  topic: string;
  resources?: LearningResource[];
}

export interface SkillComparison {
  categories: string[];
  user_scores: number[];
  target_scores: number[];
}

export interface PivotRole {
  role: string;
  soc_code?: string;
  skill_overlap_pct: number;
  salary_range: { min: number; max: number; median: number };
  market_demand: number;
  growth_rate?: string;
  entry_education?: string;
  ai_risk_pct: number;
  missing_skills: string[];
  skill_comparison?: SkillComparison;
  learning_plan: LearningWeek[];
  time_to_pivot_weeks: number;
}

export interface RiskAssessment {
  automation_risk_score: number;
  task_breakdown: TaskBreakdown[];
  resistant_abilities?: string[];
  parsed_role: string;
  parsed_skills: string[];
  years_experience: number;
  industry: string;
  soc_code?: string;
}

export interface SkillBridgeTarget {
  industry: string;
  role: string;
  why: string;
  salary_range: { min: number; max: number; median: number };
  demand: string;
  growth_rate: string;
  collar: string;
  ai_resistant: boolean;
}

export interface SkillBridge {
  your_skill: string;
  skill_category: string;
  transfers_to: SkillBridgeTarget[];
}
