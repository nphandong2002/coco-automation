"""Tạo kênh + nhân vật mẫu "Koko" qua API của hệ thống đang chạy (đọc tài khoản dashboard từ .env).

    .venv\\Scripts\\python scripts\\seed_koko.py

Chạy lại nhiều lần vẫn an toàn: thấy kênh/nhân vật đã có thì bỏ qua.
"""
import base64
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
env = dict(l.split("=", 1) for l in (ROOT / ".env").read_text(encoding="utf-8").splitlines()
           if "=" in l and not l.lstrip().startswith("#"))
BASE = f"http://localhost:{env.get('PORT', '8080')}/api"
c = httpx.Client(base_url=BASE, auth=(env["DASHBOARD_USERNAME"], env["DASHBOARD_PASSWORD"]), timeout=30)

CHANNEL = {
    "code": "koko-bedtime",
    "name": "Koko Kể Chuyện Đêm Khuya",
    "description": ("Chào bạn, mình là Koko, cú thủ thư của Thư viện lúc nửa đêm. "
                    "Mỗi tối Koko pha một tách trà và kể một câu chuyện nhẹ nhàng để bạn thư giãn và ngủ ngon.\n"
                    "Truyện cổ tích đêm khuya · Chuyện thư viện cây sồi · Vũ trụ trước giờ ngủ"),
    "language": "vi",
    "target_country": "VN",
    "topics": ["truyện ngủ ngon", "truyện cổ tích", "thư giãn", "ASMR nhẹ", "lofi"],
    "visual_style": {
        "theme": "Thư viện trong thân cây sồi lúc nửa đêm",
        "mood": "ấm áp, yên tĩnh, buồn ngủ",
        "palette": ["#F2E3C6", "#8B5E3C", "#E0A526", "#1F2A44", "#FFD98A"],
        "keywords": ["watercolor", "gouache", "đèn dầu", "trời sao", "sách cũ"],
    },
    "audio_style": {
        "ambience": ["tiếng lửa nhỏ", "mưa nhẹ", "gió đêm", "tiếng giở sách"],
        "music": "lofi / ambient piano chậm, có bản quyền rõ ràng",
        "notes": "Giọng trầm ấm 110–125 từ/phút; nhạc nền nhỏ hơn giọng ít nhất 12 dB; không quảng cáo giữa truyện.",
    },
    "publish_schedule": {
        "timezone": "Asia/Ho_Chi_Minh",
        "slots": [{"weekday": d, "time": "20:30"} for d in (0, 2, 4)],  # T2, T4, T6
    },
}

CHARACTER = {
    "name": "Koko",
    "species": "Cú mèo",
    "role": "primary",
    "appearance": ("Cú mèo nhỏ lông kem pha nâu, đeo kính tròn gọng vàng hơi lệch xuống mũi, "
                   "một chiếc lông trên đầu dựng lên như dấu chấm hỏi, đôi mắt to hiền, luôn cầm tách trà có hơi nước."),
    "art_style": "Tranh màu nước và gouache, nét bo tròn, ấm áp",
    "primary_colors": ["#F2E3C6", "#8B5E3C", "#E0A526", "#1F2A44", "#FFD98A"],
    "outfit": "Khăn len màu mù tạt quấn cổ, một đầu khăn dài hơn đầu kia.",
    "personality": ("Dịu dàng, kiên nhẫn, hơi hay quên, hài hước nhẹ. Thích pha trà hoa cúc, sưu tầm sách cũ, "
                    "ngắm sao, đan khăn mãi không xong. Sợ tiếng sấm và hết trà. "
                    "Câu cửa miệng: 'Chào bạn, đêm nay mình đọc gì nhỉ?'; kết: 'Ngủ ngon nhé. Koko giữ đèn cho bạn.'"),
    "usual_settings": ["Thư viện trong thân cây sồi", "Bên cửa sổ nhìn ra trời sao", "Ghế bành cạnh đèn dầu"],
    "allowed_animations": ["chớp mắt", "gật đầu", "nhấp trà", "lật sách", "vẫy tay chào"],
}


def die(r: httpx.Response) -> None:
    sys.exit(f"LỖI {r.status_code} {r.request.method} {r.request.url.path}: {r.text[:400]}")


r = c.get("/channels")
r.raise_for_status()
ch = next((x for x in r.json() if x["code"] == CHANNEL["code"]), None)
if ch:
    print(f"Kênh đã có (id={ch['id']}), bỏ qua.")
else:
    r = c.post("/channels", json=CHANNEL)
    if r.status_code >= 400:
        die(r)
    ch = r.json()
    print(f"Đã tạo kênh id={ch['id']} ({ch['name']})")

r = c.get(f"/channels/{ch['id']}/characters")
r.raise_for_status()
if any(x["name"] == CHARACTER["name"] for x in r.json()):
    print("Nhân vật Koko đã có, bỏ qua.")
else:
    r = c.post(f"/channels/{ch['id']}/characters", json=CHARACTER)
    if r.status_code >= 400:
        die(r)
    print(f"Đã tạo nhân vật id={r.json()['id']} (Koko)")
print(f"Mở: http://localhost:{env.get('PORT', '8080')}/  → kênh '{CHANNEL['name']}'")
