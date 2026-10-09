"""Agent modules — each implements a clear run(input) -> output interface."""

from shorts_pipeline.agents.base import Agent, AgentError, AgentInput, AgentOutput

__all__ = ["Agent", "AgentError", "AgentInput", "AgentOutput"]
