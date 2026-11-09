def test_create_list_get_channel(client, channel):
    ch = channel(topics=["Study", "study", " Rain "], publish_schedule={
        "timezone": "Asia/Bangkok", "slots": [{"weekday": 0, "time": "19:30"}]})
    assert ch["topics"] == ["Study", "Rain"]
    # brand-new channel without YouTube OAuth must be reported honestly
    assert ch["status"] == "disconnected"
    assert ch["youtube_connected"] is False
    assert len(client.get("/api/channels").json()) == 1
    assert client.get(f"/api/channels/{ch['id']}").json()["code"] == "cozy-study"


def test_duplicate_code_and_validation(client, channel):
    channel()
    r = client.post("/api/channels", json={"code": "cozy-study", "name": "Other"})
    assert r.status_code == 409
    r = client.post("/api/channels", json={"code": "Bad Code!", "name": "X1"})
    assert r.status_code == 422
    r = client.post("/api/channels", json={"code": "ok-code", "name": "X1",
                                           "publish_schedule": {"timezone": "Mars/Base", "slots": []}})
    assert r.status_code == 422
    r = client.post("/api/channels", json={"code": "ok-code", "name": "X1",
                                           "publish_schedule": {"slots": [{"weekday": 9, "time": "25:00"}]}})
    assert r.status_code == 422


def test_update_pause_enable(client, channel):
    ch = channel()
    r = client.patch(f"/api/channels/{ch['id']}", json={"description": "Lo-fi study", "language": "vi"})
    assert r.json()["description"] == "Lo-fi study" and r.json()["language"] == "vi"
    assert client.post(f"/api/channels/{ch['id']}/pause").json()["status"] == "paused"
    assert client.post(f"/api/channels/{ch['id']}/enable").json()["status"] == "disconnected"


def test_delete_requires_confirmation(client, channel):
    ch = channel()
    assert client.delete(f"/api/channels/{ch['id']}", params={"confirm": "wrong"}).status_code == 409
    assert client.delete(f"/api/channels/{ch['id']}", params={"confirm": "cozy-study"}).status_code == 204
    assert client.get(f"/api/channels/{ch['id']}").status_code == 404


def test_brand_images(client, channel, png):
    ch = channel()
    r = client.post(f"/api/channels/{ch['id']}/avatar", files={"file": ("a.png", png(), "image/png")})
    assert r.status_code == 200 and r.json()["avatar_url"].startswith("/media/channels/")
    assert client.get(r.json()["avatar_url"]).status_code == 200
    r = client.post(f"/api/channels/{ch['id']}/banner", files={"file": ("x.txt", b"not image", "text/plain")})
    assert r.status_code == 400


def test_clone_channel_copies_config_and_owned_characters_only(client, channel, png):
    a = channel(topics=["study"], visual_style={"theme": "pastel", "palette": ["#FFEEDD"]})
    b = channel(code="rainy-night", name="Rainy Night")
    momo = client.post(f"/api/channels/{a['id']}/characters",
                       json={"name": "Momo", "role": "primary", "appearance": "white cat"}).json()
    client.post(f"/api/channels/{a['id']}/characters/{momo['id']}/images",
                data={"slot": "avatar"}, files={"file": ("m.png", png(), "image/png")})
    luna = client.post(f"/api/channels/{b['id']}/characters", json={"name": "Luna"}).json()
    client.post(f"/api/channels/{b['id']}/characters/{luna['id']}/grants",
                json={"target_channel_id": a["id"]})

    r = client.post(f"/api/channels/{a['id']}/clone",
                    json={"name": "Cozy Study JP", "code": "cozy-study-jp"})
    assert r.status_code == 201, r.text
    clone = r.json()
    assert clone["visual_style"]["theme"] == "pastel" and clone["cloned_from_id"] == a["id"]
    assert clone["youtube_connected"] is False
    chars = client.get(f"/api/channels/{clone['id']}/characters").json()
    assert [c["name"] for c in chars] == ["Momo"]  # granted Luna is NOT copied
    cloned_momo = chars[0]
    assert cloned_momo["id"] != momo["id"] and cloned_momo["is_owner"] and cloned_momo["role"] == "primary"
    assert cloned_momo["current_version"]["appearance"] == "white cat"
    assert f"/channels/{clone['id']}/" in cloned_momo["current_version"]["avatar_url"]


def test_overview_reports_not_synced_instead_of_fake_numbers(client, channel):
    channel()
    ov = client.get("/api/overview").json()
    assert ov["channels_total"] == 1
    assert ov["channels_by_status"]["disconnected"] == 1
    assert ov["total_views"] == {"value": None, "source": "not_synced", "synced_at": None}
    assert ov["daily_views"] == []
    assert ov["recent_activity"][0]["message"].startswith("Tạo kênh")


def test_system_info(client):
    info = client.get("/api/system/info").json()
    assert info["database_ok"] is True and info["secret_key_configured"] is True
