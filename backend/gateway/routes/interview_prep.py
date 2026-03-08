# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Interview Prep Agent API routes."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.gateway.deps import get_current_user
from backend.shared.billing_store import debit_wallet, get_wallet
from backend.shared.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/interview-prep", tags=["interview-prep"])

# In-memory registries
_prep_registry: Dict[str, Dict[str, Any]] = {}
_prep_events: Dict[str, list] = {}
_prep_subscribers: Dict[str, list] = {}


class StartPrepRequest(BaseModel):
    company: str
    role: str
    job_description: Optional[str] = None
    resume_text: str
    application_id: Optional[str] = None


class SubmitAnswerRequest(BaseModel):
    question_id: str
    answer: str


class CoachRequest(BaseModel):
    question_id: str


class PrepResponse(BaseModel):
    session_id: str


def _emit_prep(session_id: str, event_type: str, data: Any):
    """Log and broadcast an SSE event."""
    event = {
        "type": event_type,
        "data": data if isinstance(data, dict) else {"message": str(data)},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    _prep_events.setdefault(session_id, []).append(event)
    for q in _prep_subscribers.get(session_id, []):
        q.put_nowait(event)


async def _run_prep_pipeline(session_id: str, graph, config, initial_state):
    """Run the interview prep graph in the background."""
    try:
        _emit_prep(session_id, "status", {"status": "researching", "message": "Researching company..."})
        async for snapshot in graph.astream(initial_state, config, stream_mode="values"):
            status = snapshot.get("status", "")
            if status:
                messages = {
                    "researching_company": "Researching company culture, news, and values...",
                    "generating_questions": "Generating personalized interview questions...",
                }
                _emit_prep(session_id, "status", {"status": status, "message": messages.get(status, status)})

            if snapshot.get("company_brief") and not _prep_registry[session_id].get("brief_emitted"):
                _emit_prep(session_id, "company_brief", snapshot["company_brief"])
                _prep_registry[session_id]["brief_emitted"] = True

            if snapshot.get("questions") and not _prep_registry[session_id].get("questions_emitted"):
                all_questions = snapshot["questions"]
                is_paid = _prep_registry[session_id].get("paid", False)
                max_free = _prep_registry[session_id].get("max_free_questions", 2)
                # Send all questions for paid/premium users; only free ones otherwise
                _emit_prep(session_id, "questions_ready", {
                    "questions": all_questions if is_paid else all_questions[:max_free],
                    "total": len(all_questions),
                })
                _prep_registry[session_id]["questions_emitted"] = True
                _prep_registry[session_id]["questions"] = all_questions

        _emit_prep(session_id, "ready_for_practice", {"message": "Ready to start mock interview!"})
        _prep_registry[session_id]["status"] = "ready"
    except Exception as exc:
        logger.exception("Interview prep pipeline failed for %s", session_id)
        _emit_prep(session_id, "error", {"message": str(exc)})
        _prep_registry[session_id]["status"] = "failed"


@router.post("", response_model=PrepResponse)
async def start_prep(request: Request, body: StartPrepRequest):
    """Start a new interview prep session."""
    user = get_current_user(request)
    session_id = str(uuid.uuid4())

    premium_emails = [e.strip().lower() for e in settings.PREMIUM_EMAILS.split(",") if e.strip()]
    is_premium = user.get("is_premium", False) or user["email"].lower() in premium_emails

    _prep_registry[session_id] = {
        "user_id": user["id"],
        "user_email": user["email"],
        "status": "starting",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "grades": [],
        "questions_answered": 0,
        "resume_text": body.resume_text,
        "company": body.company,
        "role": body.role,
        "coaching_cache": {},
        "paid": is_premium,
        "max_free_questions": 2,
    }
    _prep_events[session_id] = []

    graph = request.app.state.interview_prep_graph
    config = {"configurable": {"thread_id": f"prep_{session_id}"}}
    initial_state = {
        "session_id": session_id,
        "user_id": user["id"],
        "application_id": body.application_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "company": body.company,
        "role": body.role,
        "job_description": body.job_description or "",
        "resume_text": body.resume_text,
        "questions": [],
        "current_question_index": 0,
        "transcript": [],
        "grades": [],
        "status": "starting",
        "errors": [],
        "waiting_for_answer": False,
        "is_free_session": True,
        "questions_answered": 0,
        "max_free_questions": 2,
    }

    asyncio.create_task(_run_prep_pipeline(session_id, graph, config, initial_state))
    return PrepResponse(session_id=session_id)


@router.post("/{session_id}/answer")
async def submit_answer(request: Request, session_id: str, body: SubmitAnswerRequest):
    """Submit an answer to a question and get grading."""
    if session_id not in _prep_registry:
        raise HTTPException(404, "Prep session not found")

    from backend.shared.llm import build_llm, default_model, invoke_with_retry
    from langchain_core.messages import HumanMessage, SystemMessage

    meta = _prep_registry[session_id]
    questions = meta.get("questions", [])

    # Find the question
    question = None
    for q in questions:
        if q.get("id") == body.question_id:
            question = q
            break

    if not question:
        raise HTTPException(404, "Question not found")

    # Enforce free question limit
    max_free = meta.get("max_free_questions", 2)
    if meta.get("questions_answered", 0) >= max_free and not meta.get("paid"):
        wallet = get_wallet(meta["user_id"])
        raise HTTPException(402, detail={
            "error": "free_limit_reached",
            "questions_answered": meta["questions_answered"],
            "max_free": max_free,
            "balance": wallet["balance"],
            "cost": 1.0,
            "message": "You've used your free questions. Unlock unlimited questions for 1 credit.",
        })

    # Grade the answer
    llm = build_llm(model=default_model(), max_tokens=2048, temperature=0.0)
    messages = [
        SystemMessage(content="""You are an expert interview coach grading a candidate's answer.
Score on these dimensions (0-10 each):
- relevance: How well does the answer address the question?
- specificity: Does it include specific examples and metrics?
- star_structure: Does it follow Situation-Task-Action-Result format?
- confidence: Does the tone convey confidence and competence?
- overall: Overall quality of the answer

Also provide:
- feedback: 2-3 sentences of constructive feedback
- strong_answer_example: A brief example of what a strong answer would include

Return as JSON:
{
  "relevance": 8, "specificity": 6, "star_structure": 5, "confidence": 7, "overall": 7,
  "feedback": "...", "strong_answer_example": "..."
}"""),
        HumanMessage(content=f"Question ({question['category']}): {question['question']}\n\nCandidate's Answer: {body.answer}"),
    ]

    response = await invoke_with_retry(llm, messages)

    from backend.orchestrator.career_pivot.graph import _safe_parse_json
    grade = _safe_parse_json(
        response.content,
        {"relevance": 5, "specificity": 5, "star_structure": 5, "confidence": 5, "overall": 5,
         "feedback": "Unable to grade at this time.", "strong_answer_example": ""},
    )

    grade["question_id"] = body.question_id
    meta.setdefault("grades", []).append(grade)
    meta["questions_answered"] = meta.get("questions_answered", 0) + 1

    _emit_prep(session_id, "answer_graded", {
        "question_id": body.question_id,
        "grade": grade,
        "questions_answered": meta["questions_answered"],
    })

    return {"grade": grade, "questions_answered": meta["questions_answered"]}


@router.post("/{session_id}/coach")
async def get_coaching(request: Request, session_id: str, body: CoachRequest):
    """Get AI coaching hints for a question based on the user's resume."""
    if session_id not in _prep_registry:
        raise HTTPException(404, "Prep session not found")

    meta = _prep_registry[session_id]

    # Enforce free question limit for coaching too
    max_free = meta.get("max_free_questions", 2)
    if meta.get("questions_answered", 0) >= max_free and not meta.get("paid"):
        raise HTTPException(402, detail={
            "error": "free_limit_reached",
            "message": "Unlock unlimited questions to access coaching.",
        })

    # Return cached coaching if available
    cached = meta.get("coaching_cache", {}).get(body.question_id)
    if cached:
        return cached

    from backend.shared.llm import build_llm, default_model, invoke_with_retry
    from langchain_core.messages import HumanMessage, SystemMessage

    questions = meta.get("questions", [])
    question = None
    for q in questions:
        if q.get("id") == body.question_id:
            question = q
            break

    if not question:
        raise HTTPException(404, "Question not found")

    resume_text = meta.get("resume_text", "")
    company = meta.get("company", "")
    role = meta.get("role", "")

    llm = build_llm(model=default_model(), max_tokens=2048, temperature=0.2)
    messages = [
        SystemMessage(content=f"""You are an expert interview coach helping a candidate prepare for a {role} interview at {company}.

The candidate has shared their resume. Your job is to help them craft a strong answer to the interview question by:

1. **resume_highlights**: Pull 2-3 specific, relevant experiences from their resume that directly relate to this question. Quote concrete details — project names, technologies, metrics, team sizes.

2. **star_scaffold**: Provide a STAR framework scaffold tailored to this specific question and the candidate's background:
   - situation: Suggest which resume experience to set the scene with
   - task: What responsibility or challenge to highlight
   - action: What specific actions to emphasize (use first person)
   - result: What metrics or outcomes to mention

3. **key_points**: 3-4 things the interviewer is specifically looking for with this type of question (e.g. "leadership under ambiguity", "quantified impact", "cross-functional collaboration")

4. **pitfalls**: 2-3 common mistakes candidates make when answering this type of question

Return ONLY valid JSON, no markdown fences:
{{
  "resume_highlights": ["Led migration of...", "Managed team of 5..."],
  "star_scaffold": {{
    "situation": "At [company], you were facing...",
    "task": "You were responsible for...",
    "action": "Walk through how you specifically...",
    "result": "Mention the outcome: X% improvement, $Y saved..."
  }},
  "key_points": ["Shows leadership under ambiguity", "Demonstrates technical depth"],
  "pitfalls": ["Don't be too vague — use specific numbers", "Avoid saying 'we' without clarifying your role"]
}}"""),
        HumanMessage(content=f"Interview question ({question['category']}): {question['question']}\n\nCandidate's resume:\n{resume_text[:3000]}"),
    ]

    response = await invoke_with_retry(llm, messages)

    from backend.orchestrator.career_pivot.graph import _safe_parse_json
    coaching = _safe_parse_json(
        response.content,
        {
            "resume_highlights": [],
            "star_scaffold": {
                "situation": "Think about a relevant experience...",
                "task": "What was your specific responsibility?",
                "action": "What steps did you take?",
                "result": "What was the measurable outcome?",
            },
            "key_points": [],
            "pitfalls": [],
        },
    )

    # Cache for this question
    meta.setdefault("coaching_cache", {})[body.question_id] = coaching
    return coaching


@router.post("/{session_id}/unlock")
async def unlock_prep(request: Request, session_id: str):
    """Unlock unlimited interview questions by spending 1 credit."""
    if session_id not in _prep_registry:
        raise HTTPException(404, "Prep session not found")

    user = get_current_user(request)
    meta = _prep_registry[session_id]

    if meta["user_id"] != user["id"]:
        raise HTTPException(403, "Not your session")

    if meta.get("paid"):
        return {"status": "already_unlocked"}

    try:
        result = debit_wallet(
            user["id"], 1.0, "interview_prep", session_id, "Interview prep unlimited questions"
        )
    except ValueError:
        wallet = get_wallet(user["id"])
        raise HTTPException(402, detail={
            "error": "insufficient_credits",
            "balance": wallet["balance"],
            "cost": 1.0,
        })

    meta["paid"] = True

    # Emit remaining questions that were held back
    all_questions = meta.get("questions", [])
    max_free = meta.get("max_free_questions", 2)
    if len(all_questions) > max_free:
        _emit_prep(session_id, "questions_unlocked", {
            "questions": all_questions[max_free:],
        })

    _emit_prep(session_id, "unlocked", {"message": "Unlimited questions unlocked!"})

    return {"status": "unlocked", "balance": result["balance"]}


@router.post("/{session_id}/end")
async def end_prep(request: Request, session_id: str):
    """End the mock interview and generate readiness report."""
    if session_id not in _prep_registry:
        raise HTTPException(404, "Prep session not found")

    meta = _prep_registry[session_id]
    grades = meta.get("grades", [])

    if not grades:
        return {"overall_readiness": 0.0, "category_scores": {}, "message": "No answers submitted"}

    # Calculate scores
    questions = meta.get("questions", [])
    category_totals: Dict[str, list] = {}
    for grade in grades:
        q_id = grade.get("question_id", "")
        category = "unknown"
        for q in questions:
            if q.get("id") == q_id:
                category = q.get("category", "unknown")
                break
        category_totals.setdefault(category, []).append(grade.get("overall", 5))

    category_scores = {cat: round(sum(scores) / len(scores), 1) for cat, scores in category_totals.items()}
    overall = round(sum(g.get("overall", 5) for g in grades) / len(grades), 1)

    report = {
        "overall_readiness": overall,
        "category_scores": category_scores,
        "total_questions_answered": len(grades),
        "focus_areas": [cat for cat, score in category_scores.items() if score < 7.0],
    }

    _emit_prep(session_id, "readiness_report", report)
    _emit_prep(session_id, "done", {"message": "Mock interview complete"})
    meta["status"] = "completed"

    return report


@router.get("/{session_id}/stream")
async def stream_prep(request: Request, session_id: str):
    """SSE stream for an interview prep session."""
    if session_id not in _prep_registry:
        raise HTTPException(404, "Prep session not found")

    queue: asyncio.Queue = asyncio.Queue()
    _prep_subscribers.setdefault(session_id, []).append(queue)

    async def event_generator():
        for event in _prep_events.get(session_id, []):
            yield f"event: {event['type']}\ndata: {json.dumps(event['data'])}\n\n"
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield f"event: {event['type']}\ndata: {json.dumps(event['data'])}\n\n"
                    if event["type"] in ("done", "error"):
                        break
                except asyncio.TimeoutError:
                    yield f"event: ping\ndata: {json.dumps({'ping': True})}\n\n"
        finally:
            if queue in _prep_subscribers.get(session_id, []):
                _prep_subscribers[session_id].remove(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/{session_id}")
async def get_prep(request: Request, session_id: str):
    """Get current state of a prep session."""
    if session_id not in _prep_registry:
        raise HTTPException(404, "Prep session not found")

    meta = _prep_registry[session_id]
    max_free = meta.get("max_free_questions", 2)
    answered = meta.get("questions_answered", 0)
    paid = meta.get("paid", False)
    result: Dict[str, Any] = {
        "session_id": session_id,
        "status": meta.get("status", "unknown"),
        "created_at": meta.get("created_at"),
        "questions_answered": answered,
        "paid": paid,
        "max_free_questions": max_free,
        "free_remaining": max(0, max_free - answered) if not paid else None,
    }

    for event in _prep_events.get(session_id, []):
        if event["type"] == "company_brief":
            result["company_brief"] = event["data"]
        elif event["type"] == "questions_ready":
            # Only expose free questions unless paid
            all_q = meta.get("questions", event["data"]["questions"])
            if paid:
                result["questions"] = all_q
            else:
                result["questions"] = all_q[:max_free]
            result["total_questions"] = len(meta.get("questions", []))
        elif event["type"] == "readiness_report":
            result["readiness_report"] = event["data"]

    result["grades"] = meta.get("grades", [])
    return result
