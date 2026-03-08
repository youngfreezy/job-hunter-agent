# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Neo4j knowledge graph client for ATS strategies and cross-session learning.

Provides async queries for ATS form field patterns, application strategies,
and screening question answers.  Falls back gracefully (returns ``None`` or
empty results) when Neo4j is unavailable so the rest of the pipeline keeps
running.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from backend.shared.config import get_settings

logger = logging.getLogger(__name__)

# neo4j driver is an optional dependency -- guard the import so the rest
# of the application can start even if neo4j is not installed.
try:
    from neo4j import AsyncGraphDatabase, AsyncDriver
except ImportError:
    AsyncGraphDatabase = None  # type: ignore[assignment,misc]
    AsyncDriver = None  # type: ignore[assignment,misc]


class Neo4jClient:
    """Async Neo4j client for the ATS knowledge graph.

    All public query methods degrade gracefully: if the driver is not
    configured or a query fails, they log a warning and return ``None``
    (or an empty list) instead of raising.
    """

    def __init__(self) -> None:
        self._driver: Optional[Any] = None  # AsyncDriver when available
        settings = get_settings()
        self._uri = settings.NEO4J_URI
        self._user = settings.NEO4J_USER
        self._password = settings.NEO4J_PASSWORD

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Initialise the Neo4j async driver.

        Silently no-ops if credentials are missing or the ``neo4j``
        package is not installed.
        """
        if AsyncGraphDatabase is None:
            logger.warning(
                "neo4j package not installed -- knowledge graph features disabled"
            )
            return

        if not all([self._uri, self._user, self._password]):
            logger.warning(
                "Neo4j credentials not configured -- knowledge graph features disabled"
            )
            return

        try:
            self._driver = AsyncGraphDatabase.driver(
                self._uri,
                auth=(self._user, self._password),
            )
            # Verify connectivity
            await self._driver.verify_connectivity()
            logger.info("Neo4j connected to %s", self._uri)
        except Exception as exc:
            logger.warning("Neo4j connection failed (%s) -- degrading gracefully", exc)
            self._driver = None

    async def close(self) -> None:
        """Close the Neo4j driver."""
        if self._driver is not None:
            await self._driver.close()
            self._driver = None
            logger.info("Neo4j connection closed")

    @property
    def available(self) -> bool:
        """Return ``True`` if the driver is connected and usable."""
        return self._driver is not None

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    async def _run_query(
        self,
        query: str,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Execute a Cypher query and return a list of record dicts.

        Returns an empty list on any failure.
        """
        if not self.available:
            return []
        try:
            async with self._driver.session() as session:
                result = await session.run(query, parameters or {})
                records = await result.data()
                return records
        except Exception as exc:
            logger.warning("Neo4j query failed: %s -- %s", query[:120], exc)
            return []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_ats_strategy(self, company: str) -> Optional[Dict[str, Any]]:
        """Look up the known ATS platform and application strategy for *company*.

        Returns a dict with keys ``ats_name``, ``ats_version``,
        ``strategy_name``, ``steps_json``, ``success_rate`` -- or ``None``
        if nothing is found.
        """
        query = """
        MATCH (c:Company {name: $company})-[:USES_ATS]->(ats:ATSPlatform)
        OPTIONAL MATCH (ats)-[:REQUIRES_STRATEGY]->(s:ApplicationStrategy)
        RETURN ats.name       AS ats_name,
               ats.version    AS ats_version,
               s.name         AS strategy_name,
               s.steps_json   AS steps_json,
               s.success_rate AS success_rate
        LIMIT 1
        """
        records = await self._run_query(query, {"company": company})
        if not records:
            return None
        return records[0]

    async def get_form_fields(self, ats_type: str) -> List[Dict[str, Any]]:
        """Return known form fields for an ATS platform type.

        Each dict contains ``label``, ``type``, and ``common_values``.
        """
        query = """
        MATCH (ats:ATSPlatform {name: $ats_type})-[:HAS_FORM_FIELD]->(f:FormField)
        RETURN f.label         AS label,
               f.type          AS type,
               f.common_values AS common_values
        """
        return await self._run_query(query, {"ats_type": ats_type})

    async def record_application(
        self,
        company: str,
        ats_type: str,
        success: bool,
        strategy: Optional[str] = None,
    ) -> None:
        """Record the outcome of an application attempt for future learning.

        Creates or updates Company and ATSPlatform nodes, and -- if a
        strategy name is given -- updates the strategy's success rate.
        """
        query = """
        MERGE (c:Company {name: $company})
        MERGE (ats:ATSPlatform {name: $ats_type})
        MERGE (c)-[:USES_ATS]->(ats)
        WITH ats
        WHERE $strategy IS NOT NULL
        MERGE (s:ApplicationStrategy {name: $strategy})
        MERGE (ats)-[:REQUIRES_STRATEGY]->(s)
        SET s.total_attempts = coalesce(s.total_attempts, 0) + 1,
            s.successes = CASE WHEN $success THEN coalesce(s.successes, 0) + 1
                               ELSE coalesce(s.successes, 0) END,
            s.success_rate = CASE WHEN (coalesce(s.total_attempts, 0) + 1) > 0
                THEN toFloat(
                    CASE WHEN $success THEN coalesce(s.successes, 0) + 1
                         ELSE coalesce(s.successes, 0) END
                ) / (coalesce(s.total_attempts, 0) + 1)
                ELSE 0.0 END
        """
        await self._run_query(
            query,
            {
                "company": company,
                "ats_type": ats_type,
                "success": success,
                "strategy": strategy,
            },
        )

    async def get_best_answer(self, question_text: str) -> Optional[str]:
        """Look up the most effective known answer for a screening question.

        Uses a case-insensitive substring match on the question text.
        Returns the answer text or ``None``.
        """
        query = """
        MATCH (q:Question)-[:BEST_ANSWERED_WITH]->(a:Answer)
        WHERE toLower(q.text) CONTAINS toLower($question_text)
        RETURN a.text AS answer, a.effectiveness AS effectiveness
        ORDER BY a.effectiveness DESC
        LIMIT 1
        """
        records = await self._run_query(query, {"question_text": question_text})
        if not records:
            return None
        return records[0].get("answer")

    async def record_screening_question(
        self,
        question_text: str,
        answer_text: str,
        company: str,
        effective: bool = False,
    ) -> None:
        """Store a screening question and the answer used.

        If *effective* is ``True`` (e.g., the application led to a
        callback), the answer's effectiveness score is incremented.
        """
        query = """
        MERGE (q:Question {text: $question_text})
        MERGE (c:Company {name: $company})
        MERGE (q)-[:ASKED_BY]->(c)
        MERGE (a:Answer {text: $answer_text})
        MERGE (q)-[:BEST_ANSWERED_WITH]->(a)
        SET a.effectiveness = CASE WHEN $effective
                THEN coalesce(a.effectiveness, 0.0) + 1.0
                ELSE coalesce(a.effectiveness, 0.0) END
        """
        await self._run_query(
            query,
            {
                "question_text": question_text,
                "answer_text": answer_text,
                "company": company,
                "effective": effective,
            },
        )


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

neo4j_client = Neo4jClient()
