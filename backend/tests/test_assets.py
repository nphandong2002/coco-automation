import pytest

from conftest import has_ffmpeg, make_png, make_wav


def test_upload_image_license_rules(client, channel, upload_asset):
    ch = channel()
    # non-owned licence needs a source
    r = upload_asset(make_png(), "bg.png", ch["id"], license_type="royalty_free")
    assert r.status_code == 400 and "nguồn" in r.json()["detail"]
    # CC BY needs an attribution line
    r = upload_asset(make_png(), "bg.png", ch["id"], license_type="cc_by", license_source="https://example.org/x")
    assert r.status_code == 400 and "attribution" in r.json()["detail"]
    r = upload_asset(make_png(), "bg.png", ch["id"], license_type="cc_by",
                     license_source="https://example.org/x", attribution="Photo by A (CC BY 4.0)", tags="Rain, night")
    assert r.status_code == 201, r.text
    a = r.json()
    assert a["kind"] == "image" and a["width"] == 64 and a["channel_id"] == ch["id"]
    assert a["tags"] == ["rain", "night"] and a["url"].startswith("/media/channels/")
    # same file again in the same scope → duplicate
    r = upload_asset(make_png(), "again.png", ch["id"], license_type="owned")
    assert r.status_code == 409


def test_reject_bad_files(client, channel, upload_asset):
    ch = channel()
    assert upload_asset(b"hello", "x.exe", ch["id"]).status_code == 400
    assert upload_asset(b"not an image", "fake.png", ch["id"]).status_code == 400


def test_scopes_and_listing(client, channel, upload_asset, background):
    a, b = channel("chan-a", "Chan A"), channel("chan-b", "Chan B")
    upload_asset(make_png((10, 20, 30)), "a.png", a["id"])
    upload_asset(make_png((40, 50, 60)), "shared.png", None)
    upload_asset(make_png((70, 80, 90)), "b.png", b["id"])
    usable_a = client.get(f"/api/channels/{a['id']}/assets").json()
    names = sorted(x["name"] for x in usable_a)
    assert names == ["a", "shared"]           # never channel B's asset
    assert len(client.get("/api/assets", params={"scope": "shared"}).json()) == 1
    assert len(client.get("/api/assets").json()) == 3


def test_generate_background_uses_channel_palette(client, channel, background):
    ch = channel(visual_style={"theme": "cozy", "mood": "", "palette": ["#112233", "#AA8844"], "keywords": []})
    a = background(ch["id"], style="rainy_window", seed=42)
    assert a["source"] == "generated" and a["license_type"] == "owned"
    assert a["meta"]["palette"] == ["#112233", "#AA8844"] and a["width"] == 1920
    # same seed + palette → identical file → same asset returned
    again = background(ch["id"], style="rainy_window", seed=42)
    assert again["id"] == a["id"]
    r = client.post("/api/assets/generate-background", json={"style": "nope"})
    assert r.status_code == 400


def test_update_and_delete_asset(client, channel, upload_asset):
    ch = channel()
    a = upload_asset(make_png(), "bg.png", ch["id"]).json()
    r = client.patch(f"/api/assets/{a['id']}", json={"name": "Cozy room", "license_type": "licensed"})
    assert r.status_code == 400          # licensed without source
    r = client.patch(f"/api/assets/{a['id']}", json={"name": "Cozy room", "license_type": "licensed",
                                                    "license_source": "Bought on store X, order 123"})
    assert r.status_code == 200 and r.json()["name"] == "Cozy room"
    assert client.delete(f"/api/assets/{a['id']}").status_code == 204
    assert client.get(f"/api/assets/{a['id']}").status_code == 404


@pytest.mark.skipif(not has_ffmpeg(), reason="ffmpeg not available")
def test_upload_audio_is_probed(client, channel, upload_asset):
    ch = channel()
    r = upload_asset(make_wav(2.0), "rain.wav", ch["id"], license_type="cc0", license_source="freesound #1")
    assert r.status_code == 201, r.text
    a = r.json()
    assert a["kind"] == "audio" and abs(a["duration_sec"] - 2.0) < 0.1
    assert a["meta"]["audio"]["sample_rate"] == 22050
    # garbage with an audio extension is rejected and not kept on disk
    r = upload_asset(b"\x00" * 2048, "broken.mp3", ch["id"])
    assert r.status_code == 400
