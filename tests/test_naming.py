import pytest

from koushare_cli.errors import KoushareError
from koushare_cli.naming import build_name_context, literal_filename, render_filename


def test_template_uses_video_metadata_and_format_specifier():
    context = build_name_context(
        title="A/B: talk",
        video_id="123",
        live_id="900001",
        quality="FHD",
        height=1080,
        index=2,
        item={"speakerName": "Ada", "startTime": "2026-09-18 10:00:00"},
        live_info={"title": "Conference"},
    )
    name = render_filename("{index:02d} - {speaker} - {title} [{video_id}]", context, fallback="x")
    assert name == "02 - Ada - A_B_ talk [123].mp4"
    assert context["date"] == "2026-09-18 10:00:00"
    assert context["live_title"] == "Conference"


def test_literal_filename_adds_extension_and_strips_paths():
    assert literal_filename("nested/name", fallback="x") == "nested_name.mp4"


def test_unknown_template_field_is_clear_error():
    context = build_name_context(title="T", video_id="1")
    with pytest.raises(KoushareError, match="available fields"):
        render_filename("{does_not_exist}", context, fallback="x")
