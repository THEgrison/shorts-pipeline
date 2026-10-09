"""Base agent interface with Pydantic I/O schemas."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

from shorts_pipeline.db.enums import AgentName


class AgentInput(BaseModel):
    """Base input shared by all agents."""

    job_id: str | None = Field(default=None, description="Orchestrator / Celery job id")
    dry_run: bool = False


class AgentOutput(BaseModel):
    """Base output shared by all agents."""

    success: bool = True
    message: str = ""
    error: str | None = None


InT = TypeVar("InT", bound=AgentInput)
OutT = TypeVar("OutT", bound=AgentOutput)


class AgentError(Exception):
    """Raised when an agent fails in a controlled way."""

    def __init__(self, message: str, *, retryable: bool = True) -> None:
        super().__init__(message)
        self.message = message
        self.retryable = retryable


class Agent(ABC, Generic[InT, OutT]):
    """Independent, replaceable agent with a single entrypoint."""

    name: AgentName

    @abstractmethod
    def run(self, input_data: InT) -> OutT:
        """Execute the agent synchronously. Must be idempotent where possible."""
