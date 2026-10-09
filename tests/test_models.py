"""ORM model smoke tests on SQLite."""

from __future__ import annotations

from sqlalchemy.orm import Session

from shorts_pipeline.db.enums import LicenseBasis, VideoStatus
from shorts_pipeline.db.models import ChannelWhitelist, SourceVideo, StyleTemplate


def test_create_source_video_with_whitelist(sync_session: Session) -> None:
    channel = ChannelWhitelist(
        youtube_channel_id="UCtest123",
        title="Ma chaîne",
        handle="@me",
        is_owned=True,
    )
    sync_session.add(channel)
    sync_session.flush()

    video = SourceVideo(
        youtube_video_id="abc123XYZ",
        channel_id=channel.id,
        youtube_channel_id=channel.youtube_channel_id,
        title="Vidéo test",
        license_basis=LicenseBasis.WHITELIST,
        status=VideoStatus.DISCOVERED,
        relevance_score=87.5,
    )
    sync_session.add(video)
    sync_session.commit()

    loaded = sync_session.query(SourceVideo).filter_by(youtube_video_id="abc123XYZ").one()
    assert loaded.status == VideoStatus.DISCOVERED
    assert loaded.license_basis == LicenseBasis.WHITELIST
    assert loaded.channel is not None
    assert loaded.channel.title == "Ma chaîne"


def test_style_template(sync_session: Session) -> None:
    tmpl = StyleTemplate(
        name="tiktok_default",
        is_default=True,
        config={"font_size": 72, "highlight_color": "#FFE566"},
    )
    sync_session.add(tmpl)
    sync_session.commit()
    assert sync_session.query(StyleTemplate).count() == 1
