from koushare_cli.api import KoushareClient


def test_signature_matches_known_vector():
    sign, ts = KoushareClient.make_signature(
        {"liveId": 900001, "pageNum": 1, "pageSize": 200},
        "GET",
        timestamp_ms=1700000000000,
    )
    assert ts == 1700000000000
    assert sign == "3f4a6c9c36e8a5fe7d0d814bf0e95afb"
