import json
from pathlib import Path

import koushare_cli.cli as cli


class FakeClient:
    def live_info(self, live_id):
        return {"title": "Physics Meeting", "startTime": "2026-09-18 09:00:00"}

    def live_playbacks(self, live_id):
        return [
            {"videoId": "101", "title": "First / Talk", "speakerName": "Alice"},
            {"videoId": "102", "title": "Second Talk", "speakerName": "Bob"},
        ]

    def live_playback(self, live_id, video_id, *, fastback=False):
        return {
            "playbackUrls": [
                {
                    "list": [
                        {
                            "labelEn": "FHD",
                            "height": 1080,
                            "fileUrl": f"https://cdn.example/{video_id}.m3u8?token=secret",
                        }
                    ]
                }
            ]
        }


def _install_fake(monkeypatch):
    monkeypatch.setattr(cli, "_client", lambda args: FakeClient())


def test_list_json_is_normalized_for_agents(monkeypatch, capsys):
    _install_fake(monkeypatch)
    assert cli.main(["list", "live:900001", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["live_id"] == "900001"
    assert data["videos"][0]["video_id"] == "101"
    assert data["videos"][0]["title"] == "First / Talk"


def test_plan_all_with_metadata_template(monkeypatch, capsys, tmp_path):
    _install_fake(monkeypatch)
    rc = cli.main(
        [
            "plan",
            "live:900001",
            "--all",
            "--dir",
            str(tmp_path),
            "--template",
            "{index:02d} - {speaker} - {title} [{video_id}]",
            "--json",
        ]
    )
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert data["ok"] is True
    assert data["items"][0]["path"].endswith("01 - Alice - First _ Talk [101].mp4")
    assert data["items"][1]["path"].endswith("02 - Bob - Second Talk [102].mp4")
    assert "token=secret" not in data["items"][0]["media_url"]


def test_download_dry_run_exact_path(monkeypatch, capsys, tmp_path):
    _install_fake(monkeypatch)
    target = tmp_path / "chosen-name.mp4"
    rc = cli.main(
        [
            "download",
            "live:900001",
            "--video-id",
            "101",
            "--path",
            str(target),
            "--dry-run",
            "--json",
        ]
    )
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert data["downloads"][0]["status"] == "dry-run"
    assert Path(data["downloads"][0]["path"]) == target.resolve()


def test_name_rejected_for_multiple_videos(monkeypatch, capsys):
    _install_fake(monkeypatch)
    rc = cli.main(["download", "live:900001", "--all", "--name", "same.mp4", "--dry-run", "--json"])
    assert rc == 2
    err = json.loads(capsys.readouterr().err)
    assert err["ok"] is False
    assert "exactly one" in err["error"]
