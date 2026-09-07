"""Agent card definitions for the Knowledge Akgents team.

Three roles:
- ``@Manager``   — routes the human's request to the right specialist.
- ``@Knowledge`` — answers questions by querying the shared knowledge base.
- ``@WebIngest`` — fetches a web page, extracts knowledge, and stores it in the same base.
"""

from __future__ import annotations

from typing import Any, cast

from akgentic.agent import AgentConfig
from akgentic.core import AgentCard
from akgentic.llm import ModelConfig, PromptTemplate

from knowledge_akgents.settings import settings
from knowledge_akgents.tools import (
    knowledge_ingest_card,
    knowledge_query_card,
    vector_store_card,
    web_card,
)


def _model() -> ModelConfig:
    # settings.llm_provider is a plain str; ModelConfig.provider is a Literal.
    return ModelConfig(provider=cast(Any, settings.llm_provider), model=settings.llm_model)


MANAGER_PROMPT = """You are the Manager of a small knowledge team. You never answer
knowledge questions yourself — you route.

Team:
- @Knowledge: answers questions using the shared knowledge base.
- @WebIngest: fetches a web page, extracts knowledge from it, and stores it in the
  same knowledge base.

Routing rules:
- If the user wants to add/ingest/learn from a URL or web page, delegate to @WebIngest
  with the URL and what to focus on.
- If the user asks a question to be answered from stored knowledge, delegate to @Knowledge.
- Relay the specialist's answer back to the human clearly and concisely.
"""

KNOWLEDGE_PROMPT = """You are the Knowledge agent. Answer questions using ONLY the shared
knowledge base via your knowledge-graph tools (search the graph, read entities/relations).
If the knowledge base has nothing relevant, say so plainly and suggest ingesting a source
via @WebIngest rather than inventing an answer. Cite the entities/relations you relied on.
"""

WEBINGEST_PROMPT = """You are the Web-Ingest agent. Given a URL (and optionally a focus),
use your web tools to fetch and extract the page content, then distill it into knowledge:
identify the key entities and the relations between them, and write them into the shared
knowledge base using your knowledge-graph update tool. Prefer a small number of accurate,
well-described entities and relations over many noisy ones. Report a short summary of what
you stored (entities and relations), so it can later be queried by @Knowledge.
"""


def manager_card() -> AgentCard:
    return AgentCard(
        agent_class="akgentic.agent.BaseAgent",
        description="Routes requests to the Knowledge and Web-Ingest specialists.",
        skills=["coordination", "routing"],
        config=AgentConfig(
            name="@Manager",
            role="Manager",
            prompt=PromptTemplate(template=MANAGER_PROMPT),
            model_cfg=_model(),
            tools=[],
        ),
    )


def knowledge_card() -> AgentCard:
    return AgentCard(
        agent_class="akgentic.agent.BaseAgent",
        description="Answers questions from the shared knowledge base.",
        skills=["knowledge", "retrieval", "question-answering"],
        config=AgentConfig(
            name="@Knowledge",
            role="Knowledge",
            prompt=PromptTemplate(template=KNOWLEDGE_PROMPT),
            model_cfg=_model(),
            tools=[vector_store_card(), knowledge_query_card()],
        ),
    )


def webingest_card() -> AgentCard:
    return AgentCard(
        agent_class="akgentic.agent.BaseAgent",
        description="Fetches web pages and stores extracted knowledge in the shared base.",
        skills=["web", "extraction", "ingestion"],
        config=AgentConfig(
            name="@WebIngest",
            role="WebIngest",
            prompt=PromptTemplate(template=WEBINGEST_PROMPT),
            model_cfg=_model(),
            tools=[vector_store_card(), web_card(), knowledge_ingest_card()],
        ),
    )


def all_cards() -> list[AgentCard]:
    return [manager_card(), knowledge_card(), webingest_card()]
