"""YouTube metadata generation (title ≤ 100, description ≤ 5000, tags ≤ 500 chars).

Built from the project's real configuration: duration, Pomodoro settings, chapters,
sounds and the licence attributions of every asset used (CC BY requires credit).
"""
from __future__ import annotations

from app.render.audio import GENERATORS

TYPE_LABELS = {
    "en": {
        "study_with_me": "Study With Me", "pomodoro": "Pomodoro Timer", "cozy_ambience": "Cozy Ambience",
        "rain_sounds": "Rain Sounds", "fireplace_sounds": "Fireplace Sounds", "sleep_ambience": "Sleep Ambience",
        "reading_room": "Reading Room Ambience", "cafe_ambience": "Café Ambience",
        "nature_ambience": "Nature Ambience",
    },
    "vi": {
        "study_with_me": "Học Cùng Mình", "pomodoro": "Pomodoro", "cozy_ambience": "Không Gian Ấm Áp",
        "rain_sounds": "Tiếng Mưa", "fireplace_sounds": "Tiếng Lò Sưởi", "sleep_ambience": "Âm Thanh Ngủ Ngon",
        "reading_room": "Phòng Đọc Sách", "cafe_ambience": "Không Gian Quán Cà Phê",
        "nature_ambience": "Âm Thanh Thiên Nhiên",
    },
}

T = {
    "en": {"hour": "Hour", "hours": "Hours", "min": "Minutes", "chapters": "Chapters",
           "sounds": "Sounds", "credits": "Credits", "pomodoro": "Pomodoro",
           "focus": "focus", "break": "break", "long": "long break every",
           "made": "Visuals & sound design made for this channel.",
           "intro": "Relax, focus and stay productive with this {label} video{setting}.",
           "with": " with {character}"},
    "vi": {"hour": "Giờ", "hours": "Giờ", "min": "Phút", "chapters": "Mốc thời gian",
           "sounds": "Âm thanh", "credits": "Ghi nguồn", "pomodoro": "Pomodoro",
           "focus": "tập trung", "break": "nghỉ", "long": "nghỉ dài sau mỗi",
           "made": "Hình ảnh & âm thanh được thực hiện riêng cho kênh.",
           "intro": "Thư giãn, tập trung và làm việc hiệu quả cùng video {label}{setting}.",
           "with": " cùng {character}"},
}


def duration_label(minutes: int, lang: str = "en") -> str:
    t = T.get(lang, T["en"])
    if minutes % 60 == 0:
        h = minutes // 60
        return f"{h} {t['hour'] if h == 1 else t['hours']}"
    return f"{minutes} {t['min']}"


def _cap(s: str) -> str:
    return " ".join(w[:1].upper() + w[1:] for w in s.split())


def make_title(content_type: str, duration_min: int, setting: str, theme: str,
               pomodoro: dict | None, lang: str = "en", character: str | None = None) -> str:
    label = TYPE_LABELS.get(lang, TYPE_LABELS["en"]).get(content_type, content_type)
    parts = [duration_label(duration_min, lang), label]
    scene = " ".join(x for x in (_cap(theme), _cap(setting)) if x)
    title = " ".join(parts)
    if scene:
        title += f" | {scene}"
    if pomodoro and pomodoro.get("focus_min"):
        title += f" | {pomodoro['focus_min']}/{pomodoro.get('short_break_min', 5)}"
    if character and len(title) + len(character) + 3 <= 100:
        title += f" · {character}"
    return title[:100].rstrip(" |·")


def make_tags(content_type: str, setting: str, theme: str, base_tags: list[str], topics: list[str],
              sounds: list[str], lang: str = "en") -> list[str]:
    label = TYPE_LABELS.get(lang, TYPE_LABELS["en"]).get(content_type, content_type)
    raw = [label, *base_tags, *topics, setting, theme, *sounds, "ambience", "relaxing", "focus music"]
    tags, seen, total = [], set(), 0
    for t in raw:
        t = (t or "").strip().replace("<", "").replace(">", "")
        if not t or t.lower() in seen or len(t) > 100:
            continue
        cost = len(t) + (2 if " " in t else 0) + (1 if tags else 0)   # YouTube counts quotes + commas
        if total + cost > 480:
            break
        tags.append(t)
        seen.add(t.lower())
        total += cost
    return tags


def make_description(*, content_type: str, duration_min: int, setting: str, theme: str,
                     pomodoro: dict | None, chapters: list[dict], sounds: list[str],
                     attributions: list[str], channel_description: str = "", lang: str = "en",
                     character: str | None = None, script: str = "") -> str:
    t = T.get(lang, T["en"])
    label = TYPE_LABELS.get(lang, TYPE_LABELS["en"]).get(content_type, content_type)
    scene = " ".join(x for x in (theme, setting) if x)
    setting_txt = (f" — {scene}" if scene else "") + (t["with"].format(character=character) if character else "")
    lines = [t["intro"].format(label=label, setting=setting_txt), ""]
    if script.strip():
        lines += [script.strip()[:800], ""]
    if pomodoro and pomodoro.get("focus_min"):
        lines.append(f"⏱ {t['pomodoro']}: {pomodoro['focus_min']} min {t['focus']} / "
                     f"{pomodoro.get('short_break_min', 5)} min {t['break']}"
                     + (f", {pomodoro.get('long_break_min')} min {t['long']} {pomodoro.get('cycles_before_long')}"
                        if pomodoro.get("long_break_min") and pomodoro.get("cycles_before_long") else ""))
        lines.append("")
    if sounds:
        lines += [f"🎧 {t['sounds']}: " + ", ".join(sounds), ""]
    if chapters:
        lines.append(f"📌 {t['chapters']}:")
        lines += [f"{c['timestamp']} {c['title']}" for c in chapters]
        lines.append("")
    if attributions:
        lines.append(f"© {t['credits']}:")
        lines += [f"- {a}" for a in attributions]
        lines.append("")
    if channel_description.strip():
        lines += [channel_description.strip()[:600], ""]
    lines.append(t["made"])
    text = "\n".join(lines).replace("<", "").replace(">", "")
    return text[:5000]


def sound_names(layers: list[dict], asset_names: dict[int, str], lang: str = "en") -> list[str]:
    out = []
    key = "label" if lang == "vi" else "en"
    for l in layers:
        if l.get("kind") == "generator":
            out.append(GENERATORS.get(l.get("generator"), {}).get(key, l.get("generator", "")))
        elif l.get("asset_id") in asset_names:
            out.append(asset_names[l["asset_id"]])
    return [s for s in out if s]
