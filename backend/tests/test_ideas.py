from test_content import _builtin_template


def test_generate_unique_ideas_and_accept(client, channel, character_with_art):
    ch = channel(topics=["study", "rain"], audio_style={"ambience": ["rain"], "music": "", "notes": ""})
    character_with_art(ch["id"])
    _builtin_template("study_with_me")
    r = client.post(f"/api/channels/{ch['id']}/ideas/generate", json={"count": 6})
    assert r.status_code == 201, r.text
    ideas = r.json()
    assert 1 <= len(ideas) <= 6
    types = {i["content_type"] for i in ideas}
    assert types <= {"study_with_me", "pomodoro", "reading_room", "rain_sounds", "cozy_ambience"}
    combos = {(i["content_type"], i["attributes"]["setting"], i["theme"], tuple(i["attributes"]["sounds"]),
               i["attributes"]["duration_minutes"]) for i in ideas}
    assert len(combos) == len(ideas)
    # a second batch never repeats an earlier combination
    more = client.post(f"/api/channels/{ch['id']}/ideas/generate", json={"count": 6}).json()
    combos2 = {(i["content_type"], i["attributes"]["setting"], i["theme"], tuple(i["attributes"]["sounds"]),
                i["attributes"]["duration_minutes"]) for i in more}
    assert not combos & combos2

    study = next((i for i in ideas + more if i["content_type"] == "study_with_me"), ideas[0])
    r = client.post(f"/api/channels/{ch['id']}/ideas/{study['id']}/accept")
    assert r.status_code == 201, r.text
    p = r.json()
    assert p["idea_id"] == study["id"] and p["character_name"] == "Momo"
    assert [l["generator"] for l in p["audio_layers"]] == study["attributes"]["sounds"]
    statuses = {i["id"]: i["status"] for i in client.get(f"/api/channels/{ch['id']}/ideas").json()}
    assert statuses[study["id"]] == "used"


def test_reject_and_isolation(client, channel):
    a, b = channel("chan-a", "Chan A"), channel("chan-b", "Chan B")
    idea = client.post(f"/api/channels/{a['id']}/ideas/generate", json={"count": 1}).json()[0]
    assert client.post(f"/api/channels/{b['id']}/ideas/{idea['id']}/reject").status_code == 404
    assert client.post(f"/api/channels/{a['id']}/ideas/{idea['id']}/reject").json()["status"] == "rejected"
