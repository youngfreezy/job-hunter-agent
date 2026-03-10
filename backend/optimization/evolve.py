# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""EvoAgentX-powered prompt optimization using TextGrad.

Loads session outcomes from Postgres, wraps our discovery/scoring prompts
as EvoAgentX workflows, and runs TextGrad to iteratively improve them.
Optimized prompts are saved to the prompt_registry table.

Can be triggered:
  - Automatically after every N sessions (via reporting agent)
  - Manually: python -m backend.optimization.evolve
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# Prompt keys that map to our agent prompts
PROMPT_KEY_DISCOVERY = "discovery_search_query"
PROMPT_KEY_PARSE = "discovery_parse_results"
PROMPT_KEY_SCORING = "scoring_system"

# Default prompts (copied from the agents -- used as initial seeds)
_DEFAULT_DISCOVERY_PROMPT = """\
You are a job search expert. Generate {num_queries} Google search queries to find \
job listings on ATS platforms (NOT on LinkedIn, Indeed, or Glassdoor).

Target these ATS sites specifically:
- boards.greenhouse.io
- jobs.lever.co
- jobs.ashbyhq.com
- myworkdayjobs.com
- jobs.smartrecruiters.com

Job criteria:
- Keywords: {keywords}
- Remote only: {remote_only}
- Location: {location}

Generate diverse queries using site: operators and keyword variations. \
Each query should target a different ATS platform or keyword combination. \
Focus on finding CURRENT job postings (2026).

Return a JSON array of query strings, nothing else. Example:
["Senior Software Engineer remote site:boards.greenhouse.io", "AI engineer site:jobs.lever.co 2026"]
"""

_DEFAULT_SCORING_PROMPT = """\
You are an expert career-matching engine. Given a candidate's resume and a batch
of job listings, score each job on how well the candidate fits.

For EACH job, produce a score with breakdown and reasons.

Scoring guidelines:
- keyword_match: Count overlapping skills, technologies, and domain keywords.
- location_match: 100 for exact match or remote; 50 for same state; 20 for relocation needed.
- salary_match: 100 if within resume's implied range; 50 if salary not listed; lower if clearly mismatched.
- experience_match: 100 if years of experience align; lower for over/under-qualified.
- overall score should be a weighted average: keyword 40%, experience 30%, location 15%, salary 15%.
- reasons: exactly 2 short bullet points, each under 12 words.
- fit_summary: 2-3 sentences explaining why this candidate is a strong fit for the role, referencing specific skills, experiences, or qualifications from their resume that match the job requirements. Write in second person ("You have...", "Your experience in...").
"""


def _get_api_key() -> str:
    """Get Anthropic API key from settings or env."""
    try:
        from backend.shared.config import get_settings
        key = get_settings().ANTHROPIC_API_KEY
        if key:
            return key
    except Exception:
        pass
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY must be set for prompt optimization")
    return key


def run_optimization(prompt_key: str = PROMPT_KEY_DISCOVERY) -> Dict[str, Any]:
    """Run TextGrad optimization on a specific prompt.

    Returns dict with optimization results including the best prompt
    and its evaluation score.
    """
    try:
        from evoagentx.models import LiteLLMConfig, LiteLLM
        from evoagentx.optimizers import TextGradOptimizer
        from evoagentx.workflow import SequentialWorkFlowGraph
        from evoagentx.prompts import StringTemplate
        from evoagentx.agents import AgentManager
        from evoagentx.evaluators import Evaluator
    except ImportError:
        logger.error("evoagentx not installed. Run: pip install evoagentx")
        return {"error": "evoagentx not installed"}

    from backend.shared.outcome_store import get_outcomes_for_optimization
    from backend.shared.prompt_registry import (
        get_active_prompt,
        save_prompt,
        activate_prompt,
    )

    # Check if we have enough data
    outcomes = get_outcomes_for_optimization(min_sessions=10)
    if not outcomes:
        logger.info("Not enough session outcomes for optimization (need 10+)")
        return {"error": "insufficient_data", "message": "Need at least 10 session outcomes"}

    api_key = _get_api_key()

    # Configure LLMs -- Haiku for execution, Sonnet for optimization
    executor_config = LiteLLMConfig(
        model="anthropic/claude-haiku-4-5-20251001",
        api_key=api_key,
    )
    executor_llm = LiteLLM(config=executor_config)

    optimizer_config = LiteLLMConfig(
        model="anthropic/claude-sonnet-4-20250514",
        api_key=api_key,
    )
    optimizer_llm = LiteLLM(config=optimizer_config)

    # Load current prompt (from registry or default)
    if prompt_key == PROMPT_KEY_DISCOVERY:
        current_prompt = get_active_prompt(PROMPT_KEY_DISCOVERY) or _DEFAULT_DISCOVERY_PROMPT
        goal = "Generate effective job search queries that lead to successful applications on ATS platforms"
        task_name = "search_query_generation"
        task_desc = "Generate Google search queries for ATS job boards"
    elif prompt_key == PROMPT_KEY_SCORING:
        current_prompt = get_active_prompt(PROMPT_KEY_SCORING) or _DEFAULT_SCORING_PROMPT
        goal = "Score job listings against candidate resume to predict application success"
        task_name = "job_scoring"
        task_desc = "Score job-candidate fit with breakdown"
    else:
        return {"error": f"Unknown prompt key: {prompt_key}"}

    # Build EvoAgentX workflow wrapping our prompt
    workflow_data = {
        "goal": goal,
        "tasks": [
            {
                "name": task_name,
                "description": task_desc,
                "inputs": [
                    {"name": "context", "type": "str", "required": True, "description": "Session context and search criteria"}
                ],
                "outputs": [
                    {"name": "result", "type": "str", "required": True, "description": "Generated output"}
                ],
                "prompt_template": StringTemplate(instruction=current_prompt),
                "system_prompt": f"You are optimizing a {task_name} prompt for a job application automation system.",
                "parse_mode": "str",
            }
        ],
    }

    workflow_graph = SequentialWorkFlowGraph.from_dict(workflow_data)

    # Create agent manager
    agent_manager = AgentManager()
    agent_manager.add_agents_from_workflow(workflow_graph, llm_config=executor_config)

    # Build benchmark from session outcomes
    benchmark = _build_benchmark(outcomes)

    # Create evaluator
    def collate_func(example: dict) -> dict:
        return {"context": _format_outcome_as_context(example)}

    evaluator = Evaluator(
        llm=executor_llm,
        agent_manager=agent_manager,
        collate_func=collate_func,
        num_workers=3,
        verbose=False,
    )

    # Run TextGrad optimization
    logger.info("Starting TextGrad optimization for '%s' with %d outcomes", prompt_key, len(outcomes))

    optimizer = TextGradOptimizer(
        graph=workflow_graph,
        optimize_mode="instruction",
        executor_llm=executor_llm,
        optimizer_llm=optimizer_llm,
        batch_size=3,
        max_steps=10,
        evaluator=evaluator,
        eval_every_n_steps=2,
        eval_rounds=1,
        rollback=True,
        save_path=None,
    )

    try:
        optimizer.optimize(dataset=benchmark, seed=42)
        optimizer.restore_best_graph()
    except Exception as exc:
        logger.error("TextGrad optimization failed: %s", exc, exc_info=True)
        return {"error": str(exc)}

    # Extract optimized prompt
    optimized_prompt = workflow_graph.tasks[0].prompt_template.instruction

    # Evaluate improvement
    eval_result = {}
    try:
        eval_result = optimizer.evaluate(dataset=benchmark, eval_mode="test")
    except Exception:
        logger.warning("Post-optimization evaluation failed", exc_info=True)

    score = eval_result.get("accuracy", 0.0) if eval_result else 0.0

    # Save to registry
    version = save_prompt(
        prompt_key,
        optimized_prompt,
        score=score,
        metadata={
            "optimization_method": "textgrad",
            "num_outcomes": len(outcomes),
            "eval_result": eval_result,
            "max_steps": 10,
        },
    )
    activate_prompt(prompt_key, version)

    logger.info(
        "Optimization complete for '%s': v%d activated (score=%.2f)",
        prompt_key, version, score,
    )

    return {
        "prompt_key": prompt_key,
        "version": version,
        "score": score,
        "eval_result": eval_result,
        "prompt_preview": optimized_prompt[:200] + "..." if len(optimized_prompt) > 200 else optimized_prompt,
    }


def _build_benchmark(outcomes: List[Dict[str, Any]]):
    """Build an EvoAgentX Benchmark from session outcomes."""
    from evoagentx.benchmark import Benchmark

    class SessionOutcomeBenchmark(Benchmark):
        def __init__(self, data: List[Dict[str, Any]]):
            self._raw_data = data
            super().__init__()

        def _load_data(self):
            n = len(self._raw_data)
            split1 = int(n * 0.6)
            split2 = int(n * 0.8)
            self._train_data = self._raw_data[:split1]
            self._dev_data = self._raw_data[split1:split2]
            self._test_data = self._raw_data[split2:]

        def _get_id(self, example: dict) -> str:
            return example["session_id"]

        def _get_label(self, example: dict) -> str:
            # Label is whether the session had any successful submissions
            return "success" if example.get("submitted_count", 0) > 0 else "failure"

        def evaluate(self, prediction: str, label: str) -> dict:
            # Score: does the generated prompt seem likely to produce
            # queries/scores that lead to successful applications?
            # Simple heuristic: if prediction mentions ATS-specific terms
            pred_lower = prediction.lower() if prediction else ""
            ats_terms = ["greenhouse", "lever", "ashby", "workday", "site:", "ats"]
            quality_signals = sum(1 for t in ats_terms if t in pred_lower)
            accuracy = min(1.0, quality_signals / 3.0)
            return {"accuracy": accuracy}

    return SessionOutcomeBenchmark(outcomes)


def _format_outcome_as_context(outcome: dict) -> str:
    """Format a session outcome as context for the optimization workflow."""
    config = outcome.get("search_config", {})
    errors = outcome.get("error_categories", {})
    ats = outcome.get("ats_breakdown", {})

    return (
        f"Session outcome:\n"
        f"- Keywords: {config.get('keywords', 'N/A')}\n"
        f"- Location: {config.get('location', 'N/A')}\n"
        f"- Remote: {config.get('remote_only', 'N/A')}\n"
        f"- Jobs discovered: {outcome.get('discovery_count', 0)}\n"
        f"- Jobs scored: {outcome.get('scored_count', 0)}\n"
        f"- Applications submitted: {outcome.get('submitted_count', 0)}\n"
        f"- Applications failed: {outcome.get('failed_count', 0)}\n"
        f"- Success rate: {outcome.get('success_rate', 0):.0%}\n"
        f"- Error breakdown: {errors}\n"
        f"- ATS breakdown: {ats}\n"
    )


def run_all_optimizations() -> List[Dict[str, Any]]:
    """Run optimization on all prompt keys. Returns list of results."""
    results = []
    for key in [PROMPT_KEY_DISCOVERY, PROMPT_KEY_SCORING]:
        result = run_optimization(prompt_key=key)
        results.append(result)
    return results


# Allow running as standalone script
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    results = run_all_optimizations()
    for r in results:
        print(f"\n{'='*60}")
        print(f"Prompt: {r.get('prompt_key', 'unknown')}")
        print(f"Version: {r.get('version', 'N/A')}")
        print(f"Score: {r.get('score', 'N/A')}")
        if r.get("error"):
            print(f"Error: {r['error']}")
        print(f"{'='*60}")
