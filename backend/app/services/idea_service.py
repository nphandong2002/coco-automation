"""Video idea generator (rule-based, offline, per channel).

An idea is a combination of concrete production choices — content type, setting, time of day,
weather/season, sound mix and duration — derived from the channel's topics, audio style and
its characters' usual settings. Each combination has a fingerprint; UNIQUE(channel_id,
fingerprint) guarantees the generator never proposes the same video twice with a new title.
"""
from __future__ import annotations

import hashlib
import itertools
import json
import random

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Asset, Channel, ChannelCharacter, Character, ContentIdea, ContentProject, VideoTemplate
from app.models.enums import AssetKind, CharacterRole, ContentType, IdeaStatus
from app.render.metadata import TYPE_LABELS, duration_label
from app.schemas.content import ContentCreate, IdeaOut
from app.services import activity
from app.services.errors import AppError, NotFound

CT = ContentType
KEYWORDS: dict[str, tuple[ContentType, ...]] = {
    "study": (CT.STUDY_WITH_ME, CT.POMODORO, CT.READING_ROOM), "học": (CT.STUDY_WITH_ME, CT.POMODORO),
    "focus": (CT.STUDY_WITH_ME, CT.POMODORO), "work": (CT.POMODORO, CT.CAFE_AMBIENCE),
    "pomodoro": (CT.POMODORO,), "rain": (CT.RAIN_SOUNDS, CT.COZY_AMBIENCE), "mưa": (CT.RAIN_SOUNDS,),
    "fire": (CT.FIREPLACE_SOUNDS, CT.COZY_AMBIENCE), "lò sưởi": (CT.FIREPLACE_SOUNDS,),
    "sleep": (CT.SLEEP_AMBIENCE,), "ngủ": (CT.SLEEP_AMBIENCE,), "night": (CT.SLEEP_AMBIENCE, CT.RAIN_SOUNDS),
    "read": (CT.READING_ROOM,), "book": (CT.READING_ROOM,), "đọc": (CT.READING_ROOM,),
    "library": (CT.READING_ROOM, CT.STUDY_WITH_ME), "thư viện": (CT.READING_ROOM,),
    "cafe": (CT.CAFE_AMBIENCE,), "café": (CT.CAFE_AMBIENCE,), "coffee": (CT.CAFE_AMBIENCE,),
    "cà phê": (CT.CAFE_AMBIENCE,), "forest": (CT.NATURE_AMBIENCE,), "nature": (CT.NATURE_AMBIENCE,),
    "rừng": (CT.NATURE_AMBIENCE,), "suối": (CT.NATURE_AMBIENCE,), "river": (CT.NATURE_AMBIENCE,),
    "cozy": (CT.COZY_AMBIENCE,), "ấm": (CT.COZY_AMBIENCE,), "asmr": (CT.COZY_AMBIENCE, CT.SLEEP_AMBIENCE),
}

SETTINGS: dict[ContentType, list[str]] = {
    CT.STUDY_WITH_ME: ["cozy bedroom desk", "attic study room", "library corner", "window seat", "dorm room",
                       "greenhouse desk"],
    CT.POMODORO: ["minimal desk setup", "cozy bedroom desk", "attic study room", "library corner", "window seat"],
    CT.COZY_AMBIENCE: ["cabin living room", "cozy bedroom", "reading nook", "winter cottage", "tea room"],
    CT.RAIN_SOUNDS: ["rainy window", "city apartment", "train window", "camping tent", "forest cabin porch"],
    CT.FIREPLACE_SOUNDS: ["stone fireplace", "log cabin", "winter lodge", "cottage living room"],
    CT.SLEEP_AMBIENCE: ["dim bedroom", "night sky window", "moonlit cabin", "quiet attic"],
    CT.READING_ROOM: ["old library", "bookstore loft", "reading nook", "study hall"],
    CT.CAFE_AMBIENCE: ["corner café", "rainy café window", "bakery café", "jazz café", "night café"],
    CT.NATURE_AMBIENCE: ["forest stream", "mountain lake", "bamboo grove", "meadow at dawn", "riverside"],
}
TIMES = ["early morning", "afternoon", "golden hour", "evening", "late night"]
WEATHER: dict[ContentType, list[str]] = {
    CT.RAIN_SOUNDS: ["rainy", "thunderstorm", "drizzle"],
    CT.FIREPLACE_SOUNDS: ["snowy", "winter", "autumn"],
    CT.NATURE_AMBIENCE: ["spring", "summer", "autumn", "foggy"],
    CT.SLEEP_AMBIENCE: ["rainy", "calm", "snowy"],
}
DEFAULT_WEATHER = ["rainy", "snowy", "autumn", "spring", "calm"]
MIXES: dict[ContentType, list[list[str]]] = {
    CT.STUDY_WITH_ME: [["rain"], ["rain", "room_tone"], ["brown_noise"], ["fireplace", "rain"], ["room_tone"]],
    CT.POMODORO: [["rain"], ["brown_noise"], ["rain", "room_tone"], ["fireplace", "rain"]],
    CT.COZY_AMBIENCE: [["fireplace", "rain"], ["fireplace"], ["rain", "wind"], ["fireplace", "wind"]],
    CT.RAIN_SOUNDS: [["rain"], ["rain", "heavy_rain"], ["heavy_rain", "wind"], ["rain", "night_crickets"]],
    CT.FIREPLACE_SOUNDS: [["fireplace"], ["fireplace", "wind"], ["fireplace", "rain"]],
    CT.SLEEP_AMBIENCE: [["brown_noise"], ["brown_noise", "rain"], ["pink_noise"], ["ocean"], ["rain", "wind"]],
    CT.READING_ROOM: [["fireplace", "rain"], ["room_tone", "rain"], ["room_tone", "fireplace"]],
    CT.CAFE_AMBIENCE: [["room_tone"], ["room_tone", "rain"]],
    CT.NATURE_AMBIENCE: [["stream", "wind"], ["stream"], ["wind", "night_crickets"], ["ocean", "wind"]],
}
DURATIONS: dict[ContentType, list[int]] = {
    CT.STUDY_WITH_ME: [120, 240], CT.POMODORO: [120, 240], CT.COZY_AMBIENCE: [60, 120],
    CT.RAIN_SOUNDS: [120, 240, 480], CT.FIREPLACE_SOUNDS: [120, 240], CT.SLEEP_AMBIENCE: [480, 360],
    CT.READING_ROOM: [120], CT.CAFE_AMBIENCE: [120, 60], CT.NATURE_AMBIENCE: [120, 240],
}
VI = {
    "early morning": "sáng sớm", "afternoon": "buổi chiều", "golden hour": "hoàng hôn", "evening": "buổi tối",
    "late night": "đêm khuya", "rainy": "mưa", "thunderstorm": "giông bão", "drizzle": "mưa phùn",
    "snowy": "tuyết rơi", "winter": "mùa đông", "autumn": "mùa thu", "spring": "mùa xuân", "summer": "mùa hè",
    "foggy": "sương mù", "calm": "yên tĩnh",
    "cozy bedroom desk": "góc học trong phòng ngủ", "attic study room": "phòng học gác mái",
    "library corner": "góc thư viện", "window seat": "ghế cạnh cửa sổ", "dorm room": "phòng ký túc xá",
    "greenhouse desk": "bàn học trong nhà kính", "minimal desk setup": "góc làm việc tối giản",
    "cabin living room": "phòng khách nhà gỗ", "cozy bedroom": "phòng ngủ ấm áp", "reading nook": "góc đọc sách",
    "winter cottage": "nhà nhỏ mùa đông", "tea room": "phòng trà", "rainy window": "cửa sổ mưa",
    "city apartment": "căn hộ thành phố", "train window": "cửa sổ tàu hỏa", "camping tent": "lều cắm trại",
    "forest cabin porch": "hiên nhà gỗ trong rừng", "stone fireplace": "lò sưởi đá", "log cabin": "nhà gỗ",
    "winter lodge": "nhà nghỉ mùa đông", "cottage living room": "phòng khách nhà vườn",
    "dim bedroom": "phòng ngủ ánh đèn mờ", "night sky window": "cửa sổ bầu trời đêm",
    "moonlit cabin": "nhà gỗ dưới trăng", "quiet attic": "gác mái yên tĩnh", "old library": "thư viện cổ",
    "bookstore loft": "gác hiệu sách", "study hall": "phòng tự học", "corner café": "quán cà phê góc phố",
    "rainy café window": "cửa sổ quán cà phê ngày mưa", "bakery café": "tiệm bánh cà phê",
    "jazz café": "quán cà phê jazz", "night café": "quán cà phê đêm", "forest stream": "suối trong rừng",
    "mountain lake": "hồ trên núi", "bamboo grove": "rừng tre", "meadow at dawn": "đồng cỏ lúc bình minh",
    "riverside": "bờ sông",
}


def _vi(s: str) -> str:
    return VI.get(s, s)


def idea_out(i: ContentIdea) -> IdeaOut:
    return IdeaOut(id=i.id, channel_id=i.channel_id, title=i.title, content_type=i.content_type, theme=i.theme,
                   description=i.description, attributes=i.attributes, status=i.status, created_at=i.created_at)


def fingerprint(ct: str, setting: str, time_of_day: str, weather: str, sounds: list[str], duration: int) -> str:
    payload = [ct, setting.lower(), time_of_day, weather, sorted(sounds), duration]
    return hashlib.sha256(json.dumps(payload).encode()).hexdigest()


def _channel_types(ch: Channel, wanted: ContentType | None) -> list[ContentType]:
    if wanted is not None:
        return [wanted]
    text = " ".join([*ch.topics, ch.description or "", *(ch.visual_style or {}).get("keywords", []),
                     *(ch.audio_style or {}).get("ambience", [])]).lower()
    types: list[ContentType] = []
    for kw, cts in KEYWORDS.items():
        if kw in text:
            types += [c for c in cts if c not in types]
    return types or list(ContentType)


def _character_settings(db: Session, channel_id: int) -> list[str]:
    rows = db.scalars(select(Character).join(ChannelCharacter, ChannelCharacter.character_id == Character.id)
                      .where(ChannelCharacter.channel_id == channel_id)).all()
    out: list[str] = []
    for c in rows:
        if c.current_version:
            out += [s for s in c.current_version.usual_settings if s]
    return out


def _title(lang: str, ct: ContentType, duration: int, setting: str, time_of_day: str, weather: str) -> str:
    label = TYPE_LABELS.get(lang, TYPE_LABELS["en"])[ct.value]
    if lang == "vi":
        return f"{duration_label(duration, 'vi')} {label} — {_vi(setting)}, {_vi(time_of_day)} {_vi(weather)}"[:200]
    scene = f"{weather.title()} {time_of_day.title()} in a {setting.title()}" if weather != "calm" \
        else f"Calm {time_of_day.title()} in a {setting.title()}"
    return f"{duration_label(duration, 'en')} {label} — {scene}"[:200]


def generate(db: Session, ch: Channel, count: int = 5, content_type: ContentType | None = None) -> list[IdeaOut]:
    lang = "vi" if (ch.language or "en").lower().startswith("vi") else "en"
    existing = set(db.scalars(select(ContentIdea.fingerprint).where(ContentIdea.channel_id == ch.id)).all())
    project_keys = {(p.content_type.value, (p.setting or "").lower(), (p.theme or "").lower())
                    for p in db.scalars(select(ContentProject).where(ContentProject.channel_id == ch.id)).all()}
    ambience = " ".join((ch.audio_style or {}).get("ambience", [])).lower()
    char_settings = _character_settings(db, ch.id)
    rnd = random.Random()
    created: list[ContentIdea] = []
    for ct in _channel_types(ch, content_type):
        settings = list(dict.fromkeys(char_settings + SETTINGS[ct]))
        combos = list(itertools.product(settings, TIMES, WEATHER.get(ct, DEFAULT_WEATHER), MIXES[ct], DURATIONS[ct]))
        rnd.shuffle(combos)
        # prefer mixes matching the channel's declared ambience (e.g. "rain")
        combos.sort(key=lambda c: -sum(1 for s in c[3] if s.split("_")[0] in ambience))
        per_type = max(1, count // max(1, len(_channel_types(ch, content_type))))
        made = 0
        for setting, tod, weather, mix, duration in combos:
            if len(created) >= count or made >= per_type + 1:
                break
            fp = fingerprint(ct.value, setting, tod, weather, mix, duration)
            theme = f"{weather} {tod}" if lang == "en" else f"{_vi(tod)} {_vi(weather)}"
            if fp in existing or (ct.value, setting.lower(), theme.lower()) in project_keys:
                continue
            effects = ["vignette"]
            if weather in ("rainy", "thunderstorm", "drizzle"):
                effects.append("rain")
            if weather in ("snowy", "winter"):
                effects.append("snow")
            if "fireplace" in mix:
                effects.append("warm_flicker")
            idea = ContentIdea(
                channel_id=ch.id, title=_title(lang, ct, duration, setting, tod, weather), content_type=ct,
                theme=theme, fingerprint=fp,
                description=(f"{TYPE_LABELS[lang][ct.value]} · {_vi(setting) if lang == 'vi' else setting} · "
                             f"{theme} · {', '.join(mix)} · {duration_label(duration, lang)}"),
                attributes={"setting": setting if lang == "en" else _vi(setting), "time_of_day": tod,
                            "weather": weather, "sounds": mix, "duration_minutes": duration, "effects": effects},
            )
            db.add(idea)
            existing.add(fp)
            created.append(idea)
            made += 1
        if len(created) >= count:
            break
    if not created:
        raise AppError("Đã dùng hết các tổ hợp ý tưởng cho kênh này. Hãy thêm chủ đề / bối cảnh nhân vật mới.")
    db.flush()
    activity.record(db, "content", f"Sinh {len(created)} ý tưởng video mới", channel_id=ch.id)
    db.commit()
    return [idea_out(i) for i in created]


def list_ideas(db: Session, channel_id: int, status: IdeaStatus | None = None) -> list[IdeaOut]:
    stmt = select(ContentIdea).where(ContentIdea.channel_id == channel_id)
    if status is not None:
        stmt = stmt.where(ContentIdea.status == status)
    return [idea_out(i) for i in db.scalars(stmt.order_by(ContentIdea.created_at.desc(), ContentIdea.id.desc()))]


def get_idea(db: Session, channel_id: int, idea_id: int) -> ContentIdea:
    i = db.get(ContentIdea, idea_id)
    if i is None or i.channel_id != channel_id:
        raise NotFound(f"Kênh #{channel_id} không có ý tưởng #{idea_id}")
    return i


def set_status(db: Session, idea: ContentIdea, status: IdeaStatus) -> IdeaOut:
    idea.status = status
    db.commit()
    return idea_out(idea)


def delete_idea(db: Session, idea: ContentIdea) -> None:
    db.delete(idea)
    db.commit()


def _pick_background(db: Session, channel_id: int, words: list[str]) -> int | None:
    images = db.scalars(select(Asset).where(Asset.kind == AssetKind.IMAGE,
                                            (Asset.channel_id == channel_id) | Asset.channel_id.is_(None))).all()
    best, score = None, 0
    for a in images:
        hay = " ".join([a.name, *a.tags]).lower()
        s = sum(1 for w in words if w and w.lower() in hay)
        if s > score:
            best, score = a.id, s
    return best


def to_project_payload(db: Session, ch: Channel, idea: ContentIdea) -> ContentCreate:
    """Turn an idea into a ContentCreate using the built-in template of its type."""
    a = idea.attributes or {}
    tpl = db.scalar(select(VideoTemplate).where(VideoTemplate.channel_id.is_(None),
                                                VideoTemplate.content_type == idea.content_type)
                    .order_by(VideoTemplate.id).limit(1))
    sounds = a.get("sounds") or ["rain"]
    layers = [{"kind": "generator", "generator": s, "volume": 0.7 if i == 0 else 0.35} for i, s in enumerate(sounds)]
    primary = db.scalar(select(ChannelCharacter).where(ChannelCharacter.channel_id == ch.id,
                                                       ChannelCharacter.role == CharacterRole.PRIMARY))
    character_id = None
    if primary is not None and not primary.character.archived and primary.character.current_version:
        v = primary.character.current_version
        if v.full_body_image or v.avatar_image:
            character_id = primary.character_id
    payload: dict = {
        "title": idea.title, "content_type": idea.content_type, "theme": idea.theme,
        "setting": a.get("setting", ""), "duration_minutes": a.get("duration_minutes", 120),
        "audio_layers": layers, "idea_id": idea.id, "character_id": character_id,
        "background_asset_id": _pick_background(db, ch.id, [a.get("setting", ""), a.get("weather", ""),
                                                            a.get("time_of_day", "")]),
    }
    if tpl is not None:
        payload["template_id"] = tpl.id
        anim = dict((tpl.config or {}).get("animation") or {})
        anim["effects"] = a.get("effects") or anim.get("effects", [])
        payload["animation"] = anim
    elif a.get("effects"):
        payload["animation"] = {"effects": a["effects"]}
    return ContentCreate(**payload)
