from koushare_cli.api import available_qualities, choose_media


PLAYBACK = {
    "playbackUrls": [
        {
            "list": [
                {"labelEn": "SD", "height": 480, "fileUrl": "https://cdn/x/sd.m3u8"},
                {"labelEn": "HD", "height": 720, "fileUrl": "https://cdn/x/hd.m3u8"},
                {"labelEn": "FHD", "height": 1080, "fileUrl": "https://cdn/x/fhd.m3u8"},
            ]
        }
    ]
}


def test_quality_listing():
    assert available_qualities(PLAYBACK) == ["SD", "HD", "FHD"]


def test_best_prefers_fhd():
    url, item = choose_media(PLAYBACK, "best")
    assert url.endswith("fhd.m3u8")
    assert item["height"] == 1080


def test_alias_720p():
    url, _ = choose_media(PLAYBACK, "720p")
    assert url.endswith("hd.m3u8")


def test_fallback_when_requested_quality_missing():
    playback = {"playbackUrls": [{"list": [{"labelEn": "HD", "url": "https://cdn/x/hd.m3u8"}]}]}
    url, _ = choose_media(playback, "FHD")
    assert url.endswith("hd.m3u8")
