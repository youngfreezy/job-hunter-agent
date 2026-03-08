# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""LLM-as-judge evaluation functions for each pipeline agent."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, Dict, List, Optional

from scipy.stats import spearmanr

from backend.eval.models import EvalMetric
from backend.shared.llm import build_llm, default_model, invoke_with_retry

logger = logging.getLogger(__name__)


async def _judge(prompt: str, agent: str, metric_name: str) -> EvalMetric:
    """Run an LLM judge prompt and parse the JSON response."""
    llm = build_llm(model=default_model(), max_tokens=2048, temperature=0.0)
    response = await invoke_with_retry(llm, [
        {"role": "system", "content": (
            "You are an evaluation judge. Analyze the provided data and return "
            "a JSON object with exactly two keys: "
            '"score" (float 0.0-1.0) and "reasoning" (string, 2-3 sentences). '
            "Nothing else."
        )},
        {"role": "user", "content": prompt},
    ])
    text = response.content if hasattr(response, "content") else str(response)
    if not text or not text.strip():
        logger.warning("Empty LLM response for %s, checking additional_kwargs", metric_name)
        # Some models return structured output differently
        if hasattr(response, "additional_kwargs"):
            text = json.dumps(response.additional_kwargs)

    # Strip markdown code fences if present
    if "```" in text:
        text = re.sub(r"```(?:json)?\s*", "", text).strip()

    # Parse JSON from response
    try:
        # Try full text first, then extract JSON block
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            # Find JSON by matching balanced braces
            start = text.find("{")
            if start >= 0:
                depth = 0
                end = start
                for i, c in enumerate(text[start:], start):
                    if c == "{":
                        depth += 1
                    elif c == "}":
                        depth -= 1
                        if depth == 0:
                            end = i + 1
                            break
                data = json.loads(text[start:end])
            else:
                raise
    except (json.JSONDecodeError, AttributeError):
        logger.warning("Failed to parse judge response for %s: %s", metric_name, text[:200])
        data = {"score": 0.0, "reasoning": f"Parse error: {text[:200]}"}

    score = max(0.0, min(1.0, float(data.get("score", 0.0))))
    return EvalMetric(
        name=metric_name,
        score=score,
        reasoning=data.get("reasoning", ""),
        agent=agent,
    )


# ---------------------------------------------------------------------------
# Coach judges
# ---------------------------------------------------------------------------

async def judge_coach_faithfulness(
    original_resume: str, rewritten_resume: str
) -> EvalMetric:
    """Check if the rewritten resume contains hallucinated experience."""
    prompt = f"""Compare the ORIGINAL resume with the REWRITTEN resume.
Identify any claims in the REWRITTEN version that are NOT supported by the ORIGINAL
(hallucinated jobs, degrees, skills, companies, or metrics).

Score 1.0 if fully faithful (no hallucinations), 0.0 if heavily hallucinated.

ORIGINAL RESUME:
{original_resume[:2000]}

REWRITTEN RESUME:
{rewritten_resume[:2000]}"""
    return await _judge(prompt, "coach", "coach_faithfulness")


def judge_coach_improvement(
    resume_score: Dict[str, Any]
) -> EvalMetric:
    """Evaluate resume quality based on the coach's own scoring dimensions."""
    dimensions = ["keyword_density", "impact_metrics", "ats_compatibility", "readability", "formatting"]
    scores = [resume_score.get(d, 0) for d in dimensions]
    avg = sum(scores) / len(scores) / 100.0 if scores else 0.0

    return EvalMetric(
        name="coach_improvement",
        score=avg,
        reasoning=(
            f"Average across {len(dimensions)} dimensions: {avg:.2f}. "
            f"Scores: {', '.join(f'{d}={resume_score.get(d, 0)}' for d in dimensions)}."
        ),
        agent="coach",
    )


# ---------------------------------------------------------------------------
# Discovery judges
# ---------------------------------------------------------------------------

async def judge_discovery_relevance(
    keywords: List[str], discovered_jobs: List[Dict[str, Any]]
) -> EvalMetric:
    """Evaluate what % of discovered jobs match the search keywords."""
    if not discovered_jobs:
        return EvalMetric(
            name="discovery_relevance",
            score=0.0,
            reasoning="No jobs discovered.",
            agent="discovery",
        )

    # Sample up to 20 jobs for LLM evaluation
    sample = discovered_jobs[:20]
    jobs_text = "\n".join(
        f"- {j.get('title', '?')} at {j.get('company', '?')}: {(j.get('description_snippet') or '')[:100]}"
        for j in sample
    )

    prompt = f"""Given search keywords: {', '.join(keywords)}

Evaluate what fraction of these discovered jobs are RELEVANT to those keywords.
A job is relevant if the title or description reasonably matches the search intent.

DISCOVERED JOBS ({len(sample)} of {len(discovered_jobs)} total):
{jobs_text}

Score 1.0 if all are relevant, 0.0 if none are."""
    return await _judge(prompt, "discovery", "discovery_relevance")


def compute_discovery_coverage(discovered_jobs: List[Dict[str, Any]]) -> EvalMetric:
    """Evaluate board diversity — how many distinct boards returned results."""
    boards = set()
    for j in discovered_jobs:
        board = j.get("board")
        if isinstance(board, str):
            boards.add(board)
        elif hasattr(board, "value"):
            boards.add(board.value)

    total_boards = 4  # linkedin, indeed, glassdoor, ziprecruiter
    score = min(1.0, len(boards) / total_boards)

    return EvalMetric(
        name="discovery_coverage",
        score=score,
        reasoning=f"Found jobs from {len(boards)}/{total_boards} boards: {', '.join(sorted(boards))}.",
        agent="discovery",
    )


# ---------------------------------------------------------------------------
# Scoring judges
# ---------------------------------------------------------------------------

async def judge_scoring_calibration(
    scored_jobs: List[Dict[str, Any]], keywords: List[str]
) -> EvalMetric:
    """Re-score a sample of jobs and compare rank correlation."""
    if len(scored_jobs) < 3:
        return EvalMetric(
            name="scoring_calibration",
            score=0.5,
            reasoning=f"Only {len(scored_jobs)} scored jobs, insufficient for calibration.",
            agent="scoring",
        )

    # Sample 5 jobs evenly across the score range
    sorted_jobs = sorted(scored_jobs, key=lambda j: j.get("score", 0), reverse=True)
    indices = [0, len(sorted_jobs) // 4, len(sorted_jobs) // 2, 3 * len(sorted_jobs) // 4, -1]
    sample = []
    seen = set()
    for i in indices:
        idx = i if i >= 0 else len(sorted_jobs) + i
        if 0 <= idx < len(sorted_jobs) and idx not in seen:
            seen.add(idx)
            sample.append(sorted_jobs[idx])
    sample = sample[:5]

    jobs_text = "\n".join(
        f"{i+1}. {j.get('job', {}).get('title', '?')} at {j.get('job', {}).get('company', '?')} "
        f"(pipeline score: {j.get('score', 0)})"
        for i, j in enumerate(sample)
    )

    prompt = f"""You are evaluating job-candidate fit. The candidate's keywords are: {', '.join(keywords)}

Re-score each job 0-100 based on how well it matches these keywords.
Return a JSON object: {{"score": <float 0-1>, "reasoning": "<explanation>", "rescores": [<score1>, <score2>, ...]}}

JOBS TO EVALUATE:
{jobs_text}"""

    llm = build_llm(model=default_model(), max_tokens=2048, temperature=0.0)
    response = await invoke_with_retry(llm, [
        {"role": "system", "content": "Return only valid JSON."},
        {"role": "user", "content": prompt},
    ])
    text = response.content if hasattr(response, "content") else str(response)
    if not text or not text.strip():
        if hasattr(response, "additional_kwargs"):
            text = json.dumps(response.additional_kwargs)
    if "```" in text:
        text = re.sub(r"```(?:json)?\s*", "", text).strip()

    try:
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            if start >= 0:
                depth = 0
                end = start
                for i, c in enumerate(text[start:], start):
                    if c == "{":
                        depth += 1
                    elif c == "}":
                        depth -= 1
                        if depth == 0:
                            end = i + 1
                            break
                data = json.loads(text[start:end])
            else:
                raise
        rescores = data.get("rescores", [])

        if len(rescores) == len(sample):
            pipeline_scores = [j.get("score", 0) for j in sample]
            corr, _ = spearmanr(pipeline_scores, rescores)
            # Convert correlation (-1 to 1) to score (0 to 1)
            score = max(0.0, min(1.0, (corr + 1) / 2))
        else:
            score = float(data.get("score", 0.5))

        return EvalMetric(
            name="scoring_calibration",
            score=score,
            reasoning=data.get("reasoning", f"Spearman correlation: {score:.2f}"),
            agent="scoring",
        )
    except Exception as e:
        logger.warning("Scoring calibration parse error: %s", e)
        return EvalMetric(
            name="scoring_calibration",
            score=0.5,
            reasoning=f"Parse error during calibration: {e}",
            agent="scoring",
        )


# ---------------------------------------------------------------------------
# Tailor judges
# ---------------------------------------------------------------------------

async def judge_tailor_customization(
    job: Dict[str, Any], tailored_resume: Dict[str, Any]
) -> EvalMetric:
    """Check if the tailored resume addresses specific job requirements."""
    job_info = job.get("job", job)
    prompt = f"""Evaluate whether this TAILORED RESUME addresses the specific requirements
of the TARGET JOB. Score 1.0 if highly customized, 0.0 if generic.

TARGET JOB:
Title: {job_info.get('title', '?')}
Company: {job_info.get('company', '?')}
Description: {(job_info.get('description_snippet') or '')[:500]}

CHANGES MADE: {', '.join(tailored_resume.get('changes_made', []))}

TAILORED RESUME (excerpt):
{tailored_resume.get('tailored_text', '')[:2000]}"""
    return await _judge(prompt, "tailor", "tailor_customization")


async def judge_tailor_faithfulness(
    original_resume: str, tailored_resume: Dict[str, Any]
) -> EvalMetric:
    """Check if tailored resume hallucinated skills/experience."""
    prompt = f"""Compare the ORIGINAL resume with the TAILORED version.
Identify any claims in the TAILORED version not supported by the ORIGINAL
(hallucinated skills, experience, certifications, or metrics).

Score 1.0 if fully faithful, 0.0 if heavily hallucinated.

ORIGINAL RESUME:
{original_resume[:2000]}

TAILORED RESUME:
{tailored_resume.get('tailored_text', '')[:2000]}"""
    return await _judge(prompt, "tailor", "tailor_faithfulness")


# ---------------------------------------------------------------------------
# E2E metrics (pure computation, no LLM)
# ---------------------------------------------------------------------------

def compute_e2e_metrics(state: Dict[str, Any]) -> List[EvalMetric]:
    """Compute end-to-end pipeline metrics from session state."""
    metrics = []

    discovered = len(state.get("discovered_jobs") or [])
    scored = len(state.get("scored_jobs") or [])
    submitted = len(state.get("applications_submitted") or [])
    failed = len(state.get("applications_failed") or [])
    skipped = len(state.get("applications_skipped") or [])
    total_attempted = submitted + failed

    # Submission success rate
    if total_attempted > 0:
        success_rate = submitted / total_attempted
        metrics.append(EvalMetric(
            name="submission_success_rate",
            score=success_rate,
            reasoning=f"{submitted}/{total_attempted} applications succeeded ({success_rate:.0%}).",
            agent="e2e",
        ))
    else:
        metrics.append(EvalMetric(
            name="submission_success_rate",
            score=0.0,
            reasoning="No applications attempted.",
            agent="e2e",
        ))

    # Pipeline throughput (discovered -> submitted)
    if discovered > 0:
        throughput = submitted / discovered
        metrics.append(EvalMetric(
            name="pipeline_throughput",
            score=min(1.0, throughput * 5),  # 20% throughput = 1.0
            reasoning=f"{submitted}/{discovered} discovered jobs resulted in submissions ({throughput:.0%}).",
            agent="e2e",
        ))

    # Scoring funnel (what % of discovered jobs got scored)
    if discovered > 0:
        scoring_rate = min(1.0, scored / discovered)
        metrics.append(EvalMetric(
            name="scoring_coverage",
            score=scoring_rate,
            reasoning=f"{scored}/{discovered} jobs scored ({scoring_rate:.0%}).",
            agent="e2e",
        ))

    return metrics


# ---------------------------------------------------------------------------
# Run all judges for a session
# ---------------------------------------------------------------------------

async def evaluate_session(state: Dict[str, Any]) -> List[EvalMetric]:
    """Run all applicable judges on a session's state."""
    metrics: List[EvalMetric] = []

    resume_text = state.get("resume_text") or ""
    keywords = state.get("keywords") or []

    # --- Coach ---
    coach_output = state.get("coach_output")
    if coach_output:
        co = coach_output if isinstance(coach_output, dict) else coach_output.dict()
        rewritten = co.get("rewritten_resume", "")
        if resume_text and rewritten:
            m = await judge_coach_faithfulness(resume_text, rewritten)
            metrics.append(m)

        resume_score = co.get("resume_score", {})
        if isinstance(resume_score, dict):
            metrics.append(judge_coach_improvement(resume_score))
        elif hasattr(resume_score, "dict"):
            metrics.append(judge_coach_improvement(resume_score.dict()))

    # --- Discovery ---
    discovered = state.get("discovered_jobs") or []
    discovered_dicts = [
        j if isinstance(j, dict) else j.dict() for j in discovered
    ]
    if discovered_dicts and keywords:
        m = await judge_discovery_relevance(keywords, discovered_dicts)
        metrics.append(m)
    metrics.append(compute_discovery_coverage(discovered_dicts))

    # --- Scoring ---
    scored = state.get("scored_jobs") or []
    scored_dicts = [j if isinstance(j, dict) else j.dict() for j in scored]
    if scored_dicts and keywords:
        m = await judge_scoring_calibration(scored_dicts, keywords)
        metrics.append(m)

    # --- Tailor ---
    tailored = state.get("tailored_resumes") or {}
    if isinstance(tailored, dict) and tailored:
        # Evaluate a sample (first 3 tailored resumes)
        customization_tasks = []
        faithfulness_tasks = []

        items = list(tailored.items())[:3]
        for job_id, tr in items:
            tr_dict = tr if isinstance(tr, dict) else tr.dict()

            # Find the corresponding scored job
            matching_job = next(
                (sj for sj in scored_dicts
                 if (sj.get("job", {}).get("id") or sj.get("id")) == job_id),
                None,
            )
            if matching_job:
                customization_tasks.append(
                    judge_tailor_customization(matching_job, tr_dict)
                )
            if resume_text:
                faithfulness_tasks.append(
                    judge_tailor_faithfulness(resume_text, tr_dict)
                )

        # Run tailor judges concurrently
        results = await asyncio.gather(
            *customization_tasks, *faithfulness_tasks,
            return_exceptions=True,
        )
        for r in results:
            if isinstance(r, EvalMetric):
                metrics.append(r)
            elif isinstance(r, Exception):
                logger.warning("Tailor judge failed: %s", r)

    # --- E2E ---
    metrics.extend(compute_e2e_metrics(state))

    return metrics
