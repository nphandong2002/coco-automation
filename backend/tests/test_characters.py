import pytest
from sqlalchemy.exc import IntegrityError

from app.core.database import SessionLocal
from app.models import ContentProject
from app.models.enums import ContentType


def _char(client, cid, **kw):
    r = client.post(f"/api/channels/{cid}/characters", json={"name": "Momo", **kw})
    assert r.status_code == 201, r.text
    return r.json()


def test_create_character_with_initial_version(client, channel):
    ch = channel()
    c = _char(client, ch["id"], species="cat", appearance="small white cat, round glasses",
              primary_colors=["#ffd1dc", "#FFD1DC"], allowed_animations=["blink", "write"])
    assert c["is_owner"] and c["version_count"] == 1
    v = c["current_version"]
    assert v["version_no"] == 1 and v["primary_colors"] == ["#FFD1DC"]
    assert client.post(f"/api/channels/{ch['id']}/characters", json={"name": "Momo"}).status_code == 409
    bad = client.post(f"/api/channels/{ch['id']}/characters", json={"name": "X", "primary_colors": ["pink"]})
    assert bad.status_code == 422


def test_versions_are_immutable_and_rollback(client, channel):
    ch = channel()
    c = _char(client, ch["id"], appearance="white cat", outfit="hoodie")
    url = f"/api/channels/{ch['id']}/characters/{c['id']}"
    r = client.post(url + "/versions", json={"outfit": "winter scarf", "change_note": "Winter look"})
    assert r.status_code == 201
    cur = r.json()["current_version"]
    assert cur["version_no"] == 2 and cur["outfit"] == "winter scarf" and cur["appearance"] == "white cat"
    # no-op version rejected
    assert client.post(url + "/versions", json={"outfit": "winter scarf"}).status_code == 400
    versions = client.get(url + "/versions").json()
    assert [v["version_no"] for v in versions] == [2, 1]
    assert versions[1]["outfit"] == "hoodie"  # old version untouched
    v1 = versions[1]["id"]
    r = client.post(url + f"/versions/{v1}/activate")
    assert r.json()["current_version"]["version_no"] == 1
    # renaming does not create a version
    r = client.patch(url, json={"name": "Momo-chan"})
    assert r.json()["name"] == "Momo-chan" and r.json()["version_count"] == 2


def test_image_uploads_create_versions(client, channel, png):
    ch = channel()
    c = _char(client, ch["id"])
    url = f"/api/channels/{ch['id']}/characters/{c['id']}"
    r = client.post(url + "/images", data={"slot": "full_body"}, files={"file": ("f.png", png(), "image/png")})
    assert r.status_code == 201 and r.json()["current_version"]["full_body_url"]
    r = client.post(url + "/images", data={"slot": "reference"},
                    files={"file": ("r.png", png((1, 2, 3)), "image/png")})
    ref = r.json()["current_version"]["reference_images"][0]["path"]
    r = client.post(url + "/images", data={"slot": "expression", "expression_name": "Sleepy"},
                    files={"file": ("e.png", png((9, 9, 9)), "image/png")})
    cur = r.json()["current_version"]
    assert cur["version_no"] == 4 and cur["expressions"][0]["name"] == "sleepy"
    assert client.post(url + "/images", data={"slot": "expression"},
                       files={"file": ("e.png", png(), "image/png")}).status_code == 400
    r = client.delete(url + "/images", params={"slot": "reference", "key": ref})
    assert r.json()["current_version"]["reference_images"] == []
    assert r.json()["version_count"] == 5


def test_single_primary_per_channel(client, channel):
    ch = channel()
    a = _char(client, ch["id"], role="primary")
    b = _char(client, ch["id"], name="Bobo", role="primary")
    chars = {c["id"]: c for c in client.get(f"/api/channels/{ch['id']}/characters").json()}
    assert chars[b["id"]]["role"] == "primary" and chars[a["id"]]["role"] == "secondary"
    client.put(f"/api/channels/{ch['id']}/characters/{a['id']}/role", json={"role": "primary"})
    chars = {c["id"]: c for c in client.get(f"/api/channels/{ch['id']}/characters").json()}
    assert chars[a["id"]]["role"] == "primary" and chars[b["id"]]["role"] == "secondary"


def test_channel_isolation_and_grants(client, channel):
    a = channel()
    b = channel(code="rainy-night", name="Rainy Night")
    momo = _char(client, a["id"])
    # channel B cannot see or use Momo without a grant
    assert client.get(f"/api/channels/{b['id']}/characters").json() == []
    assert client.get(f"/api/channels/{b['id']}/characters/{momo['id']}").status_code == 404

    r = client.post(f"/api/channels/{a['id']}/characters/{momo['id']}/grants",
                    json={"target_channel_id": b["id"], "role": "secondary"})
    assert r.status_code == 201 and r.json()["shared_with"][0]["channel_id"] == b["id"]
    seen = client.get(f"/api/channels/{b['id']}/characters/{momo['id']}").json()
    assert seen["is_owner"] is False and seen["shared_with"] == []
    # grantee cannot modify the character
    assert client.patch(f"/api/channels/{b['id']}/characters/{momo['id']}",
                        json={"name": "Hacked"}).status_code == 403
    assert client.post(f"/api/channels/{b['id']}/characters/{momo['id']}/versions",
                       json={"outfit": "x"}).status_code == 403
    # but it can choose the role in its own channel
    r = client.put(f"/api/channels/{b['id']}/characters/{momo['id']}/role", json={"role": "primary"})
    assert r.json()["role"] == "primary"
    # duplicate grant / self grant
    assert client.post(f"/api/channels/{a['id']}/characters/{momo['id']}/grants",
                       json={"target_channel_id": b["id"]}).status_code == 409
    assert client.post(f"/api/channels/{a['id']}/characters/{momo['id']}/grants",
                       json={"target_channel_id": a["id"]}).status_code == 400
    # revoke
    r = client.delete(f"/api/channels/{a['id']}/characters/{momo['id']}/grants/{b['id']}")
    assert r.status_code == 200 and r.json()["shared_with"] == []
    assert client.get(f"/api/channels/{b['id']}/characters").json() == []


def test_db_blocks_content_using_ungranted_character(client, channel):
    """Composite FK: a content project can only reference a character linked to its channel."""
    a = channel()
    b = channel(code="rainy-night", name="Rainy Night")
    momo = _char(client, a["id"])
    with SessionLocal() as db:
        db.add(ContentProject(channel_id=b["id"], character_id=momo["id"], title="x",
                              content_type=ContentType.POMODORO))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
        # allowed for the owner channel, with a version that belongs to the character
        db.add(ContentProject(channel_id=a["id"], character_id=momo["id"],
                              character_version_id=momo["current_version"]["id"],
                              title="ok", content_type=ContentType.POMODORO))
        db.commit()
    # character used by content cannot be deleted
    r = client.delete(f"/api/channels/{a['id']}/characters/{momo['id']}")
    assert r.status_code == 409


def test_delete_character(client, channel):
    ch = channel()
    c = _char(client, ch["id"])
    assert client.delete(f"/api/channels/{ch['id']}/characters/{c['id']}").status_code == 204
    assert client.get(f"/api/channels/{ch['id']}/characters").json() == []


def test_global_character_list(client, channel):
    a = channel()
    b = channel(code="forest", name="Forest Ambience")
    _char(client, a["id"])
    _char(client, b["id"], name="Bobo")
    names = {c["name"]: c["owner_channel_name"] for c in client.get("/api/characters").json()}
    assert names == {"Momo": "Cozy Study", "Bobo": "Forest Ambience"}
