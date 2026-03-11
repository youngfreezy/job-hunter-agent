# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Persistent storage for the agent marketplace.

Follows the billing_store.py pattern: sync psycopg for DDL,
sync helpers for CRUD via get_connection().
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Dict, List, Optional

from backend.shared.db import get_connection

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Table creation (called from main.py lifespan)
# ---------------------------------------------------------------------------

_CREATE_TABLES = """
CREATE TABLE IF NOT EXISTS agents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    long_description TEXT,
    icon TEXT DEFAULT 'bot',
    category TEXT NOT NULL,
    credit_cost DECIMAL(10,2) DEFAULT 1.0,
    is_builtin BOOLEAN DEFAULT TRUE,
    is_published BOOLEAN DEFAULT TRUE,
    author_user_id UUID REFERENCES users(id),
    graph_key TEXT,
    route_prefix TEXT,
    frontend_path TEXT,
    input_schema JSONB,
    stages JSONB,
    total_uses INTEGER DEFAULT 0,
    avg_rating DECIMAL(3,2) DEFAULT 0.00,
    rating_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS agent_reviews (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID REFERENCES agents(id) ON DELETE CASCADE NOT NULL,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE NOT NULL,
    session_id TEXT,
    rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
    review_text TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(agent_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_agent_reviews_agent ON agent_reviews(agent_id);

CREATE TABLE IF NOT EXISTS agent_usage (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID REFERENCES agents(id) ON DELETE CASCADE NOT NULL,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE NOT NULL,
    session_id TEXT,
    status TEXT DEFAULT 'started',
    started_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_agent_usage_agent ON agent_usage(agent_id);
CREATE INDEX IF NOT EXISTS idx_agent_usage_user ON agent_usage(user_id);
"""


async def ensure_agent_tables() -> None:
    """Create marketplace tables if they don't exist."""
    try:
        with get_connection() as conn:
            conn.execute(_CREATE_TABLES)
            conn.commit()
            logger.info("Agent marketplace tables ensured")
    except Exception:
        logger.exception("Failed to create agent marketplace tables")


# ---------------------------------------------------------------------------
# Built-in agent seed data
# ---------------------------------------------------------------------------

BUILTIN_AGENTS = [
    {
        "slug": "job-hunter",
        "name": "Job Hunter",
        "description": "Automated job search, resume tailoring, and application submission across LinkedIn, Glassdoor, ZipRecruiter, and Indeed.",
        "long_description": "The core JobHunter agent discovers matching jobs across 4 major boards, scores them against your profile, tailors your resume and cover letter for each position, and auto-submits applications through ATS platforms like Greenhouse, Lever, and Workday.",
        "icon": "briefcase",
        "category": "career",
        "credit_cost": 1.0,
        "graph_key": "graph",
        "route_prefix": "/api/sessions",
        "frontend_path": "/session/new",
        "stages": json.dumps([
            {"name": "intake", "description": "Parse your job preferences"},
            {"name": "coaching", "description": "Refine your resume with AI career coach"},
            {"name": "discovery", "description": "Search across 4 job boards"},
            {"name": "scoring", "description": "Rank and score matches"},
            {"name": "tailoring", "description": "Customize resume for each role"},
            {"name": "application", "description": "Auto-fill and submit applications"},
            {"name": "verification", "description": "Confirm submissions"},
        ]),
    },
    {
        "slug": "career-pivot",
        "name": "Career Pivot Advisor",
        "description": "Analyze your automation risk, discover adjacent roles, and plan career transitions with data-driven insights.",
        "long_description": "Powered by O*NET data and AI analysis, this agent assesses your current role's automation risk, identifies transferable skills, maps adjacent career paths, and provides actionable transition strategies with salary projections.",
        "icon": "compass",
        "category": "career",
        "credit_cost": 1.0,
        "graph_key": "career_pivot_graph",
        "route_prefix": "/api/career-pivot",
        "frontend_path": "/career-pivot",
        "stages": json.dumps([
            {"name": "parse_skills", "description": "Extract skills from your profile"},
            {"name": "research", "description": "Research O*NET occupational data"},
            {"name": "automation_risk", "description": "Assess automation exposure"},
            {"name": "adjacent_roles", "description": "Map adjacent career paths"},
            {"name": "cross_industry", "description": "Identify cross-industry opportunities"},
        ]),
    },
    {
        "slug": "interview-prep",
        "name": "Interview Prep Coach",
        "description": "Generate tailored interview questions and get real-time coaching on your answers for any role or company.",
        "long_description": "This agent researches the target company, generates role-specific behavioral and technical questions, then provides detailed coaching feedback on your answers with scoring and improvement suggestions.",
        "icon": "mic",
        "category": "interview",
        "credit_cost": 1.0,
        "graph_key": "interview_prep_graph",
        "route_prefix": "/api/interview-prep",
        "frontend_path": "/interview-prep",
        "stages": json.dumps([
            {"name": "research", "description": "Research the target company"},
            {"name": "questions", "description": "Generate tailored questions"},
            {"name": "coaching", "description": "Coach on your answers"},
        ]),
    },
    {
        "slug": "freelance",
        "name": "Freelance Matchmaker",
        "description": "Find freelance and contract gigs on Upwork and LinkedIn, score matches, and generate winning proposals.",
        "long_description": "This agent searches freelance platforms for gigs matching your skills, scores them based on fit and pay rate, then generates customized proposals optimized for each platform's algorithm and client expectations.",
        "icon": "rocket",
        "category": "freelance",
        "credit_cost": 1.0,
        "graph_key": "freelance_graph",
        "route_prefix": "/api/freelance",
        "frontend_path": "/freelance",
        "stages": json.dumps([
            {"name": "profiles", "description": "Generate platform profiles"},
            {"name": "search", "description": "Search for matching gigs"},
            {"name": "scoring", "description": "Score and rank matches"},
            {"name": "proposals", "description": "Generate winning proposals"},
        ]),
    },
]


def seed_builtin_agents() -> None:
    """Insert or update built-in agents. Idempotent (ON CONFLICT DO UPDATE)."""
    try:
        with get_connection() as conn:
            for agent in BUILTIN_AGENTS:
                conn.execute(
                    """INSERT INTO agents (slug, name, description, long_description, icon,
                                          category, credit_cost, is_builtin, is_published,
                                          graph_key, route_prefix, frontend_path, stages)
                       VALUES (%(slug)s, %(name)s, %(description)s, %(long_description)s, %(icon)s,
                               %(category)s, %(credit_cost)s, TRUE, TRUE,
                               %(graph_key)s, %(route_prefix)s, %(frontend_path)s, %(stages)s)
                       ON CONFLICT (slug) DO UPDATE SET
                           name = EXCLUDED.name,
                           description = EXCLUDED.description,
                           long_description = EXCLUDED.long_description,
                           icon = EXCLUDED.icon,
                           category = EXCLUDED.category,
                           credit_cost = EXCLUDED.credit_cost,
                           graph_key = EXCLUDED.graph_key,
                           route_prefix = EXCLUDED.route_prefix,
                           frontend_path = EXCLUDED.frontend_path,
                           stages = EXCLUDED.stages,
                           updated_at = NOW()
                    """,
                    agent,
                )
            conn.commit()
            logger.info("Seeded %d built-in agents", len(BUILTIN_AGENTS))
    except Exception:
        logger.exception("Failed to seed built-in agents")


# ---------------------------------------------------------------------------
# CRUD operations
# ---------------------------------------------------------------------------

def list_published_agents(category: Optional[str] = None) -> List[Dict[str, Any]]:
    """List all published agents, optionally filtered by category."""
    with get_connection() as conn:
        if category:
            cur = conn.execute(
                """SELECT id, slug, name, description, long_description, icon, category,
                          credit_cost, is_builtin, total_uses, avg_rating, rating_count,
                          frontend_path, stages, created_at
                   FROM agents
                   WHERE is_published = TRUE AND category = %s
                   ORDER BY total_uses DESC, created_at ASC""",
                (category,),
            )
        else:
            cur = conn.execute(
                """SELECT id, slug, name, description, long_description, icon, category,
                          credit_cost, is_builtin, total_uses, avg_rating, rating_count,
                          frontend_path, stages, created_at
                   FROM agents
                   WHERE is_published = TRUE
                   ORDER BY total_uses DESC, created_at ASC"""
            )
        return [_row_to_agent(row) for row in cur.fetchall()]


def get_agent_by_slug(slug: str) -> Optional[Dict[str, Any]]:
    """Get a single agent by slug."""
    with get_connection() as conn:
        cur = conn.execute(
            """SELECT id, slug, name, description, long_description, icon, category,
                      credit_cost, is_builtin, total_uses, avg_rating, rating_count,
                      frontend_path, stages, created_at
               FROM agents WHERE slug = %s""",
            (slug,),
        )
        row = cur.fetchone()
        return _row_to_agent(row) if row else None


def _row_to_agent(row) -> Dict[str, Any]:
    """Convert a database row to an agent dict."""
    stages = row[13]
    if isinstance(stages, str):
        stages = json.loads(stages)
    return {
        "id": str(row[0]),
        "slug": row[1],
        "name": row[2],
        "description": row[3],
        "long_description": row[4],
        "icon": row[5],
        "category": row[6],
        "credit_cost": float(row[7]),
        "is_builtin": row[8],
        "total_uses": row[9],
        "avg_rating": float(row[10]) if row[10] else 0.0,
        "rating_count": row[11],
        "frontend_path": row[12],
        "stages": stages,
        "created_at": row[14].isoformat() if row[14] else None,
    }


# ---------------------------------------------------------------------------
# Usage tracking
# ---------------------------------------------------------------------------

def record_usage(agent_slug: str, user_id: str, session_id: Optional[str] = None) -> Optional[str]:
    """Record an agent usage event. Returns usage ID or None if agent not found."""
    with get_connection() as conn:
        cur = conn.execute("SELECT id FROM agents WHERE slug = %s", (agent_slug,))
        row = cur.fetchone()
        if not row:
            return None
        agent_id = row[0]
        usage_id = str(uuid.uuid4())
        conn.execute(
            """INSERT INTO agent_usage (id, agent_id, user_id, session_id)
               VALUES (%s, %s, %s, %s)""",
            (usage_id, agent_id, user_id, session_id),
        )
        conn.execute(
            "UPDATE agents SET total_uses = total_uses + 1, updated_at = NOW() WHERE id = %s",
            (agent_id,),
        )
        conn.commit()
        return usage_id


def complete_usage(usage_id: str, status: str = "completed") -> None:
    """Mark an agent usage as completed or failed."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE agent_usage SET status = %s, completed_at = NOW() WHERE id = %s",
            (status, usage_id),
        )
        conn.commit()


# ---------------------------------------------------------------------------
# Reviews
# ---------------------------------------------------------------------------

def submit_review(
    agent_slug: str,
    user_id: str,
    rating: int,
    review_text: Optional[str] = None,
    session_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Submit or update a review. Returns the review dict or None if agent not found."""
    with get_connection() as conn:
        cur = conn.execute("SELECT id FROM agents WHERE slug = %s", (agent_slug,))
        row = cur.fetchone()
        if not row:
            return None
        agent_id = row[0]
        review_id = str(uuid.uuid4())
        cur = conn.execute(
            """INSERT INTO agent_reviews (id, agent_id, user_id, session_id, rating, review_text)
               VALUES (%s, %s, %s, %s, %s, %s)
               ON CONFLICT (agent_id, user_id) DO UPDATE SET
                   rating = EXCLUDED.rating,
                   review_text = EXCLUDED.review_text,
                   session_id = EXCLUDED.session_id,
                   created_at = NOW()
               RETURNING id, rating, review_text, created_at""",
            (review_id, agent_id, user_id, session_id, rating, review_text),
        )
        result = cur.fetchone()

        # Recalculate aggregate rating atomically
        conn.execute(
            """UPDATE agents SET
                   avg_rating = (SELECT COALESCE(AVG(rating), 0) FROM agent_reviews WHERE agent_id = %s),
                   rating_count = (SELECT COUNT(*) FROM agent_reviews WHERE agent_id = %s),
                   updated_at = NOW()
               WHERE id = %s""",
            (agent_id, agent_id, agent_id),
        )
        conn.commit()
        return {
            "id": str(result[0]),
            "rating": result[1],
            "review_text": result[2],
            "created_at": result[3].isoformat() if result[3] else None,
        }


def list_reviews(agent_slug: str, limit: int = 20, offset: int = 0) -> List[Dict[str, Any]]:
    """List reviews for an agent."""
    with get_connection() as conn:
        cur = conn.execute(
            """SELECT r.id, r.rating, r.review_text, r.created_at, u.name, u.email
               FROM agent_reviews r
               JOIN agents a ON a.id = r.agent_id
               LEFT JOIN users u ON u.id = r.user_id
               WHERE a.slug = %s
               ORDER BY r.created_at DESC
               LIMIT %s OFFSET %s""",
            (agent_slug, limit, offset),
        )
        return [
            {
                "id": str(row[0]),
                "rating": row[1],
                "review_text": row[2],
                "created_at": row[3].isoformat() if row[3] else None,
                "user_name": row[4] or (row[5].split("@")[0] if row[5] else "Anonymous"),
            }
            for row in cur.fetchall()
        ]
