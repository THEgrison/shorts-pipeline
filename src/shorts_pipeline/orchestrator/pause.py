"""In-process + Redis-backed agent pause flags."""

from __future__ import annotations

from typing import Any

from shorts_pipeline.config import get_settings
from shorts_pipeline.db.enums import AgentName
from shorts_pipeline.logging_setup import get_logger

logger = get_logger(__name__)

_PAUSE_KEY = "shorts_pipeline:agent_paused:{agent}"
_local_paused: set[str] = set()


def _redis() -> Any | None:
    try:
        import redis

        settings = get_settings()
        return redis.Redis.from_url(settings.redis_url, decode_responses=True)
    except Exception:
        return None


def pause_agent(agent: AgentName) -> None:
    """Pause an agent (new jobs should no-op / requeue)."""
    key = _PAUSE_KEY.format(agent=agent.value)
    client = _redis()
    if client is not None:
        try:
            client.set(key, "1")
        except Exception:
            _local_paused.add(agent.value)
    else:
        _local_paused.add(agent.value)
    logger.warning("agent.paused", agent=agent.value)


def resume_agent(agent: AgentName) -> None:
    """Resume a paused agent."""
    key = _PAUSE_KEY.format(agent=agent.value)
    client = _redis()
    if client is not None:
        try:
            client.delete(key)
        except Exception:
            _local_paused.discard(agent.value)
    _local_paused.discard(agent.value)
    logger.info("agent.resumed", agent=agent.value)


def is_agent_paused(agent: AgentName) -> bool:
    """Return True if the agent is currently paused."""
    if agent.value in _local_paused:
        return True
    key = _PAUSE_KEY.format(agent=agent.value)
    client = _redis()
    if client is None:
        return False
    try:
        return bool(client.get(key) == "1")
    except Exception:
        return agent.value in _local_paused


def clear_local_pauses() -> None:
    """Test helper."""
    _local_paused.clear()
