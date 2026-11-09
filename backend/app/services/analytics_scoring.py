"""Pure functions (no database): video scoring, retention maths, recommendations.

Scores are *calculated by Coco from YouTube-reported metrics* — they are never shown as if YouTube
reported them. A video is judged against the other videos of ITS OWN channel (percentile rank),
using watch time, view duration %, retention, subscribers gained and engagement — not views alone.
"""
from __future__ import annotations

from statistics import median

# metric -> weight (re-normalised over the metrics that exist for a video)
WEIGHTS: dict[str, float] = {
    "watch_time_per_day": 0.30,
    "avg_view_pct": 0.20,
    "retention": 0.15,
    "subs_per_1k_views": 0.15,
    "engagement": 0.10,
    "views_per_day": 0.10,
}
LABELS_VI = {
    "watch_time_per_day": "watch time/ngày",
    "avg_view_pct": "% xem trung bình",
    "retention": "giữ chân người xem",
    "subs_per_1k_views": "subscriber/1000 lượt xem",
    "engagement": "tương tác (like+comment)/lượt xem",
    "views_per_day": "lượt xem/ngày",
}
MIN_DAYS_LIVE = 3          # younger videos are "too_new": YouTube data is still settling
MIN_COHORT = 4             # percentile ranks are meaningless below this
STRONG_AT = 65.0
WEAK_AT = 35.0
MIN_SLOT_SAMPLES = 3


def percentile_ranks(values: list[float | None]) -> list[float | None]:
    """Mid-rank percentile (0..1) of every value among the non-None ones; None stays None."""
    present = [v for v in values if v is not None]
    n = len(present)
    out: list[float | None] = []
    for v in values:
        if v is None:
            out.append(None)
        elif n == 1:
            out.append(0.5)
        else:
            less = sum(1 for x in present if x < v)
            equal = sum(1 for x in present if x == v)
            out.append((less + 0.5 * (equal - 1)) / (n - 1))
    return out


def derive_metrics(v: dict) -> dict[str, float | None]:
    """v needs: views, watch_time_minutes, exposure_days, avg_view_pct, retention_avg, subs, likes, comments."""
    days = max(v.get("exposure_days") or 0, 1)
    views = v.get("views") or 0
    return {
        "watch_time_per_day": (v["watch_time_minutes"] or 0) / days if v.get("has_data") else None,
        "views_per_day": views / days if v.get("has_data") else None,
        "avg_view_pct": v.get("avg_view_pct"),
        "retention": v.get("retention_avg"),
        "subs_per_1k_views": (v["subs"] / views * 1000) if v.get("has_data") and views > 0 else None,
        "engagement": ((v["likes"] + v["comments"]) / views) if v.get("has_data") and views > 0 else None,
    }


def score_videos(items: list[dict]) -> None:
    """Adds `metrics`, `score` (0..100|None), `label`, `components`, `weak_reasons` to each item in place.

    Items are compared inside their channel only (`channel_id`).
    """
    by_channel: dict[int, list[dict]] = {}
    for it in items:
        it["metrics"] = derive_metrics(it)
        it["score"], it["components"], it["weak_reasons"] = None, {}, []
        if not it.get("has_data"):
            it["label"] = "not_synced"
        elif (it.get("exposure_days") or 0) < MIN_DAYS_LIVE:
            it["label"] = "too_new"
        else:
            it["label"] = "insufficient_data"
            by_channel.setdefault(it["channel_id"], []).append(it)

    for cohort in by_channel.values():
        if len(cohort) < MIN_COHORT:
            continue
        ranks = {m: percentile_ranks([c["metrics"][m] for c in cohort]) for m in WEIGHTS}
        medians = {m: median([c["metrics"][m] for c in cohort if c["metrics"][m] is not None] or [0]) for m in WEIGHTS}
        for i, it in enumerate(cohort):
            comps = {m: ranks[m][i] for m in WEIGHTS if ranks[m][i] is not None}
            total_w = sum(WEIGHTS[m] for m in comps)
            if not comps or total_w == 0:
                continue
            score = 100 * sum(WEIGHTS[m] * r for m, r in comps.items()) / total_w
            it["score"] = round(score, 1)
            it["components"] = {m: round(r * 100, 1) for m, r in comps.items()}
            it["label"] = "strong" if score >= STRONG_AT else "weak" if score <= WEAK_AT else "average"
            for m, r in comps.items():
                if r <= 0.25 and WEIGHTS[m] >= 0.10:
                    val = it["metrics"][m]
                    it["weak_reasons"].append(
                        f"{LABELS_VI[m]} thấp: {_fmt(m, val)} (trung vị kênh {_fmt(m, medians[m])})")


def _fmt(metric: str, v: float | None) -> str:
    if v is None:
        return "—"
    if metric in ("avg_view_pct",):
        return f"{v:.1f}%"
    if metric in ("retention", "engagement"):
        return f"{v * 100:.1f}%"
    if metric == "subs_per_1k_views":
        return f"{v:.2f}"
    return f"{v:.1f}"


# ---------------------------------------------------------------- retention
def retention_at(points: list[list[float]], ratio: float) -> float | None:
    """Audience watch ratio at `ratio` of the video (linear interpolation), None without data."""
    if not points:
        return None
    pts = sorted(points)
    if ratio <= pts[0][0]:
        return pts[0][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x0 <= ratio <= x1:
            return y0 if x1 == x0 else y0 + (y1 - y0) * (ratio - x0) / (x1 - x0)
    return pts[-1][1]


def retention_summary(points: list[list[float]]) -> dict:
    if not points:
        return {"average": None, "at_10": None, "at_25": None, "at_50": None, "at_75": None, "steepest_drop": None}
    pts = sorted(points)
    drop = None
    window = 0.10
    for x0, y0 in pts:
        y1 = retention_at(pts, min(1.0, x0 + window))
        if y1 is None or x0 + window > 1.0 + 1e-9:
            continue
        delta = y1 - y0
        if drop is None or delta < drop["delta"]:
            drop = {"from": round(x0, 3), "to": round(min(1.0, x0 + window), 3), "delta": round(delta, 4)}
    if drop is not None and drop["delta"] >= -0.05:
        drop = None  # nothing notable
    return {
        "average": round(sum(y for _, y in pts) / len(pts), 4),
        "at_10": _r(retention_at(pts, 0.10)), "at_25": _r(retention_at(pts, 0.25)),
        "at_50": _r(retention_at(pts, 0.50)), "at_75": _r(retention_at(pts, 0.75)),
        "steepest_drop": drop,
    }


def _r(v: float | None) -> float | None:
    return None if v is None else round(v, 4)


def average_curves(curves: list[list[list[float]]]) -> list[list[float]]:
    acc: dict[float, list[float]] = {}
    for pts in curves:
        for x, y in pts:
            acc.setdefault(round(x, 2), []).append(y)
    return [[x, sum(ys) / len(ys)] for x, ys in sorted(acc.items())]


# ---------------------------------------------------------------- recommendations
def confidence(n: int) -> str:
    return "high" if n >= 8 else "medium" if n >= 4 else "low"


def build_recommendations(*, topics: list[dict], durations: list[dict], posting: dict, retention: dict | None,
                          weak_videos: list[dict], scored_videos: int, days_since_upload: int | None) -> list[dict]:
    """Rule-based, evidence-carrying advice. Every item states the numbers it is based on."""
    recs: list[dict] = []

    if days_since_upload is not None and days_since_upload >= 14:
        recs.append({"kind": "cadence", "confidence": "high",
                     "text": f"Kênh chưa đăng video mới trong {days_since_upload} ngày. Đều đặn đăng bài giúp "
                             "thuật toán và người xem quay lại.",
                     "evidence": {"days_since_last_upload": days_since_upload}})

    if scored_videos < 4:
        recs.append({"kind": "need_data", "confidence": "high",
                     "text": "Chưa đủ dữ liệu để đánh giá chủ đề/khung giờ/thời lượng: cần ít nhất 4 video đã đăng "
                             "≥3 ngày và đã đồng bộ Analytics.",
                     "evidence": {"videos_with_score": scored_videos}})
        return recs

    ranked = [t for t in topics if t["n_scored"] >= 2 and t["avg_score"] is not None]
    if len(ranked) >= 2:
        ranked.sort(key=lambda t: t["avg_score"], reverse=True)
        best, worst = ranked[0], ranked[-1]
        if best["avg_score"] - worst["avg_score"] >= 10:
            recs.append({
                "kind": "topic", "confidence": confidence(best["n_scored"] + worst["n_scored"]),
                "suggested_content_type": best["key"] if best["group"] == "content_type" else None,
                "text": f"Chủ đề '{best['label']}' đang hiệu quả nhất (điểm TB {best['avg_score']:.0f}, "
                        f"{best['n_scored']} video) so với '{worst['label']}' ({worst['avg_score']:.0f}). "
                        f"Nên sản xuất thêm '{best['label']}' với bối cảnh/âm thanh MỚI (không nhân bản hàng loạt "
                        "chỉ đổi tiêu đề).",
                "evidence": {"best": best["label"], "best_score": best["avg_score"],
                             "worst": worst["label"], "worst_score": worst["avg_score"]}})

    dur = [d for d in durations if d["n_scored"] >= 2 and d["avg_score"] is not None]
    if len(dur) >= 2:
        dur.sort(key=lambda d: d["avg_score"], reverse=True)
        if dur[0]["avg_score"] - dur[-1]["avg_score"] >= 10:
            recs.append({
                "kind": "duration", "confidence": confidence(dur[0]["n_scored"]),
                "text": f"Video dài ~{dur[0]['minutes']} phút có điểm TB cao nhất ({dur[0]['avg_score']:.0f}) "
                        f"so với ~{dur[-1]['minutes']} phút ({dur[-1]['avg_score']:.0f}).",
                "evidence": {"best_minutes": dur[0]["minutes"], "best_score": dur[0]["avg_score"],
                             "worst_minutes": dur[-1]["minutes"], "worst_score": dur[-1]["avg_score"]}})

    slots = [h for h in posting.get("by_hour", []) if h["n"] >= MIN_SLOT_SAMPLES and h["avg_views_7d"] is not None]
    if slots:
        best = max(slots, key=lambda h: h["avg_views_7d"])
        recs.append({
            "kind": "posting_time", "confidence": confidence(best["n"]),
            "text": f"Video đăng lúc {best['hour']:02d}:00 (giờ kênh) có lượt xem 7 ngày đầu cao nhất: "
                    f"TB {best['avg_views_7d']:.0f} ({best['n']} video).",
            "evidence": {"hour": best["hour"], "avg_views_7d": best["avg_views_7d"], "samples": best["n"]}})
    elif posting.get("measured_videos", 0) > 0:
        recs.append({"kind": "posting_time", "confidence": "low",
                     "text": "Chưa đủ mẫu để kết luận khung giờ đăng tốt nhất (cần ≥3 video cùng khung giờ).",
                     "evidence": {"videos_measured": posting["measured_videos"]}})

    if retention and retention.get("at_10") is not None and retention["n_videos"] >= 2:
        if retention["at_10"] < 0.5:
            recs.append({
                "kind": "retention", "confidence": confidence(retention["n_videos"]),
                "text": f"Trung bình chỉ {retention['at_10'] * 100:.0f}% người xem còn lại ở 10% đầu video. "
                        "Cân nhắc cải thiện cảnh mở đầu (vào nội dung/âm thanh chính sớm hơn).",
                "evidence": {"retention_at_10pct": retention["at_10"], "videos": retention["n_videos"]}})

    if weak_videos:
        names = ", ".join(f"'{v['title']}'" for v in weak_videos[:3])
        recs.append({"kind": "underperformers", "confidence": confidence(scored_videos),
                     "text": f"{len(weak_videos)} video hiệu suất thấp so với phần còn lại của kênh: {names}. "
                             "Xem lý do chi tiết, thử đổi thumbnail/tiêu đề hoặc ngừng làm dạng tương tự.",
                     "evidence": {"video_ids": [v["video_id"] for v in weak_videos[:10]]}})
    return recs
