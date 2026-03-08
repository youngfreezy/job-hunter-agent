export interface Question {
  id: string;
  category: string;
  question: string;
  source: string;
}

export interface Grade {
  question_id: string;
  relevance: number;
  specificity: number;
  star_structure: number;
  confidence: number;
  overall: number;
  feedback: string;
  strong_answer_example: string;
}

export interface CompanyBrief {
  mission: string;
  culture: string;
  recent_news: string;
  glassdoor_rating: number | null;
  things_to_mention: string[];
  interview_tips: string[];
}

export interface InterviewReport {
  overall_readiness: number;
  category_scores?: Record<string, number>;
  focus_areas?: string[];
}

export interface CoachingHints {
  resume_highlights: string[];
  star_scaffold: {
    situation: string;
    task: string;
    action: string;
    result: string;
  };
  key_points: string[];
  pitfalls: string[];
}
