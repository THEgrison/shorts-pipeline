"""Agent base interface contract."""

from __future__ import annotations

from shorts_pipeline.agents.base import Agent, AgentInput, AgentOutput
from shorts_pipeline.db.enums import AgentName


class EchoInput(AgentInput):
    text: str


class EchoOutput(AgentOutput):
    echoed: str = ""


class EchoAgent(Agent[EchoInput, EchoOutput]):
    name = AgentName.ORCHESTRATOR

    def run(self, input_data: EchoInput) -> EchoOutput:
        return EchoOutput(success=True, message="ok", echoed=input_data.text)


def test_agent_run() -> None:
    agent = EchoAgent()
    result = agent.run(EchoInput(text="ping", dry_run=True))
    assert result.success
    assert result.echoed == "ping"
