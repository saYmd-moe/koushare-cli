from koushare_cli.api import KoushareClient


def test_signature_matches_known_vector():
    sign, ts = KoushareClient.make_signature(
        {"liveId": 900001, "pageNum": 1, "pageSize": 200},
        "GET",
        timestamp_ms=1700000000000,
    )
    assert ts == 1700000000000
    assert sign == "129998dc39f447e567e3e8dda2d9e88e"
