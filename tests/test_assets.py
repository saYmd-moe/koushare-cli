from pathlib import Path

from koushare_cli.assets import cover_path, cover_url, description_html, subtitle_path, subtitle_urls


def test_cover_prefers_video_metadata_and_keeps_known_extension():
    metadata = {"coverUrl": "https://cdn.example/video.webp?token=temporary"}
    live_metadata = {"cover": "https://cdn.example/live.png"}
    url = cover_url(metadata, live_metadata)
    assert url == metadata["coverUrl"]
    assert cover_path(Path("Talk [700001].mp4"), url) == Path("Talk [700001].cover.webp")


def test_description_preserves_available_localized_html():
    rendered = description_html(
        {"blurb": "<p>中文简介</p>", "blurbEn": "<p>English abstract</p>"},
        {"brief": "<p>中文简介</p>"},
    )
    assert rendered.startswith("<!doctype html>")
    assert rendered.count("<p>中文简介</p>") == 1
    assert "English abstract" in rendered


def test_subtitle_discovery_is_limited_to_subtitle_fields_and_deduplicates():
    url = "https://cdn.example/captions/zh-CN.vtt?token=temporary"
    metadata = {
        "subtitleList": [{"subtitleUrl": url}],
        "unrelatedUrl": "https://cdn.example/not-a-subtitle.vtt",
    }
    assert subtitle_urls(metadata, {}) == [("subtitle-1", url)]
    assert subtitle_path(Path("Talk.mp4"), "zh-CN", url, 1) == Path("Talk.zh-CN.vtt")
