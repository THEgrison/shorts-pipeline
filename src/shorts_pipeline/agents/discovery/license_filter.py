"""Mandatory license authorization filter."""

from __future__ import annotations

from dataclasses import dataclass

from shorts_pipeline.clients.youtube import YouTubeVideoSnippet
from shorts_pipeline.db.enums import LicenseBasis


@dataclass(frozen=True, slots=True)
class AuthorizationResult:
    allowed: bool
    basis: LicenseBasis | None
    reason: str


def authorize_video(
    video: YouTubeVideoSnippet,
    *,
    whitelist_channel_ids: set[str],
) -> AuthorizationResult:
    """
    Keep only:
      (a) channels in the owned/authorized whitelist, OR
      (b) videos under Creative Commons license.
    """
    if video.channel_id in whitelist_channel_ids:
        return AuthorizationResult(
            allowed=True,
            basis=LicenseBasis.WHITELIST,
            reason=f"channel {video.channel_id} is whitelisted",
        )
    if video.license == "creativeCommon":
        return AuthorizationResult(
            allowed=True,
            basis=LicenseBasis.CREATIVE_COMMONS,
            reason="video licensed as creativeCommon",
        )
    return AuthorizationResult(
        allowed=False,
        basis=None,
        reason="not whitelisted and not Creative Commons",
    )
