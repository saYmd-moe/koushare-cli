import pytest

from koushare_cli.errors import UnsupportedUrl
from koushare_cli.urls import parse_target


def test_current_live_url_without_vid():
    target = parse_target("https://www.koushare.com/live/details/900001")
    assert target.kind == "live"
    assert target.live_id == "900001"
    assert target.video_id is None


def test_current_live_url_with_vid():
    target = parse_target("https://www.koushare.com/live/details/900001?vid=123456")
    assert target.live_id == "900001"
    assert target.video_id == "123456"


def test_video_url():
    target = parse_target("https://www.koushare.com/video/videodetail/123")
    assert target.kind == "video"
    assert target.video_id == "123"


def test_video_details_preserves_ticket():
    target = parse_target("https://www.koushare.com/video/details/900002?ticket=abc123")
    assert target.video_id == "900002"
    assert target.ticket == "abc123"


def test_legacy_room():
    target = parse_target("https://www.koushare.com/lives/room/987")
    assert target.kind == "legacy-room"
    assert target.room_id == "987"


def test_prefixes_and_bare_id():
    assert parse_target("900001").live_id == "900001"
    assert parse_target("video:123").video_id == "123"
    assert parse_target("room:456").room_id == "456"


def test_reject_foreign_host():
    with pytest.raises(UnsupportedUrl):
        parse_target("https://example.com/live/details/900001")
