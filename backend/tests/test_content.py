from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import Video, VideoTemplate
from conftest import make_png

GEN_RAIN = [{"kind": "generator", "generator": "rain", "volume": 0.7}]


def _project(client, cid, **kw):
    body = {"title": "Rainy study", "content_type": "study_with_me", "duration_minutes": 120,
            "audio_layers": GEN_RAIN, **kw}
    return client.post(f"/api/channels/{cid}/content", json=body)


def _builtin_template(content_type="pomodoro") -> int:
    """Tests use create_all (no migration seed): add the same kind of built-in template."""
    with SessionLocal() as db:
        t = VideoTemplate(channel_id=None, name="Pomodoro 25/5", content_type=content_type, config={
            "builtin": True, "duration_minutes": 120,
            "animation": {"background_motion": "slow_zoom", "effects": ["vignette"],
                          "character": {"position": "bottom_right", "scale": 0.42, "motion": "bob"}},
            "audio_layers": [{"kind": "generator", "generator": "rain", "volume": 0.4}],
            "pomodoro": {"focus_min": 25, "short_break_min": 5, "long_break_min": 15, "cycles_before_long": 4},
            "render_settings": {"overlay": {"mode": "pomodoro", "position": "top_center"}, "chime": True},
            "tags": ["pomodoro"]})
        db.add(t)
        db.commit()
        return t.id


def test_create_from_template_merges_defaults(client, channel, background):
    ch = channel()
    tpl = _builtin_template()
    bg = background(ch["id"])
    r = client.post(f"/api/channels/{ch['id']}/content", json={
        "title": "Pomodoro night", "content_type": "pomodoro", "template_id": tpl,
        "background_asset_id": bg["id"], "setting": "attic"})
    assert r.status_code == 201, r.text
    p = r.json()
    assert p["pomodoro"]["focus_min"] == 25 and p["render_settings"]["overlay"]["mode"] == "pomodoro"
    assert p["audio_layers"][0]["generator"] == "rain" and p["youtube_tags"] == ["pomodoro"]
    assert p["status"] == "draft" and p["fingerprint"]
    assert len(client.get("/api/content").json()) == 1


def test_duplicate_only_title_changed_is_blocked(client, channel):
    ch = channel()
    assert _project(client, ch["id"]).status_code == 201
    r = _project(client, ch["id"], title="Rainy study v2", youtube_title="Different title")
    assert r.status_code == 409 and "trùng" in r.json()["detail"]
    # a real change (setting) makes it a different video
    assert _project(client, ch["id"], title="Rainy study v2", setting="library").status_code == 201
    # same config in ANOTHER channel is that channel's own business
    other = channel("other-ch", "Other")
    assert _project(client, other["id"]).status_code == 201


def test_character_isolation_and_version_pinning(client, channel, character_with_art):
    a, b = channel("chan-a", "Chan A"), channel("chan-b", "Chan B")
    momo = character_with_art(a["id"])
    # channel B cannot use A's character without a grant
    r = _project(client, b["id"], character_id=momo["id"])
    assert r.status_code == 404
    client.post(f"/api/channels/{a['id']}/characters/{momo['id']}/grants",
                json={"target_channel_id": b["id"], "role": "secondary"})
    r = _project(client, b["id"], character_id=momo["id"])
    assert r.status_code == 201, r.text
    p = r.json()
    pinned = p["character_version_id"]
    assert p["character_version_no"] == 2      # v1 = created, v2 = full-body image
    # owner changes the character → project keeps its pinned version
    client.post(f"/api/channels/{a['id']}/characters/{momo['id']}/versions",
                json={"outfit": "red scarf", "change_note": "winter"})
    p = client.get(f"/api/channels/{b['id']}/content/{p['id']}").json()
    assert p["character_version_id"] == pinned and p["character_current_version_id"] != pinned
    r = client.post(f"/api/channels/{b['id']}/content/{p['id']}/character/sync-version")
    assert r.status_code == 200 and r.json()["character_version_no"] == 3


def test_asset_isolation(client, channel, upload_asset):
    a, b = channel("chan-a", "Chan A"), channel("chan-b", "Chan B")
    bg_a = upload_asset(make_png(), "a.png", a["id"]).json()
    assert _project(client, b["id"], background_asset_id=bg_a["id"]).status_code == 404
    # audio layer must reference an AUDIO asset
    r = _project(client, a["id"], audio_layers=[{"kind": "asset", "asset_id": bg_a["id"], "volume": 1}])
    assert r.status_code == 400


def test_validation_report_and_ready(client, channel, background):
    ch = channel()
    p = _project(client, ch["id"]).json()
    rep = client.get(f"/api/channels/{ch['id']}/content/{p['id']}/validate").json()
    assert not rep["ok"] and any("hình nền" in e for e in rep["errors"])
    assert client.post(f"/api/channels/{ch['id']}/content/{p['id']}/ready").status_code == 400
    bg = background(ch["id"])
    client.patch(f"/api/channels/{ch['id']}/content/{p['id']}", json={"background_asset_id": bg["id"]})
    rep = client.get(f"/api/channels/{ch['id']}/content/{p['id']}/validate").json()
    assert rep["ok"], rep
    r = client.post(f"/api/channels/{ch['id']}/content/{p['id']}/ready")
    assert r.status_code == 200 and r.json()["status"] == "ready"
    # render-affecting edit sends it back to draft; metadata edit does not
    r = client.patch(f"/api/channels/{ch['id']}/content/{p['id']}", json={"youtube_title": "New"})
    assert r.json()["status"] == "ready"
    r = client.patch(f"/api/channels/{ch['id']}/content/{p['id']}", json={"setting": "café"})
    assert r.json()["status"] == "draft"


def test_pomodoro_overlay_requires_config(client, channel, background):
    ch = channel()
    bg = background(ch["id"])
    p = _project(client, ch["id"], background_asset_id=bg["id"],
                 render_settings={"overlay": {"mode": "pomodoro"}}).json()
    rep = client.get(f"/api/channels/{ch['id']}/content/{p['id']}/validate").json()
    assert any("Pomodoro" in e for e in rep["errors"])


def test_metadata_generation(client, channel, background, upload_asset):
    ch = channel(language="en", topics=["study", "rain"], description="Cozy study music channel")
    tpl = _builtin_template()
    credited = upload_asset(make_png((1, 2, 3)), "lofi-room.png", ch["id"], license_type="cc_by",
                            license_source="https://example.org/room", attribution="Room art by Jane (CC BY 4.0)").json()
    r = client.post(f"/api/channels/{ch['id']}/content", json={
        "title": "Night pomodoro", "content_type": "pomodoro", "template_id": tpl, "background_asset_id": credited["id"],
        "setting": "attic room", "theme": "rainy night"})
    p = r.json()
    m = client.post(f"/api/channels/{ch['id']}/content/{p['id']}/metadata/generate").json()
    assert m["applied"] and len(m["youtube_title"]) <= 100
    assert m["youtube_title"].startswith("2 Hours Pomodoro Timer")
    assert "0:00 Focus 1/" in m["youtube_description"].replace("00:00", "0:00")
    assert "Room art by Jane (CC BY 4.0)" in m["youtube_description"]   # licence credit
    assert sum(len(t) for t in m["youtube_tags"]) <= 500 and "pomodoro" in [t.lower() for t in m["youtube_tags"]]
    saved = client.get(f"/api/channels/{ch['id']}/content/{p['id']}").json()
    assert saved["youtube_title"] == m["youtube_title"]


def test_thumbnail_generate_and_upload(client, channel, background, character_with_art):
    ch = channel()
    char = character_with_art(ch["id"])
    bg = background(ch["id"])
    p = _project(client, ch["id"], background_asset_id=bg["id"], character_id=char["id"]).json()
    r = client.post(f"/api/channels/{ch['id']}/content/{p['id']}/thumbnail/generate")
    assert r.status_code == 200 and r.json()["thumbnail_url"].endswith(".jpg")
    small = make_png(size=(320, 180))
    r = client.post(f"/api/channels/{ch['id']}/content/{p['id']}/thumbnail", files={"file": ("t.png", small)})
    assert r.status_code == 400                # too small for YouTube
    r = client.post(f"/api/channels/{ch['id']}/content/{p['id']}/thumbnail",
                    files={"file": ("t.png", make_png(size=(1280, 720)))})
    assert r.status_code == 200


def test_delete_project_keeps_videos_and_channel_delete_cascades(client, channel, background):
    ch = channel()
    bg = background(ch["id"])
    p = _project(client, ch["id"], background_asset_id=bg["id"]).json()
    with SessionLocal() as db:
        db.add(Video(channel_id=ch["id"], content_project_id=p["id"], title="v", file_path="x.mp4",
                     duration_sec=10, width=1920, height=1080, fps=30, size_bytes=1))
        db.commit()
    assert client.delete(f"/api/channels/{ch['id']}/content/{p['id']}").status_code == 204
    with SessionLocal() as db:
        v = db.scalar(select(Video))
        assert v is not None and v.content_project_id is None
    # channel deletion with content + videos must work (composite FKs)
    p2 = _project(client, ch["id"], background_asset_id=bg["id"], setting="b").json()
    with SessionLocal() as db:
        db.add(Video(channel_id=ch["id"], content_project_id=p2["id"], title="v2", file_path="y.mp4",
                     duration_sec=10, width=1920, height=1080, fps=30, size_bytes=1))
        db.commit()
    assert client.delete(f"/api/channels/{ch['id']}", params={"confirm": ch["code"]}).status_code == 204


def test_templates_crud_and_save_from_project(client, channel):
    ch = channel()
    r = client.post("/api/templates", json={"name": "Mine", "content_type": "rain_sounds", "channel_id": ch["id"],
                                            "config": {"duration_minutes": 45}})
    assert r.status_code == 400                # 45 is not an allowed duration
    r = client.post("/api/templates", json={"name": "Mine", "content_type": "rain_sounds", "channel_id": ch["id"],
                                            "config": {"duration_minutes": 240,
                                                       "audio_layers": [{"kind": "generator", "generator": "rain"}]}})
    assert r.status_code == 201
    p = _project(client, ch["id"]).json()
    r = client.post(f"/api/channels/{ch['id']}/content/{p['id']}/save-template", json={"name": "From project"})
    assert r.status_code == 201 and r.json()["config"]["duration_minutes"] == 120
    other = channel("other-ch", "Other")
    names = [t["name"] for t in client.get("/api/templates", params={"channel_id": other["id"]}).json()]
    assert "Mine" not in names                 # channel templates are private to the channel
