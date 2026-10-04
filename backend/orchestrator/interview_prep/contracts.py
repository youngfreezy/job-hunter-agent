"""Validated model results for interview preparation; no fabricated fallbacks."""
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

MAX_RESUME_CHARACTERS = 50_000

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Score = Annotated[int, Field(strict=True, ge=0, le=10)]


class PrepContract(BaseModel):
    model_config = ConfigDict(extra='forbid')


class CompanyBrief(PrepContract):
    mission: Text
    culture: Text
    things_to_mention: list[Text] = Field(min_length=1)
    interview_tips: list[Text] = Field(min_length=1)


class Question(PrepContract):
    category: Literal['behavioral', 'technical', 'situational', 'culture_fit']
    question: Text


class QuestionSet(PrepContract):
    questions: list[Question] = Field(min_length=15, max_length=15)


class Grade(PrepContract):
    relevance: Score
    specificity: Score
    star_structure: Score
    confidence: Score
    overall: Score
    feedback: Text
    strong_answer_example: Text


class StarScaffold(PrepContract):
    situation: Text
    task: Text
    action: Text
    result: Text


class Coaching(PrepContract):
    # No resume evidence is preferable to invented personal achievements.
    resume_highlights: list[Text]
    star_scaffold: StarScaffold
    key_points: list[Text] = Field(min_length=1)
    pitfalls: list[Text] = Field(min_length=1)


class InvalidPrepOutput(ValueError):
    pass


def complete_resume_context(text: str) -> str:
    """Keep every uploaded fact; reject oversized legacy state instead of truncating."""
    if not isinstance(text, str) or len(text) > MAX_RESUME_CHARACTERS:
        raise InvalidPrepOutput("Resume exceeds the interview preparation text limit.")
    return text


async def generate_validated(llm, schema, messages):
    from langchain_core.exceptions import OutputParserException
    from pydantic import ValidationError
    from backend.shared.llm import invoke_with_retry

    try:
        result = await invoke_with_retry(llm.with_structured_output(schema), messages)
        return schema.model_validate(result)
    except (ValidationError, OutputParserException, TypeError) as exc:
        # Provider parser details may include candidate data; never expose them.
        raise InvalidPrepOutput('The model returned an incomplete response. Please try again.') from exc
