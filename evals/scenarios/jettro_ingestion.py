"""Executable fixed-fixture ingestion case for Jettro's about page."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic_evals import Case, Dataset

from akgentic_evals.evaluators import (
    AnswerContainsTerms,
    CalledRequiredTools,
    CompletedSuccessfully,
    FollowedMessageRoute,
    ToolArgumentsContain,
    ToolCallsSucceeded,
)
from akgentic_evals.models import AkgenticCaseOutput
from evals.harness.models import (
    KnowledgeCaseInput,
    KnowledgeEvaluationEnvironment,
)
from evals.routes import managed_route

JETTRO_ABOUT_URL = "https://coenradie.com/about"
FIXTURE_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "jettro_about.txt"


def build_jettro_ingestion_dataset(
    timeout_seconds: float = 180.0,
) -> Dataset[KnowledgeCaseInput, AkgenticCaseOutput, dict[str, Any]]:
    return Dataset(
        name="knowledge-akgents/jettro-ingestion",
        cases=[
            Case(
                name="ingest-jettro-about",
                inputs=KnowledgeCaseInput(
                    message=(
                        f"Ingest {JETTRO_ABOUT_URL} and focus on Jettro Coenradie's "
                        "profession and name."
                    ),
                    timeout_seconds=timeout_seconds,
                    environment=KnowledgeEvaluationEnvironment(
                        fixture_source_url=JETTRO_ABOUT_URL,
                        fixture_path=str(FIXTURE_PATH),
                    ),
                ),
                metadata={
                    "source_url": JETTRO_ABOUT_URL,
                    "fixture_captured": "2026-09-12",
                    "mode": "fixed-fixture",
                },
            )
        ],
        evaluators=[
            CompletedSuccessfully(),
            FollowedMessageRoute(
                expected_route=managed_route("@WebIngest")
            ),
            CalledRequiredTools(required_tools=("web_fetch_tool", "update_graph")),
            ToolArgumentsContain(
                tool_name="web_fetch_tool",
                argument_name="urls",
                expected_value=JETTRO_ABOUT_URL,
            ),
            ToolCallsSucceeded(tool_names=("web_fetch_tool", "update_graph")),
            AnswerContainsTerms(required_terms=("Jettro Coenradie", "Software Architect")),
        ],
    )
