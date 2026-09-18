import json
import os
import time

from koushare_cli.api import KoushareClient
from koushare_cli.auth import CredentialStore, Credentials


class Response:
    status_code = 200

    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload


class Session:
    def __init__(self, payload):
        self.payload = payload
        self.headers = {}
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        return Response(self.payload)

    def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        return Response(self.payload)


def token_payload(access="access", refresh="refresh"):
    return {
        "code": 200000,
        "data": {
            "data": {
                "access_token": access,
                "refresh_token": refresh,
                "expire_in": 3_600_000,
                "refresh_expire_in": 7_200_000,
            }
        },
    }


def test_account_login_uses_web_request_shape():
    session = Session(token_payload())
    credentials = KoushareClient.login("13800138000", "secret", session=session)
    method, url, kwargs = session.calls[0]
    assert method == "POST"
    assert url.endswith("/iam/userLogin/accountLogin")
    assert kwargs["json"] == {
        "username": "13800138000",
        "password": "secret",
        "flag": False,
        "areaCode": "86",
    }
    assert credentials.access_token == "access"
    assert credentials.refresh_token == "refresh"
    assert credentials.access_expires_at > time.time()


def test_email_login_does_not_send_phone_area_code():
    session = Session(token_payload())
    KoushareClient.login("person@example.com", "secret", session=session)
    assert "areaCode" not in session.calls[0][2]["json"]


def test_refresh_uses_refresh_token_and_persists(tmp_path):
    path = tmp_path / "auth.json"
    store = CredentialStore(path)
    old = Credentials("old-access", "old-refresh", access_expires_at=0, refresh_expires_at=time.time() + 1000)
    session = Session(token_payload("new-access", "new-refresh"))
    client = KoushareClient(credentials=old, credential_store=store, session=session)
    refreshed = client.refresh_auth()
    assert session.calls[0][2]["headers"]["Authorization"] == "old-refresh"
    assert refreshed.access_token == "new-access"
    assert store.load().refresh_token == "new-refresh"


def test_credential_store_is_private_and_never_contains_password(tmp_path):
    path = tmp_path / "nested" / "auth.json"
    store = CredentialStore(path)
    store.save(Credentials("a", "r", username="user@example.com"))
    if os.name != "nt":
        assert os.stat(path).st_mode & 0o777 == 0o600
    raw = json.loads(path.read_text())
    assert raw["access_token"] == "a"
    assert "password" not in raw


def test_auth_file_environment_override(monkeypatch, tmp_path):
    from koushare_cli.auth import default_auth_path

    custom = tmp_path / "custom" / "credentials.json"
    monkeypatch.setenv("KOUSHARE_AUTH_FILE", str(custom))
    assert default_auth_path() == custom


def test_v2_video_authorization_and_playback_shape():
    access_session = Session({"code": 200000, "data": {"code": 200000, "secret": "s"}})
    client = KoushareClient(session=access_session)
    assert client.video_access("900002", ticket="ticket")["secret"] == "s"
    assert access_session.calls[0][1].endswith("/video/v1/video/checkVideoAuthV2")
    assert access_session.calls[0][2]["json"] == {"id": "900002", "ticket": "ticket"}

    playback_session = Session({"code": 200000, "data": [{"labelEn": "HD", "fileUrl": "https://x"}]})
    playback = KoushareClient(session=playback_session).video_playback_v2("900002", ticket="ticket")
    assert playback["playbackUrls"][0]["labelEn"] == "HD"
    assert playback_session.calls[0][2]["params"] == {"videoId": "900002", "ticket": "ticket"}
