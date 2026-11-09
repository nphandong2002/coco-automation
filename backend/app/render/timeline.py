"""Timeline construction: Pomodoro phases, countdown, YouTube chapters."""
from __future__ import annotations

from dataclasses import asdict, dataclass

FOCUS, SHORT_BREAK, LONG_BREAK, SESSION = "focus", "short_break", "long_break", "session"

DEFAULT_LABELS = {
    "en": {FOCUS: "FOCUS", SHORT_BREAK: "BREAK", LONG_BREAK: "LONG BREAK", SESSION: "STUDY SESSION"},
    "vi": {FOCUS: "TẬP TRUNG", SHORT_BREAK: "NGHỈ NGẮN", LONG_BREAK: "NGHỈ DÀI", SESSION: "PHIÊN HỌC"},
}
CHAPTER_NAMES = {
    "en": {FOCUS: "Focus", SHORT_BREAK: "Break", LONG_BREAK: "Long break", SESSION: "Session"},
    "vi": {FOCUS: "Tập trung", SHORT_BREAK: "Nghỉ ngắn", LONG_BREAK: "Nghỉ dài", SESSION: "Phiên học"},
}


@dataclass
class Phase:
    kind: str
    start: float
    end: float
    index: int        # focus session number (1-based), 0 for breaks
    total: int        # total number of focus sessions in the video

    @property
    def duration(self) -> float:
        return self.end - self.start


def pomodoro_phases(duration_sec: float, focus_min: float, short_break_min: float,
                    long_break_min: float, cycles_before_long: int) -> list[Phase]:
    """Focus/break phases covering exactly [0, duration_sec]. The last phase is truncated."""
    if focus_min <= 0:
        raise ValueError("focus_min phải > 0")
    phases: list[Phase] = []
    t, n = 0.0, 0
    while t < duration_sec - 0.5:
        n += 1
        end = min(t + focus_min * 60, duration_sec)
        phases.append(Phase(FOCUS, t, end, n, 0))
        t = end
        if t >= duration_sec - 0.5:
            break
        is_long = cycles_before_long > 0 and n % cycles_before_long == 0
        brk = (long_break_min if is_long else short_break_min) * 60
        if brk <= 0:
            continue
        end = min(t + brk, duration_sec)
        phases.append(Phase(LONG_BREAK if is_long else SHORT_BREAK, t, end, 0, 0))
        t = end
    # drop a ridiculously short trailing phase (< 30 s) by extending the previous one
    if len(phases) > 1 and phases[-1].duration < 30:
        last = phases.pop()
        phases[-1].end = last.end
    total = sum(1 for p in phases if p.kind == FOCUS)
    for p in phases:
        p.total = total
    return phases


def countdown_phases(duration_sec: float) -> list[Phase]:
    return [Phase(SESSION, 0.0, float(duration_sec), 1, 1)]


def fmt_ts(seconds: float) -> str:
    s = int(round(seconds))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h:d}:{m:02d}:{sec:02d}" if h else f"{m:02d}:{sec:02d}"


def chapters(phases: list[Phase], lang: str = "en") -> list[dict]:
    """YouTube chapters: first at 00:00, at least 3, each >= 10 s. Returns [] when not applicable."""
    names = CHAPTER_NAMES.get(lang, CHAPTER_NAMES["en"])
    out = []
    for p in phases:
        if p.duration < 10:
            continue
        title = f"{names[p.kind]} {p.index}/{p.total}" if p.kind == FOCUS else names[p.kind]
        out.append({"start": p.start, "timestamp": fmt_ts(p.start), "title": title})
    if len(out) < 3 or out[0]["start"] != 0:
        return []
    return out


def to_json(phases: list[Phase]) -> list[dict]:
    return [asdict(p) for p in phases]


def from_json(items: list[dict]) -> list[Phase]:
    return [Phase(**i) for i in items]
