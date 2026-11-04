import os
import json
import time
import random
import sqlite3
import requests
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional

app = FastAPI(title="Phàm Nhân Tu Tiên - Turso Cloud Edition")

# ==========================================
# 1. CẤU HÌNH TURSO CLOUD DATABASE (HTTP API)
# ==========================================
TURSO_URL = os.getenv("TURSO_DATABASE_URL", "").strip()
TURSO_TOKEN = os.getenv("TURSO_AUTH_TOKEN", "").strip()
LOCAL_DB = "game_local.db"


class DatabaseAdapter:

    def __init__(self):
        self.use_turso = bool(TURSO_URL and TURSO_TOKEN)
        if self.use_turso:
            self.http_url = TURSO_URL.replace("libsql://", "https://").rstrip(
                "/"
            )
            if not self.http_url.startswith("https://"):
                self.http_url = "https://" + self.http_url

    def _to_turso_arg(self, val):
        if val is None:
            return {"type": "null"}
        elif isinstance(val, bool):
            return {"type": "integer", "value": "1" if val else "0"}
        elif isinstance(val, int):
            return {"type": "integer", "value": str(val)}
        elif isinstance(val, float):
            return {"type": "float", "value": val}
        return {"type": "text", "value": str(val)}

    def _from_turso_val(self, cell):
        t = cell.get("type")
        val = cell.get("value")
        if t == "null" or val is None:
            return None
        if t == "integer":
            return int(val)
        if t == "float":
            return float(val)
        return str(val)

    def execute(
        self, sql: str, params: tuple = (), fetchone=False, fetchall=False
    ):
        if self.use_turso:
            headers = {
                "Authorization": f"Bearer {TURSO_TOKEN}",
                "Content-Type": "application/json",
            }
            stmt = {"sql": sql, "args": [self._to_turso_arg(p) for p in params]}
            payload = {
                "requests": [{"type": "execute", "stmt": stmt}, {"type": "close"}]
            }
            res = requests.post(
                f"{self.http_url}/v2/pipeline",
                headers=headers,
                json=payload,
                timeout=12,
            )
            if res.status_code != 200:
                raise Exception(f"Turso HTTP Error: {res.text}")
            data = res.json()
            first_res = data.get("results", [{}])[0]
            if first_res.get("type") == "error":
                raise Exception(f"Turso SQL Error: {first_res.get('error')}")
            exec_res = first_res.get("response", {}).get("result", {})
            cols = [c["name"] for c in exec_res.get("cols", [])]
            rows = []
            for r in exec_res.get("rows", []):
                row_dict = {
                    cols[i]: self._from_turso_val(r[i])
                    for i in range(len(cols))
                }
                rows.append(row_dict)
            if fetchone:
                return rows[0] if rows else None
            if fetchall:
                return rows
            return True
        else:
            conn = sqlite3.connect(LOCAL_DB)
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute(sql, params)
            if fetchone:
                row = c.fetchone()
                conn.commit()
                conn.close()
                return dict(row) if row else None
            if fetchall:
                rows = [dict(r) for r in c.fetchall()]
                conn.commit()
                conn.close()
                return rows
            conn.commit()
            conn.close()
            return True


db = DatabaseAdapter()


def init_db():
    db.execute("""
        CREATE TABLE IF NOT EXISTS characters (
            id TEXT PRIMARY KEY,
            tg_id TEXT,
            slot INTEGER,
            name TEXT,
            gender TEXT,
            age INTEGER,
            max_age INTEGER,
            realm_idx INTEGER,
            level INTEGER,
            exp INTEGER,
            stones INTEGER,
            iron INTEGER,
            hammers INTEGER,
            pity_hammer INTEGER,
            stamina INTEGER,
            last_stamina_ts REAL,
            last_cultivate_ts REAL,
            last_active_ts REAL,
            rebirth_count INTEGER,
            potential_pts INTEGER,
            can_allocate_base INTEGER,
            ability_pts INTEGER,
            breakthrough_bonus INTEGER,
            base_stats TEXT,
            ability_stats TEXT,
            bone TEXT,
            roots_inv TEXT,
            roots_equipped TEXT,
            titles TEXT,
            equipped_title TEXT,
            inventory TEXT,
            equipped_items TEXT,
            pills TEXT,
            boss_attempts INTEGER,
            boss_id_joined INTEGER
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS world_boss (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            max_hp INTEGER,
            hp INTEGER,
            atk INTEGER,
            def_val INTEGER,
            dodge INTEGER,
            counter INTEGER,
            lifesteal INTEGER,
            element TEXT,
            active INTEGER,
            damage_board TEXT
        )
    """)
    boss = db.execute(
        "SELECT * FROM world_boss ORDER BY id DESC LIMIT 1", fetchone=True
    )
    if not boss:
        db.execute(
            """
            INSERT INTO world_boss (name, max_hp, hp, atk, def_val, dodge, counter, lifesteal, element, active, damage_board)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                "Thượng Cổ Huyết Ma Viên",
                500000,
                500000,
                850,
                200,
                15,
                15,
                10,
                "Hỏa",
                1,
                "{}",
            ),
        )


init_db()

# ==========================================
# 2. HẰNG SỐ VÀ CƠ SỞ DỮ LIỆU GAME
# ==========================================
REALMS = [
    {"name": "Phàm Nhân", "max_age": 100, "base_exp": 100, "hp_mult": 1.0},
    {"name": "Luyện Khí Kỳ", "max_age": 150, "base_exp": 250, "hp_mult": 1.4},
    {"name": "Trúc Cơ Kỳ", "max_age": 250, "base_exp": 600, "hp_mult": 2.0},
    {"name": "Kim Đan Kỳ", "max_age": 500, "base_exp": 1500, "hp_mult": 3.2},
    {"name": "Nguyên Anh Kỳ", "max_age": 1000, "base_exp": 3500, "hp_mult": 5.0},
    {"name": "Hóa Thần Kỳ", "max_age": 2000, "base_exp": 8000, "hp_mult": 8.0},
    {
        "name": "Luyện Hư Kỳ",
        "max_age": 4000,
        "base_exp": 18000,
        "hp_mult": 13.0,
    },
    {"name": "Hợp Thể Kỳ", "max_age": 8000, "base_exp": 40000, "hp_mult": 21.0},
    {
        "name": "Đại Thừa Kỳ",
        "max_age": 15000,
        "base_exp": 90000,
        "hp_mult": 35.0,
    },
    {
        "name": "Độ Kiếp Chân Tiên",
        "max_age": 99999,
        "base_exp": 250000,
        "hp_mult": 60.0,
    },
]

BONES = [
    {
        "id": "pham_cot",
        "name": "Phàm Cốt",
        "rank": "D",
        "desc": "Thể chất bình thường của phàm nhân.",
        "hp_pct": 0,
        "atk_pct": 0,
        "immortal": False,
    },
    {
        "id": "linh_cot",
        "name": "Thanh Linh Đạo Cốt",
        "rank": "B",
        "desc": "Kinh mạch thông suốt, tăng 15% Máu và 10% Công.",
        "hp_pct": 15,
        "atk_pct": 10,
        "immortal": False,
    },
    {
        "id": "ba_cot",
        "name": "Hoang Cổ Bá Thể",
        "rank": "A",
        "desc": "Nhục thân vô song, tăng 30% Máu và 20% Công.",
        "hp_pct": 30,
        "atk_pct": 20,
        "immortal": False,
    },
    {
        "id": "tien_cot",
        "name": "Tiên Thiên Đạo Thể",
        "rank": "S",
        "desc": "Con cưng của trời đất, tăng 50% Máu, 35% Công.",
        "hp_pct": 50,
        "atk_pct": 35,
        "immortal": False,
    },
    {
        "id": "ma_cot",
        "name": "Thượng Cổ Ma Thần Thể",
        "rank": "SS",
        "desc": "Sát phạt quyết đoán, tăng 40% Máu, 60% Công.",
        "hp_pct": 40,
        "atk_pct": 60,
        "immortal": False,
    },
    {
        "id": "vinh_sinh",
        "name": "Vĩnh Sinh Bất Diệt Thể",
        "rank": "SSS",
        "desc": (
            "Thọ nguyên VÔ HẠN (∞), không bao giờ chết già, +60% Máu, +40%"
            " Công."
        ),
        "hp_pct": 60,
        "atk_pct": 40,
        "immortal": True,
    },
]

ROOTS_POOL = [
    {
        "id": "tap_linh",
        "name": "Ngũ Hành Tạp Linh Căn",
        "rank": "D",
        "element": "Thổ",
        "atk": 10,
        "hp": 50,
        "crit": 1,
        "desc": "Linh căn tạp chất, tăng 10 Công, 50 HP, 1% Bạo.",
    },
    {
        "id": "hoa_linh",
        "name": "Liệt Hỏa Linh Căn",
        "rank": "C",
        "element": "Hỏa",
        "atk": 35,
        "hp": 100,
        "crit": 3,
        "desc": "Hệ Hỏa (Khắc Kim), +35 Công, +100 HP, +3% Bạo.",
    },
    {
        "id": "thuy_linh",
        "name": "Huyền Thủy Linh Căn",
        "rank": "C",
        "element": "Thủy",
        "atk": 25,
        "hp": 220,
        "crit": 2,
        "desc": "Hệ Thủy (Khắc Hỏa), +25 Công, +220 HP, +2% Bạo.",
    },
    {
        "id": "moc_linh",
        "name": "Thanh Mộc Linh Căn",
        "rank": "B",
        "element": "Mộc",
        "atk": 45,
        "hp": 380,
        "crit": 3,
        "desc": "Hệ Mộc (Khắc Thổ), +45 Công, +380 HP, +3% Bạo.",
    },
    {
        "id": "kim_linh",
        "name": "Canh Kim Kiếm Căn",
        "rank": "B",
        "element": "Kim",
        "atk": 80,
        "hp": 180,
        "crit": 6,
        "desc": "Hệ Kim (Khắc Mộc), +80 Công, +180 HP, +6% Bạo.",
    },
    {
        "id": "tho_linh",
        "name": "Hậu Thổ Hoàng Căn",
        "rank": "A",
        "element": "Thổ",
        "atk": 70,
        "hp": 600,
        "crit": 4,
        "desc": "Hệ Thổ (Khắc Thủy), +70 Công, +600 HP, +4% Bạo.",
    },
    {
        "id": "phong_linh",
        "name": "Cuồng Phong Dị Linh Căn",
        "rank": "A",
        "element": "Phong",
        "atk": 120,
        "hp": 350,
        "crit": 12,
        "desc": "Biến dị Phong (Không bị khắc), +120 Công, +350 HP, +12% Bạo.",
    },
    {
        "id": "bang_linh",
        "name": "Hàn Băng Thiên Linh Căn",
        "rank": "S",
        "element": "Băng",
        "atk": 180,
        "hp": 800,
        "crit": 10,
        "desc": "Biến dị Băng (Giảm tốc địch), +180 Công, +800 HP, +10% Bạo.",
    },
    {
        "id": "loi_linh",
        "name": "Cửu Thiên Lôi Linh Căn",
        "rank": "SS",
        "element": "Lôi",
        "atk": 300,
        "hp": 1000,
        "crit": 18,
        "desc": "Biến dị Lôi (Tê liệt mục tiêu), +300 Công, +1000 HP, +18% Bạo.",
    },
    {
        "id": "hon_don",
        "name": "Hỗn Độn Hồng Mông Căn",
        "rank": "SSS",
        "element": "Hỗn Độn",
        "atk": 550,
        "hp": 2500,
        "crit": 25,
        "desc": (
            "Chí tôn vạn giới (Áp chế mọi hệ), +550 Công, +2500 HP, +25% Bạo."
        ),
    },
]

TITLES_INFO = {
    "Tân Thủ Tu Tiên": {
        "desc": "Danh hiệu khởi đầu của người bước vào tiên giới.",
        "dodge": 0,
        "atk_pct": 0,
        "bypass_dodge_cap": False,
    },
    "Vây Hạ Đại Boss": {
        "desc": (
            "Top 10 Sát Thương Boss Thế Giới: +10% Né Tránh (Được phép vượt"
            " trần giới hạn né tránh 75% lên 85%)."
        ),
        "dodge": 10,
        "atk_pct": 5,
        "bypass_dodge_cap": True,
    },
    "Luân Hồi Giả": {
        "desc": (
            "Đã trải qua Niết Bàn Trùng Sinh trên 500 tuổi: +10% Sát thương."
        ),
        "dodge": 2,
        "atk_pct": 10,
        "bypass_dodge_cap": False,
    },
}

# Ngũ hành tương khắc: Kim -> Mộc -> Thổ -> Thủy -> Hỏa -> Kim
ELEMENT_COUNTER = {
    "Kim": "Mộc",
    "Mộc": "Thổ",
    "Thổ": "Thủy",
    "Thủy": "Hỏa",
    "Hỏa": "Kim",
}

# 15 Vật phẩm trong Vạn Bảo Các (Tuyệt đối không bán Nhẫn Quỷ)
SHOP_ITEMS = [
    {
        "id": "tay_tuy_dich",
        "name": "Tẩy Tủy Dịch (Gacha Linh Căn)",
        "type": "gacha",
        "price": 1000,
        "desc": (
            "Quay ngẫu nhiên 1 Linh Căn vào Kho. Trùng lặp mất 1.000 LT không"
            " hoàn trả."
        ),
    },
    {
        "id": "than_chuy",
        "name": "Thiên Công Thần Chùy",
        "type": "hammer",
        "price": 2000,
        "desc": "Búa thần dùng để cường hóa trang bị lên tối đa +20.",
    },
    {
        "id": "tho_menh_dan",
        "name": "Thọ Mệnh Đan",
        "type": "pill_age",
        "price": 1500,
        "desc": "Tăng trực tiếp +50 năm Thọ Nguyên tối đa.",
    },
    {
        "id": "truc_co_dan",
        "name": "Trúc Cơ Đan",
        "type": "pill_break",
        "price": 600,
        "desc": "Tăng +10% tỉ lệ Đột Phá Bình Cảnh (Từ 80% lên 90%).",
    },
    {
        "id": "ket_dan_dan",
        "name": "Kết Đan Linh Đan",
        "type": "pill_break",
        "price": 1200,
        "desc": "Đan dược thượng phẩm giúp +10% tỉ lệ Đột Phá Bình Cảnh.",
    },
    {
        "id": "hoi_linh_dan",
        "name": "Cửu Chuyển Hồi Linh Đan",
        "type": "pill_mp",
        "price": 400,
        "desc": "Tăng vĩnh viễn +2 điểm Năng Lực Linh Lực (+20 MP).",
    },
    {
        "id": "hoi_xuan_dan",
        "name": "Hồi Xuân Chân Đan",
        "type": "pill_hp",
        "price": 800,
        "desc": "Tăng vĩnh viễn +5 điểm Năng Lực Máu (+25 HP).",
    },
    {
        "id": "vk_thanh_van",
        "name": "Thanh Vân Tiên Kiếm",
        "type": "equip",
        "slot": "weapon",
        "rank": "A",
        "price": 1200,
        "atk": 120,
        "hp": 100,
        "crit": 5,
        "dodge": 0,
        "lifesteal": 0,
        "dmg_red": 0,
        "desc": "Kiếm sắc bén của Thanh Vân Môn (+120 Công, +5% Bạo).",
    },
    {
        "id": "ao_huyen_vu",
        "name": "Huyền Vũ Hộ Tâm Giáp",
        "type": "equip",
        "slot": "armor",
        "rank": "A",
        "price": 1500,
        "atk": 20,
        "hp": 850,
        "crit": 0,
        "dodge": 2,
        "lifesteal": 0,
        "dmg_red": 4,
        "desc": "Giáp mai rùa Huyền Vũ (+850 HP, +4% Giảm ST).",
    },
    {
        "id": "mu_tu_van",
        "name": "Tử Vân Đạo Quán",
        "type": "equip",
        "slot": "helm",
        "rank": "B",
        "price": 1100,
        "atk": 35,
        "hp": 450,
        "crit": 2,
        "dodge": 2,
        "lifesteal": 0,
        "dmg_red": 2,
        "desc": "Mũ đạo sĩ Tử Vân (+450 HP, +35 Công).",
    },
    {
        "id": "quan_that_tinh",
        "name": "Thất Tinh Pháp Quần",
        "type": "equip",
        "slot": "pants",
        "rank": "B",
        "price": 1100,
        "atk": 30,
        "hp": 520,
        "crit": 0,
        "dodge": 4,
        "lifesteal": 0,
        "dmg_red": 2,
        "desc": "Quần thêu chòm sao Bắc Đẩu (+520 HP, +4% Né).",
    },
    {
        "id": "giay_thanh_phong",
        "name": "Thanh Phong Tiên Hài",
        "type": "equip",
        "slot": "boots",
        "rank": "B",
        "price": 1000,
        "atk": 40,
        "hp": 300,
        "crit": 2,
        "dodge": 7,
        "lifesteal": 0,
        "dmg_red": 0,
        "desc": "Giày đạp gió (+7% Né tránh, +40 Công).",
    },
    {
        "id": "nhan_luu_ly",
        "name": "Lưu Ly Giới Chỉ",
        "type": "equip",
        "slot": "ring",
        "rank": "A",
        "price": 1800,
        "atk": 95,
        "hp": 300,
        "crit": 6,
        "dodge": 2,
        "lifesteal": 2,
        "dmg_red": 0,
        "desc": "Nhẫn ngọc lưu ly (+95 Công, +6% Bạo, +2% Hút máu).",
    },
    {
        "id": "nhan_u_hon",
        "name": "U Hồn Linh Nhẫn",
        "type": "equip",
        "slot": "ring",
        "rank": "A",
        "price": 1800,
        "atk": 110,
        "hp": 200,
        "crit": 4,
        "dodge": 0,
        "lifesteal": 6,
        "dmg_red": 0,
        "desc": "Nhẫn u hồn (+110 Công, +6% Hút máu).",
    },
    {
        "id": "nhan_thien_diep",
        "name": "Thiên Diệp Bảo Giới",
        "type": "equip",
        "slot": "ring",
        "rank": "A",
        "price": 1800,
        "atk": 60,
        "hp": 650,
        "crit": 2,
        "dodge": 4,
        "lifesteal": 0,
        "dmg_red": 4,
        "desc": "Nhẫn ngàn lá (+650 HP, +4% Né, +4% Giảm ST).",
    },
]

# Bảo vật độc quyền Boss Thế Giới
GHOST_RING_TEMPLATE = {
    "uid": "nhan_quy_special",
    "id": "nhan_quy",
    "name": "Nhẫn Quỷ (Thần Khí Boss)",
    "slot": "ring",
    "rank": "SSS",
    "level": 0,
    "atk": 250,
    "hp": 1000,
    "crit": 10,
    "dodge": 5,
    "lifesteal": 20,
    "dmg_red": 20,
    "desc": (
        "Chiến lợi phẩm Top 50 Boss Thế Giới: +10% Bạo kích, +20% Hút máu, +20%"
        " Giảm sát thương!"
    ),
}

# Mẫu trang bị rơi ở Thượng Cổ Động Phủ
DONG_PHU_DROPS = [
    {
        "id": "dp_kiem_1",
        "name": "Gỉ Sét Thiết Kiếm",
        "slot": "weapon",
        "rank": "D",
        "atk": 25,
        "hp": 30,
        "crit": 1,
        "dodge": 0,
        "lifesteal": 0,
        "dmg_red": 0,
    },
    {
        "id": "dp_ao_1",
        "name": "Áo Vải Thô Sơ",
        "slot": "armor",
        "rank": "D",
        "atk": 5,
        "hp": 120,
        "crit": 0,
        "dodge": 1,
        "lifesteal": 0,
        "dmg_red": 1,
    },
    {
        "id": "dp_mu_1",
        "name": "Khăn Đầu Thanh Y",
        "slot": "helm",
        "rank": "C",
        "atk": 15,
        "hp": 200,
        "crit": 1,
        "dodge": 1,
        "lifesteal": 0,
        "dmg_red": 1,
    },
    {
        "id": "dp_giay_1",
        "name": "Giày Cỏ Tốc Hành",
        "slot": "boots",
        "rank": "C",
        "atk": 15,
        "hp": 150,
        "crit": 1,
        "dodge": 3,
        "lifesteal": 0,
        "dmg_red": 0,
    },
    {
        "id": "dp_quan_1",
        "name": "Hắc Thiết Hộ Quần",
        "slot": "pants",
        "rank": "B",
        "atk": 30,
        "hp": 420,
        "crit": 1,
        "dodge": 2,
        "lifesteal": 0,
        "dmg_red": 2,
    },
    {
        "id": "dp_kiem_2",
        "name": "Thanh Trúc Phong Vân Kiếm",
        "slot": "weapon",
        "rank": "S",
        "atk": 220,
        "hp": 300,
        "crit": 9,
        "dodge": 3,
        "lifesteal": 4,
        "dmg_red": 0,
    },
    {
        "id": "dp_nhan_2",
        "name": "Thượng Cổ Huyết Ngọc Giới",
        "slot": "ring",
        "rank": "S",
        "atk": 160,
        "hp": 500,
        "crit": 8,
        "dodge": 3,
        "lifesteal": 8,
        "dmg_red": 5,
    },
]


# ==========================================
# 3. HÀM TÍNH CHỈ SỐ & TIỆN ÍCH NHÂN VẬT
# ==========================================
def get_sub_stage(level: int) -> str:
    if level <= 3:
        return "Sơ Kỳ"
    if level <= 6:
        return "Trung Kỳ"
    if level <= 9:
        return "Hậu Kỳ"
    return "Viên Mãn"


def parse_char(row: dict) -> dict:
    if not row:
        return None
    now = time.time()
    # 1. Cập nhật hồi phục Thể Lực (1 điểm / 60 giây, tối đa 50)
    last_stam = row["last_stamina_ts"] or now
    elapsed_min = int((now - last_stam) // 60)
    cur_stam = row["stamina"]
    if elapsed_min > 0 and cur_stam < 50:
        cur_stam = min(50, cur_stam + elapsed_min)
        last_stam = now
        db.execute(
            "UPDATE characters SET stamina=?, last_stamina_ts=? WHERE id=?",
            (cur_stam, last_stam, row["id"]),
        )
    elif cur_stam >= 50:
        last_stam = now

    base_stats = json.loads(row["base_stats"])
    ability_stats = json.loads(row["ability_stats"])
    bone = json.loads(row["bone"])
    roots_inv = json.loads(row["roots_inv"])
    roots_equipped = json.loads(row["roots_equipped"])
    titles = json.loads(row["titles"])
    inventory = json.loads(row["inventory"])
    equipped_items = json.loads(row["equipped_items"])
    pills = json.loads(row["pills"])

    # 2. Tính tổng chỉ số chiến đấu
    realm_info = REALMS[min(row["realm_idx"], len(REALMS) - 1)]
    mult = realm_info["hp_mult"]

    # Từ 5 thuộc tính gốc (Linh Lực, Thể Chất, Tốc Độ, Khí Vận, Ngộ Tính)
    hp = int((150 + base_stats["the_chat"] * 25) * mult)
    mp = int((100 + base_stats["linh_luc"] * 20) * mult)
    atk = int((25 + base_stats["linh_luc"] * 6) * mult)
    crit = round(base_stats["khi_van"] * 0.25, 1)
    dodge = round(base_stats["toc_do"] * 0.3, 1)
    dmg_red = 0.0
    lifesteal = 0.0
    hp_regen = 0

    # Từ bảng Năng Lực hàng năm (+5 HP, +5 Công, +10 MP, +0.1% Giảm ST max 15%, +5 Hồi máu/lượt)
    hp += ability_stats.get("hp", 1) * 5
    atk += ability_stats.get("atk", 1) * 5
    mp += ability_stats.get("mp", 1) * 10
    ability_dmg_red = min(15.0, round(ability_stats.get("dmg_red", 1) * 0.1, 1))
    dmg_red += ability_dmg_red
    hp_regen += ability_stats.get("regen", 1) * 5

    # Từ Linh Căn Xuất Trận (Tối đa 7 ô)
    active_elements = []
    for r_id in roots_equipped[:7]:
        r_obj = next((x for x in roots_inv if x["id"] == r_id), None)
        if r_obj:
            hp += r_obj.get("hp", 0)
            atk += r_obj.get("atk", 0)
            crit += r_obj.get("crit", 0)
            active_elements.append(r_obj.get("element", "Thổ"))

    # Từ Trang Bị Đang Mặc (Đã tính cường hóa +1 -> +20)
    for slot_k, item in equipped_items.items():
        if item:
            lv = item.get("level", 0)
            enh_mult = 1.0 + (lv * 0.08)  # Mỗi cấp +8% chỉ số gốc
            hp += int(item.get("hp", 0) * enh_mult)
            atk += int(item.get("atk", 0) * enh_mult)
            crit += item.get("crit", 0)
            dodge += item.get("dodge", 0)
            lifesteal += item.get("lifesteal", 0)
            dmg_red += item.get("dmg_red", 0)
            if lv >= 20:
                lifesteal += 5  # Dòng ẩn thần khí +20: +5% Hút máu
                crit += 5

    # Từ Dị Cốt / Thiên Mệnh
    hp = int(hp * (1 + bone.get("hp_pct", 0) / 100.0))
    atk = int(atk * (1 + bone.get("atk_pct", 0) / 100.0))

    # Từ Danh Hiệu Đặc Biệt
    eq_title = row["equipped_title"]
    t_info = TITLES_INFO.get(eq_title, TITLES_INFO["Tân Thủ Tu Tiên"])
    atk = int(atk * (1 + t_info.get("atk_pct", 0) / 100.0))
    dodge += t_info.get("dodge", 0)

    # Trần Né Tránh: Mặc định 75%, nếu đeo "Vây Hạ Đại Boss" được phép vượt trần lên 85%
    dodge_cap = 85.0 if t_info.get("bypass_dodge_cap") else 75.0
    dodge = min(dodge_cap, round(dodge, 1))
    dmg_red = min(75.0, round(dmg_red, 1))
    crit = min(100.0, round(crit, 1))

    exp_req = int(realm_info["base_exp"] * (row["level"] ** 1.35))

    return {
        "id": row["id"],
        "tg_id": row["tg_id"],
        "slot": row["slot"],
        "name": row["name"],
        "gender": row["gender"],
        "age": row["age"],
        "max_age": 999999 if bone.get("immortal") else row["max_age"],
        "immortal": bone.get("immortal", False),
        "realm_idx": row["realm_idx"],
        "realm_name": f"{realm_info['name']} - {get_sub_stage(row['level'])}",
        "level": row["level"],
        "exp": row["exp"],
        "exp_req": exp_req,
        "at_bottleneck": row["level"] >= 10 and row["exp"] >= exp_req,
        "stones": row["stones"],
        "iron": row["iron"],
        "hammers": row["hammers"],
        "pity_hammer": row["pity_hammer"],
        "stamina": cur_stam,
        "next_stamina_sec": max(0, 60 - int((now - last_stam) % 60)),
        "rebirth_count": row["rebirth_count"],
        "potential_pts": row["potential_pts"],
        "can_allocate_base": bool(row["can_allocate_base"]),
        "ability_pts": row["ability_pts"],
        "breakthrough_bonus": row["breakthrough_bonus"],
        "base_stats": base_stats,
        "ability_stats": ability_stats,
        "bone": bone,
        "roots_inv": roots_inv,
        "roots_equipped": roots_equipped,
        "active_elements": active_elements,
        "titles": titles,
        "equipped_title": eq_title,
        "titles_catalog": TITLES_INFO,
        "inventory": inventory,
        "equipped_items": equipped_items,
        "pills": pills,
        "combat_stats": {
            "hp": hp,
            "mp": mp,
            "atk": atk,
            "crit": crit,
            "dodge": dodge,
            "dodge_cap": dodge_cap,
            "dmg_red": dmg_red,
            "ability_dmg_red": ability_dmg_red,
            "lifesteal": round(lifesteal, 1),
            "hp_regen": hp_regen,
            "power": int(hp * 0.5 + atk * 4 + (crit + dodge + dmg_red) * 30),
        },
    }


# ==========================================
# 4. API ENDPOINTS
# ==========================================
class CreateCharReq(BaseModel):
    tg_id: str
    slot: int
    name: str
    gender: str
    base_stats: dict


class ActionReq(BaseModel):
    char_id: str
    extra: Optional[dict] = {}


class DevBossReq(BaseModel):
    secret: str
    name: str
    hp: int
    atk: int
    def_val: int
    dodge: int
    counter: int
    lifesteal: int
    element: str


@app.get("/api/slots/{tg_id}")
def get_slots(tg_id: str):
    rows = db.execute(
        "SELECT * FROM characters WHERE tg_id=? ORDER BY slot ASC",
        (tg_id,),
        fetchall=True,
    )
    slots = {i: None for i in range(1, 6)}
    for r in rows:
        slots[r["slot"]] = parse_char(r)
    return {"slots": slots, "shop": SHOP_ITEMS}


@app.post("/api/create_char")
def create_char(req: CreateCharReq):
    if req.slot < 1 or req.slot > 5:
        raise HTTPException(400, "Slot không hợp lệ (1-5).")
    total_alloc = sum(req.base_stats.values())
    if total_alloc > 30:
        raise HTTPException(400, "Tổng điểm khởi tạo vượt quá 30 điểm!")

    char_id = f"{req.tg_id}_slot{req.slot}"
    # Thức tỉnh Dị Cốt (Có cơ hội ra Vĩnh Sinh Bất Diệt Thể)
    weights = [35, 25, 18, 10, 7, 5]
    bone = random.choices(BONES, weights=weights, k=1)[0]
    starter_root = random.choice(ROOTS_POOL[:5])

    now = time.time()
    rem_pts = max(0, 30 - total_alloc)
    ability_init = {"hp": 1, "atk": 1, "mp": 1, "dmg_red": 1, "regen": 1}

    db.execute(
        """
        INSERT OR REPLACE INTO characters VALUES (
            ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
        )
    """,
        (
            char_id,
            req.tg_id,
            req.slot,
            req.name.strip()[:20],
            req.gender,
            16,
            100,
            0,
            1,
            0,
            1500,
            10,
            2,
            0,
            50,
            now,
            0.0,
            now,
            0,
            rem_pts,
            0,
            10,
            0,
            json.dumps(req.base_stats),
            json.dumps(ability_init),
            json.dumps(bone),
            json.dumps([starter_root]),
            json.dumps([starter_root["id"]]),
            json.dumps(["Tân Thủ Tu Tiên"]),
            "Tân Thủ Tu Tiên",
            json.dumps([]),
            json.dumps({
                "weapon": None,
                "helm": None,
                "armor": None,
                "pants": None,
                "boots": None,
                "ring": None,
            }),
            json.dumps({"tho_menh": 0, "dot_pha": 0}),
            0,
            0,
        ),
    )
    row = db.execute(
        "SELECT * FROM characters WHERE id=?", (char_id,), fetchone=True
    )
    return {"char": parse_char(row)}


@app.post("/api/select_char")
def select_char(req: ActionReq):
    row = db.execute(
        "SELECT * FROM characters WHERE id=?", (req.char_id,), fetchone=True
    )
    if not row:
        raise HTTPException(404, "Không tìm thấy nhân vật!")
    now = time.time()
    last_active = row["last_active_ts"] or now
    offline_sec = int(now - last_active)
    offline_reward = None

    # Cơ chế 5: Thu hoạch Bế Quan Ngoại Tuyến (Tối đa 12 tiếng = 43200s, kích hoạt khi off >= 5 phút)
    if offline_sec >= 300:
        capped_sec = min(43200, offline_sec)
        mins = capped_sec // 60
        stones_gain = mins * (12 + row["realm_idx"] * 8)
        exp_gain = mins * (15 + row["realm_idx"] * 12)
        new_stones = row["stones"] + stones_gain
        new_exp = row["exp"] + exp_gain
        db.execute(
            "UPDATE characters SET stones=?, exp=?, last_active_ts=? WHERE"
            " id=?",
            (new_stones, new_exp, now, req.char_id),
        )
        row = db.execute(
            "SELECT * FROM characters WHERE id=?", (req.char_id,), fetchone=True
        )
        offline_reward = {
            "minutes": mins,
            "stones": stones_gain,
            "exp": exp_gain,
        }
    else:
        db.execute(
            "UPDATE characters SET last_active_ts=? WHERE id=?",
            (now, req.char_id),
        )

    return {"char": parse_char(row), "offline_reward": offline_reward}


@app.post("/api/cultivate")
def cultivate(req: ActionReq):
    row = db.execute(
        "SELECT * FROM characters WHERE id=?", (req.char_id,), fetchone=True
    )
    if not row:
        raise HTTPException(404, "Nhân vật không tồn tại.")

    now = time.time()
    # Chống spam dưới 0.42 giây (Cooldown 0.5s chuẩn)
    if now - (row["last_cultivate_ts"] or 0) < 0.42:
        raise HTTPException(
            429, "Đạo hữu vận công quá nhanh, hãy chờ 0.5 giây!"
        )

    bone = json.loads(row["bone"])
    immortal = bone.get("immortal", False)
    if not immortal and row["age"] >= row["max_age"]:
        raise HTTPException(
            400,
            "Thọ nguyên đã cạn! Hãy dùng Thọ Mệnh Đan hoặc Tọa Hóa / Niết Bàn"
            " Trùng Sinh!",
        )

    base_stats = json.loads(row["base_stats"])
    realm_idx = row["realm_idx"]
    level = row["level"]
    realm_info = REALMS[min(realm_idx, len(REALMS) - 1)]
    exp_req = int(realm_info["base_exp"] * (level**1.35))

    # Kiểm tra Bình Cảnh Cấp 10 Viên Mãn
    if level >= 10 and row["exp"] >= exp_req:
        raise HTTPException(
            400,
            "Đã chạm Bình Cảnh Viên Mãn (Cấp 10)! Hãy bấm [Đột Phá Cảnh Giới]!",
        )

    age = row["age"] + 1
    ability_pts = row["ability_pts"] + 10  # +10 điểm năng lực mỗi năm tuổi
    stones = row["stones"]

    # Tính EXP tu luyện + Kỳ Ngộ / Tâm Ma
    exp_gain = int(
        (28 + base_stats["ngo_tinh"] * 3.5 + base_stats["linh_luc"] * 2.0)
        * (1 + realm_idx * 0.25)
    )
    logs = [
        f"Năm {age} tuổi: Tĩnh tọa thổ nạp, Tu vi +{exp_gain}, nhận +10 Điểm"
        " Năng Lực."
    ]

    # Kỳ Ngộ (Dựa vào Khí Vận)
    fortune_chance = min(25.0, 2.0 + base_stats["khi_van"] * 0.2)
    if random.uniform(0, 100) < fortune_chance:
        bonus_st = random.randint(50, 200) * (realm_idx + 1)
        stones += bonus_st
        exp_gain = int(exp_gain * 1.5)
        logs.append(
            f"✨ [KỲ NGỘ] Nhặt được túi trữ vật cổ tu, nhận +{bonus_st} Linh"
            " Thạch và đại tăng tu vi!"
        )
    # Tâm Ma (Nếu không gặp kỳ ngộ, 6% tỉ lệ xuất hiện)
    elif random.uniform(0, 100) < 6.0:
        if base_stats["ngo_tinh"] >= random.randint(10, 45):
            exp_gain = int(exp_gain * 1.6)
            logs.append(
                "🧘 [TRẢM TÂM MA] Ngộ tính cao thâm, chém đứt tâm ma, đạo tâm"
                " thông suốt (+60% Tu Vi)!"
            )
        else:
            exp_gain = int(exp_gain * 0.4)
            logs.append(
                "⚠️ [TÂM MA QUẤY NHIỄU] Tâm thần bất định, hiệu suất tu luyện"
                " năm nay giảm sút!"
            )

    new_exp = row["exp"] + exp_gain
    while level < 10 and new_exp >= exp_req:
        new_exp -= exp_req
        level += 1
        exp_req = int(realm_info["base_exp"] * (level**1.35))
        logs.append(
            f"🎉 Đột phá tiểu cảnh giới: Đạt tới {realm_info['name']} Cấp"
            f" {level} ({get_sub_stage(level)})!"
        )

    if level >= 10 and new_exp >= exp_req:
        new_exp = exp_req
        logs.append(
            "⚡ Tu vi đã đạt Cấp 10 Viên Mãn! Hãy chuẩn bị Đan Dược và Độ Lôi"
            " Kiếp Đột Phá!"
        )

    db.execute(
        """
        UPDATE characters
        SET age=?, exp=?, level=?, stones=?, ability_pts=?, last_cultivate_ts=?, last_active_ts=?
        WHERE id=?
    """,
        (age, new_exp, level, stones, ability_pts, now, now, req.char_id),
    )

    updated = db.execute(
        "SELECT * FROM characters WHERE id=?", (req.char_id,), fetchone=True
    )
    return {"char": parse_char(updated), "logs": logs}


@app.post("/api/breakthrough")
def breakthrough(req: ActionReq):
    row = db.execute(
        "SELECT * FROM characters WHERE id=?", (req.char_id,), fetchone=True
    )
    if not row:
        raise HTTPException(404, "Không tìm thấy nhân vật.")
    char = parse_char(row)
    if not char["at_bottleneck"]:
        raise HTTPException(400, "Chưa đạt Cấp 10 Viên Mãn để đột phá!")
    if row["realm_idx"] >= len(REALMS) - 1:
        raise HTTPException(400, "Đạo hữu đã đạt đỉnh phong Độ Kiếp Chân Tiên!")

    # Tỉ lệ cơ bản 80% + Đan dược hỗ trợ (+10%)
    chance = min(100, 80 + row["breakthrough_bonus"])
    roll = random.uniform(0, 100)
    logs = []

    if roll > chance:
        new_exp = int(row["exp"] * 0.85)
        db.execute(
            "UPDATE characters SET exp=?, breakthrough_bonus=0 WHERE id=?",
            (new_exp, req.char_id),
        )
        logs.append(
            f"💥 [XUNG QUAN THẤT BẠI] Tỉ lệ {chance}% nhưng khí huyết nghịch"
            " loạn, tụt 15% Tu Vi!"
        )
        updated = db.execute(
            "SELECT * FROM characters WHERE id=?", (req.char_id,), fetchone=True
        )
        return {"char": parse_char(updated), "success": False, "logs": logs}

    # Vượt 3 Đạo Thiên Lôi Kiếp
    max_hp = char["combat_stats"]["hp"]
    dmg_red = char["combat_stats"]["dmg_red"] / 100.0
    cur_hp = max_hp
    logs.append(
        f"🌩️ [ĐỘ KIẾP] Xung quan thành công ({chance}%), Cửu Thiên Lôi Kiếp"
        " giáng xuống 3 đạo thiên lôi!"
    )

    for strike in range(1, 4):
        raw_pct = random.uniform(0.22, 0.34)
        strike_dmg = int(max_hp * raw_pct * (1.0 - dmg_red * 0.7))
        cur_hp -= strike_dmg
        logs.append(
            f"⚡ Đạo Thiên Lôi thứ {strike}: Giáng xuống gây {strike_dmg} sát"
            f" thương! (HP còn: {max(0, cur_hp)}/{max_hp})"
        )

    if cur_hp <= 0:
        new_exp = int(row["exp"] * 0.85)
        db.execute(
            "UPDATE characters SET exp=?, breakthrough_bonus=0 WHERE id=?",
            (new_exp, req.char_id),
        )
        logs.append(
            "💀 Không chống nổi đạo Thiên Lôi thứ 3! Độ kiếp thất bại, kinh"
            " mạch tổn thương tụt 15% Tu Vi!"
        )
        updated = db.execute(
            "SELECT * FROM characters WHERE id=?", (req.char_id,), fetchone=True
        )
        return {"char": parse_char(updated), "success": False, "logs": logs}

    # Độ kiếp thành công -> Lên đại cảnh giới mới
    new_realm_idx = row["realm_idx"] + 1
    new_realm = REALMS[new_realm_idx]
    new_max_age = max(row["max_age"], new_realm["max_age"])

    db.execute(
        """
        UPDATE characters
        SET realm_idx=?, level=1, exp=0, max_age=?, breakthrough_bonus=0
        WHERE id=?
    """,
        (new_realm_idx, new_max_age, req.char_id),
    )

    logs.append(
        "🌈 [ĐỘ KIẾP THÀNH CÔNG] Vượt qua 3 đạo Thiên Lôi, chính thức bước vào"
        f" {new_realm['name']}! Thọ nguyên tăng lên {new_max_age} năm!"
    )
    updated = db.execute(
        "SELECT * FROM characters WHERE id=?", (req.char_id,), fetchone=True
    )
    return {"char": parse_char(updated), "success": True, "logs": logs}


@app.post("/api/rebirth")
def rebirth(req: ActionReq):
    row = db.execute(
        "SELECT * FROM characters WHERE id=?", (req.char_id,), fetchone=True
    )
    if not row:
        raise HTTPException(404, "Không tìm thấy nhân vật.")

    bone = json.loads(row["bone"])
    immortal = bone.get("immortal", False)
    age = row["age"]
    max_age = row["max_age"]

    # Quy tắc: Đủ 500 tuổi -> Niết Bàn (+15 điểm). Chưa đủ 500 tuổi nhưng đã cạn thọ nguyên -> Tọa Hóa (+5 điểm)
    if age >= 500:
        bonus_pts = 15
        msg = (
            f"🔥 [NIẾT BÀN TRÙNG SINH] Đạo hữu ở tuổi {age} viên tịch chuyển"
            " sinh, nhận +15 Điểm Tiềm Năng và mở khóa bảng Tiên Căn!"
        )
    elif not immortal and age >= max_age:
        bonus_pts = 5
        msg = (
            f"🕯️ [TỌA HÓA CHUYỂN SINH] Thọ nguyên cạn kiệt trước 500 tuổi ({age}"
            " tuổi), chuyển sinh nhận +5 Điểm Tiềm Năng an ủi!"
        )
    else:
        raise HTTPException(
            400, "Phải đạt đủ 500 tuổi mới được phép Niết Bàn Trùng Sinh!"
        )

    new_rebirth = row["rebirth_count"] + 1
    new_pot = row["potential_pts"] + bonus_pts
    titles = json.loads(row["titles"])
    if age >= 500 and "Luân Hồi Giả" not in titles:
        titles.append("Luân Hồi Giả")

    ability_reset = {"hp": 1, "atk": 1, "mp": 1, "dmg_red": 1, "regen": 1}

    db.execute(
        """
        UPDATE characters
        SET age=1, max_age=100, realm_idx=0, level=1, exp=0,
            rebirth_count=?, potential_pts=?, can_allocate_base=1,
            ability_pts=10, ability_stats=?, titles=?
        WHERE id=?
    """,
        (
            new_rebirth,
            new_pot,
            json.dumps(ability_reset),
            json.dumps(titles),
            req.char_id,
        ),
    )

    updated = db.execute(
        "SELECT * FROM characters WHERE id=?", (req.char_id,), fetchone=True
    )
    return {"char": parse_char(updated), "message": msg}


@app.post("/api/allocate_base")
def allocate_base(req: ActionReq):
    row = db.execute(
        "SELECT * FROM characters WHERE id=?", (req.char_id,), fetchone=True
    )
    if not row:
        raise HTTPException(404, "Không tìm thấy nhân vật.")
    if not row["can_allocate_base"]:
        raise HTTPException(
            400,
            "Bảng 5 thuộc tính gốc chỉ mở sau khi Niết Bàn Trùng Sinh! Hãy"
            " hoàn tất phân bổ hoặc chờ lần Niết Bàn tiếp theo.",
        )

    action = req.extra.get("action")  # "add", "reset", "lock"
    base_stats = json.loads(row["base_stats"])
    pot = row["potential_pts"]

    if action == "reset":
        # Tẩy Tủy: Thu hồi toàn bộ điểm đã cộng về quỹ điểm chung
        total_pool = pot + sum(base_stats.values())
        for k in base_stats:
            base_stats[k] = 0
        db.execute(
            "UPDATE characters SET base_stats=?, potential_pts=? WHERE id=?",
            (json.dumps(base_stats), total_pool, req.char_id),
        )
    elif action == "add":
        stat_key = req.extra.get("stat")
        amount = int(req.extra.get("amount", 1))
        if stat_key not in base_stats:
            raise HTTPException(400, "Thuộc tính không hợp lệ.")
        if pot < amount:
            raise HTTPException(400, "Không đủ Điểm Tiềm Năng!")
        if base_stats[stat_key] + amount > 100:
            raise HTTPException(400, "Mỗi thuộc tính gốc tối đa 100 điểm!")
        base_stats[stat_key] += amount
        pot -= amount
        db.execute(
            "UPDATE characters SET base_stats=?, potential_pts=? WHERE id=?",
            (json.dumps(base_stats), pot, req.char_id),
        )
    elif action == "lock":
        db.execute(
            "UPDATE characters SET can_allocate_base=0 WHERE id=?",
            (req.char_id,),
        )

    updated = db.execute(
        "SELECT * FROM characters WHERE id=?", (req.char_id,), fetchone=True
    )
    return {"char": parse_char(updated)}


@app.post("/api/allocate_ability")
def allocate_ability(req: ActionReq):
    row = db.execute(
        "SELECT * FROM characters WHERE id=?", (req.char_id,), fetchone=True
    )
    if not row:
        raise HTTPException(404, "Không tìm thấy nhân vật.")

    stat_key = req.extra.get("stat")  # hp, atk, mp, dmg_red, regen
    amount = int(req.extra.get("amount", 1))
    ability_stats = json.loads(row["ability_stats"])
    pts = row["ability_pts"]

    if stat_key not in ability_stats or amount <= 0:
        raise HTTPException(400, "Mục năng lực không hợp lệ.")
    if pts < amount:
        raise HTTPException(400, "Không đủ Điểm Năng Lực!")

    if stat_key == "dmg_red":
        if ability_stats["dmg_red"] + amount > 150:  # 150 * 0.1% = 15.0% max
            raise HTTPException(
                400, "Giảm Sát Thương trong bảng Năng Lực đã đạt tối đa 15%!"
            )

    ability_stats[stat_key] += amount
    pts -= amount
    db.execute(
        "UPDATE characters SET ability_stats=?, ability_pts=? WHERE id=?",
        (json.dumps(ability_stats), pts, req.char_id),
    )
    updated = db.execute(
        "SELECT * FROM characters WHERE id=?", (req.char_id,), fetchone=True
    )
    return {"char": parse_char(updated)}


@app.post("/api/toggle_root")
def toggle_root(req: ActionReq):
    row = db.execute(
        "SELECT * FROM characters WHERE id=?", (req.char_id,), fetchone=True
    )
    if not row:
        raise HTTPException(404, "Không tìm thấy nhân vật.")
    root_id = req.extra.get("root_id")
    roots_inv = json.loads(row["roots_inv"])
    roots_eq = json.loads(row["roots_equipped"])

    if not any(r["id"] == root_id for r in roots_inv):
        raise HTTPException(400, "Không sở hữu Linh Căn này trong kho!")

    if root_id in roots_eq:
        if len(roots_eq) <= 1:
            raise HTTPException(
                400, "Phải giữ ít nhất 1 Linh Căn xuất trận hộ thể!"
            )
        roots_eq.remove(root_id)
    else:
        if len(roots_eq) >= 7:
            raise HTTPException(
                400,
                "Tối đa chỉ được chọn 7 Linh Căn xuất trận! Hãy tháo bớt 1 cái"
                " trước.",
            )
        roots_eq.append(root_id)

    db.execute(
        "UPDATE characters SET roots_equipped=? WHERE id=?",
        (json.dumps(roots_eq), req.char_id),
    )
    updated = db.execute(
        "SELECT * FROM characters WHERE id=?", (req.char_id,), fetchone=True
    )
    return {"char": parse_char(updated)}


@app.post("/api/equip_title")
def equip_title(req: ActionReq):
    row = db.execute(
        "SELECT * FROM characters WHERE id=?", (req.char_id,), fetchone=True
    )
    title = req.extra.get("title")
    titles = json.loads(row["titles"])
    if title not in titles:
        raise HTTPException(400, "Chưa mở khóa danh hiệu này!")
    db.execute(
        "UPDATE characters SET equipped_title=? WHERE id=?",
        (title, req.char_id),
    )
    updated = db.execute(
        "SELECT * FROM characters WHERE id=?", (req.char_id,), fetchone=True
    )
    return {"char": parse_char(updated)}


@app.post("/api/shop_buy")
def shop_buy(req: ActionReq):
    row = db.execute(
        "SELECT * FROM characters WHERE id=?", (req.char_id,), fetchone=True
    )
    if not row:
        raise HTTPException(404, "Không tìm thấy nhân vật.")
    item_id = req.extra.get("item_id")
    shop_item = next((x for x in SHOP_ITEMS if x["id"] == item_id), None)
    if not shop_item:
        raise HTTPException(404, "Vật phẩm không có trong Vạn Bảo Các.")

    if row["stones"] < shop_item["price"]:
        raise HTTPException(400, "Không đủ Linh Thạch!")

    stones = row["stones"] - shop_item["price"]
    itype = shop_item["type"]
    msg = ""

    if itype == "gacha":
        # Gacha Linh Căn 1.000 LT - Trùng lặp KHÔNG hoàn trả
        roots_inv = json.loads(row["roots_inv"])
        weights = [22, 18, 16, 13, 11, 8, 5, 4, 2, 1]
        rolled = random.choices(ROOTS_POOL, weights=weights, k=1)[0]
        if any(r["id"] == rolled["id"] for r in roots_inv):
            msg = (
                f"🎲 Quay ra [{rolled['name']}] (Phẩm {rolled['rank']}) ĐÃ CÓ"
                " TRONG KHO! Tiêu hao 1.000 Linh Thạch (Không hoàn trả)."
            )
        else:
            roots_inv.append(rolled)
            msg = (
                f"🎉 Chúc mừng! Khai mở Linh Căn mới: [{rolled['name']}] (Phẩm"
                f" {rolled['rank']}) đã lưu vào Kho Linh Căn!"
            )
        db.execute(
            "UPDATE characters SET stones=?, roots_inv=? WHERE id=?",
            (stones, json.dumps(roots_inv), req.char_id),
        )

    elif itype == "hammer":
        hammers = row["hammers"] + 1
        msg = "🔨 Đã mua +1 Thiên Công Thần Chùy!"
        db.execute(
            "UPDATE characters SET stones=?, hammers=? WHERE id=?",
            (stones, hammers, req.char_id),
        )

    elif itype == "pill_age":
        pills = json.loads(row["pills"])
        pills["tho_menh"] = pills.get("tho_menh", 0) + 1
        msg = "🍑 Đã mua +1 Thọ Mệnh Đan (Vào túi Đan Dược bấm dùng để +50 năm tuổi thọ)!"
        db.execute(
            "UPDATE characters SET stones=?, pills=? WHERE id=?",
            (stones, json.dumps(pills), req.char_id),
        )

    elif itype == "pill_break":
        pills = json.loads(row["pills"])
        pills["dot_pha"] = pills.get("dot_pha", 0) + 1
        msg = (
            f"💊 Đã mua +1 {shop_item['name']} (Vào túi Đan Dược dùng để +10%"
            " tỉ lệ Đột Phá)!"
        )
        db.execute(
            "UPDATE characters SET stones=?, pills=? WHERE id=?",
            (stones, json.dumps(pills), req.char_id),
        )

    elif itype == "pill_mp":
        ab = json.loads(row["ability_stats"])
        ab["mp"] += 2
        msg = "💧 Đã uống Cửu Chuyển Hồi Linh Đan: Vĩnh viễn +20 MP!"
        db.execute(
            "UPDATE characters SET stones=?, ability_stats=? WHERE id=?",
            (stones, json.dumps(ab), req.char_id),
        )

    elif itype == "pill_hp":
        ab = json.loads(row["ability_stats"])
        ab["hp"] += 5
        msg = "❤️ Đã uống Hồi Xuân Chân Đan: Vĩnh viễn +25 HP!"
        db.execute(
            "UPDATE characters SET stones=?, ability_stats=? WHERE id=?",
            (stones, json.dumps(ab), req.char_id),
        )

    elif itype == "equip":
        inv = json.loads(row["inventory"])
        new_eq = {
            "uid": f"eq_{int(time.time()*1000)}_{random.randint(100,999)}",
            "id": shop_item["id"],
            "name": shop_item["name"],
            "slot": shop_item["slot"],
            "rank": shop_item["rank"],
            "level": 0,
            "atk": shop_item["atk"],
            "hp": shop_item["hp"],
            "crit": shop_item["crit"],
            "dodge": shop_item["dodge"],
            "lifesteal": shop_item["lifesteal"],
            "dmg_red": shop_item["dmg_red"],
            "desc": shop_item["desc"],
        }
        inv.append(new_eq)
        msg = f"🗡️ Đã mua trang bị [{shop_item['name']}] đưa vào Hành Trang!"
        db.execute(
            "UPDATE characters SET stones=?, inventory=? WHERE id=?",
            (stones, json.dumps(inv), req.char_id),
        )

    updated = db.execute(
        "SELECT * FROM characters WHERE id=?", (req.char_id,), fetchone=True
    )
    return {"char": parse_char(updated), "message": msg}


@app.post("/api/use_pill")
def use_pill(req: ActionReq):
    row = db.execute(
        "SELECT * FROM characters WHERE id=?", (req.char_id,), fetchone=True
    )
    pill_type = req.extra.get("pill_type")  # "tho_menh" or "dot_pha"
    pills = json.loads(row["pills"])

    if pills.get(pill_type, 0) <= 0:
        raise HTTPException(400, "Bạn không có đan dược này trong túi!")

    if pill_type == "tho_menh":
        pills["tho_menh"] -= 1
        new_max_age = row["max_age"] + 50
        db.execute(
            "UPDATE characters SET max_age=?, pills=? WHERE id=?",
            (new_max_age, json.dumps(pills), req.char_id),
        )
        msg = "🍑 Đã phục dụng Thọ Mệnh Đan: Thọ nguyên tối đa tăng thêm +50 năm!"
    elif pill_type == "dot_pha":
        if row["breakthrough_bonus"] >= 10:
            raise HTTPException(
                400, "Đã cắn Đan Đột Phá cho bình cảnh này rồi (+10% tối đa)!"
            )
        pills["dot_pha"] -= 1
        db.execute(
            "UPDATE characters SET breakthrough_bonus=10, pills=? WHERE id=?",
            (json.dumps(pills), req.char_id),
        )
        msg = (
            "💊 Đã phục dụng Đan Đột Phá: Tỉ lệ đột phá bình cảnh tăng từ 80%"
            " lên 90%!"
        )
    else:
        raise HTTPException(400, "Loại đan dược không hợp lệ.")

    updated = db.execute(
        "SELECT * FROM characters WHERE id=?", (req.char_id,), fetchone=True
    )
    return {"char": parse_char(updated), "message": msg}


@app.post("/api/item_action")
def item_action(req: ActionReq):
    row = db.execute(
        "SELECT * FROM characters WHERE id=?", (req.char_id,), fetchone=True
    )
    if not row:
        raise HTTPException(404, "Không tìm thấy nhân vật.")

    act = req.extra.get(
        "action"
    )  # "equip", "unequip", "enhance", "sell_trash", "salvage_high"
    inv = json.loads(row["inventory"])
    eq = json.loads(row["equipped_items"])
    stones = row["stones"]
    iron = row["iron"]
    hammers = row["hammers"]
    msg = ""

    if act == "equip":
        uid = req.extra.get("uid")
        item = next((x for x in inv if x["uid"] == uid), None)
        if not item:
            raise HTTPException(404, "Không tìm thấy trang bị trong túi.")
        slot = item["slot"]
        if eq.get(slot):
            inv.append(eq[slot])
        eq[slot] = item
        inv = [x for x in inv if x["uid"] != uid]
        msg = f"Đã trang bị [{item['name']} (+{item.get('level',0)})]!"

    elif act == "unequip":
        slot = req.extra.get("slot")
        if eq.get(slot):
            inv.append(eq[slot])
            msg = f"Đã tháo [{eq[slot]['name']}] về túi đồ."
            eq[slot] = None

    elif act == "enhance":
        # Cường hóa trang bị (+1 đến +20) bằng Thiên Công Thần Chùy + Linh Thiết
        target_type = req.extra.get("target")  # "equipped" or "inv"
        slot_or_uid = req.extra.get("key")
        item = (
            eq.get(slot_or_uid)
            if target_type == "equipped"
            else next((x for x in inv if x["uid"] == slot_or_uid), None)
        )
        if not item:
            raise HTTPException(404, "Không tìm thấy trang bị cần đập búa!")
        lv = item.get("level", 0)
        if lv >= 20:
            raise HTTPException(
                400, "Trang bị này đã đạt cấp Thần Khí +20 tối đa!"
            )
        if hammers < 1:
            raise HTTPException(400, "Cần 1 Thiên Công Thần Chùy để cường hóa!")
        iron_cost = 1 + (lv // 5)
        if iron < iron_cost:
            raise HTTPException(
                400,
                f"Cần {iron_cost} Linh Thiết để rèn cấp này (Tách đồ phẩm B/A"
                " để lấy Linh Thiết)!",
            )

        hammers -= 1
        iron -= iron_cost
        # Mốc tỉ lệ: +1..+5 (100%), +6..+10 (70%), +11..+15 (40% rớt 1 cấp), +16..+20 (15% tụt về +15)
        if lv < 5:
            rate = 100
        elif lv < 10:
            rate = 70
        elif lv < 15:
            rate = 40
        else:
            rate = 15

        if random.uniform(0, 100) <= rate:
            item["level"] = lv + 1
            msg = (
                f"🔨✨ RÈN THÀNH CÔNG! [{item['name']}] tăng lên"
                f" +{item['level']} (Tỉ lệ {rate}%)!"
            )
        else:
            if lv >= 15:
                item["level"] = 15
                msg = (
                    f"💥 Rèn thất bại ({rate}%)! Nhờ mốc bảo hộ Thần Khí, trang"
                    " bị giữ ở mức +15."
                )
            elif lv >= 10:
                item["level"] = lv - 1
                msg = (
                    f"💥 Rèn thất bại ({rate}%)! [{item['name']}] bị giảm 1 cấp"
                    f" xuống +{item['level']}."
                )
            else:
                msg = (
                    f"💨 Rèn thất bại ({rate}%)! May mắn trang bị giữ nguyên"
                    f" cấp +{lv}."
                )

    elif act == "sell_trash":
        # Bán nhanh toàn bộ trang bị phẩm D và C trong túi
        sold_cnt = 0
        gained_st = 0
        rem = []
        for x in inv:
            if x.get("rank") in ["D", "C"]:
                sold_cnt += 1
                gained_st += 80 if x.get("rank") == "D" else 180
            else:
                rem.append(x)
        inv = rem
        stones += gained_st
        msg = (
            f"💰 Đã bán nhanh {sold_cnt} trang bị phẩm D/C, thu về +{gained_st}"
            " Linh Thạch!"
        )

    elif act == "salvage_high":
        # Tách trang bị phẩm B và A lấy Linh Thiết đập đồ
        sal_cnt = 0
        gained_iron = 0
        rem = []
        for x in inv:
            if x.get("rank") in ["B", "A"]:
                sal_cnt += 1
                gained_iron += 3 if x.get("rank") == "B" else 7
            else:
                rem.append(x)
        inv = rem
        iron += gained_iron
        msg = (
            f"⚒️ Đã phân giải {sal_cnt} trang bị phẩm B/A, thu về"
            f" +{gained_iron} Linh Thiết!"
        )

    db.execute(
        """
        UPDATE characters
        SET inventory=?, equipped_items=?, stones=?, iron=?, hammers=?
        WHERE id=?
    """,
        (
            json.dumps(inv),
            json.dumps(eq),
            stones,
            iron,
            hammers,
            req.char_id,
        ),
    )

    updated = db.execute(
        "SELECT * FROM characters WHERE id=?", (req.char_id,), fetchone=True
    )
    return {"char": parse_char(updated), "message": msg}


@app.post("/api/explore")
def explore(req: ActionReq):
    row = db.execute(
        "SELECT * FROM characters WHERE id=?", (req.char_id,), fetchone=True
    )
    if not row:
        raise HTTPException(404, "Không tìm thấy nhân vật.")
    char = parse_char(row)
    zone = req.extra.get("zone")  # "yeu_thu" (5), "bi_canh" (10), "dong_phu" (15)

    costs = {"yeu_thu": 5, "bi_canh": 10, "dong_phu": 15}
    cost = costs.get(zone, 5)
    if char["stamina"] < cost:
        raise HTTPException(
            400,
            f"Không đủ Thể Lực (Cần {cost} điểm)! Thể lực tự hồi 1 điểm mỗi 1"
            " phút.",
        )

    stam = char["stamina"] - cost
    stones = row["stones"]
    hammers = row["hammers"]
    pity = row["pity_hammer"]
    pills = json.loads(row["pills"])
    inv = json.loads(row["inventory"])
    iron = row["iron"]
    logs = []

    if zone == "yeu_thu":
        # Săn Yêu Thú Loạn Tinh Hải: Cày Linh Thạch + Bảo hiểm 50 lượt chắc chắn rơi Búa
        st_gain = random.randint(150, 350) * (row["realm_idx"] + 1)
        stones += st_gain
        pity += 1
        logs.append(
            f"🐉 Trảm sát Hải Thú Loạn Tinh Hải (-5 Thể lực): Thu hoạch +{st_gain}"
            " Linh Thạch."
        )
        if pity >= 50 or random.uniform(0, 100) <= 2.0:
            hammers += 1
            pity = 0
            logs.append(
                "🔨 [BẢO VẬT XUẤT THẾ] Nhận được +1 Thiên Công Thần Chùy (Reset"
                " bảo hiểm 0/50)!"
            )

    elif zone == "bi_canh":
        # Cổ Ma Bí Cảnh (10 Thể lực): Rơi Thảo dược, Thọ Mệnh Đan, Đan Đột Phá
        st_gain = random.randint(100, 220)
        stones += st_gain
        roll = random.uniform(0, 100)
        if roll < 30:
            pills["tho_menh"] = pills.get("tho_menh", 0) + 1
            logs.append(
                "🍑 Thám hiểm Cổ Ma Bí Cảnh (-10 Thể lực): Nhặt được 1 [Thọ"
                f" Mệnh Đan] (+50 năm thọ nguyên) & +{st_gain} LT!"
            )
        elif roll < 65:
            pills["dot_pha"] = pills.get("dot_pha", 0) + 1
            logs.append(
                "💊 Thám hiểm Cổ Ma Bí Cảnh (-10 Thể lực): Nhặt được 1 [Đan Đột"
                f" Phá] (+10% tỉ lệ đột phá) & +{st_gain} LT!"
            )
        else:
            iron += 3
            logs.append(
                "🌿 Thám hiểm Cổ Ma Bí Cảnh (-10 Thể lực): Thu thập linh thảo &"
                f" khoáng thạch (+3 Linh Thiết, +{st_gain} LT)!"
            )

    elif zone == "dong_phu":
        # Thượng Cổ Động Phủ (15 Thể lực): Rơi Trang Bị (Kiếm, Giáp, Nhẫn, Giày...)
        weights = [25, 25, 18, 15, 10, 4, 3]
        drop = random.choices(DONG_PHU_DROPS, weights=weights, k=1)[0]
        new_eq = {
            "uid": f"dp_{int(time.time()*1000)}_{random.randint(100,999)}",
            "id": drop["id"],
            "name": drop["name"],
            "slot": drop["slot"],
            "rank": drop["rank"],
            "level": 0,
            "atk": drop["atk"],
            "hp": drop["hp"],
            "crit": drop["crit"],
            "dodge": drop["dodge"],
            "lifesteal": drop["lifesteal"],
            "dmg_red": drop["dmg_red"],
            "desc": f"Cổ vật khai quật từ Thượng Cổ Động Phủ (Phẩm {drop['rank']}).",
        }
        inv.append(new_eq)
        logs.append(
            "🏛️ Khai quật Thượng Cổ Động Phủ (-15 Thể lực): Nhặt được trang bị"
            f" [{drop['name']}] (Phẩm {drop['rank']})!"
        )

    db.execute(
        """
        UPDATE characters
        SET stamina=?, stones=?, hammers=?, pity_hammer=?, pills=?, inventory=?, iron=?
        WHERE id=?
    """,
        (
            stam,
            stones,
            hammers,
            pity,
            json.dumps(pills),
            json.dumps(inv),
            iron,
            req.char_id,
        ),
    )

    updated = db.execute(
        "SELECT * FROM characters WHERE id=?", (req.char_id,), fetchone=True
    )
    return {"char": parse_char(updated), "logs": logs}


# ==========================================
# 5. BOSS THẾ GIỚI, DEV PANEL & LÔI ĐÀI PVP
# ==========================================
@app.get("/api/boss")
def get_boss():
    boss = db.execute(
        "SELECT * FROM world_boss ORDER BY id DESC LIMIT 1", fetchone=True
    )
    board = json.loads(boss["damage_board"]) if boss else {}
    sorted_board = sorted(
        board.values(), key=lambda x: x["damage"], reverse=True
    )[:50]
    return {"boss": boss, "leaderboard": sorted_board}


@app.post("/api/dev_spawn_boss")
def dev_spawn_boss(req: DevBossReq):
    if req.secret != "DevGame":
        raise HTTPException(403, "Mật lệnh DEV không chính xác!")
    db.execute(
        """
        INSERT INTO world_boss (name, max_hp, hp, atk, def_val, dodge, counter, lifesteal, element, active, damage_board)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, '{}')
    """,
        (
            req.name,
            req.hp,
            req.hp,
            req.atk,
            req.def_val,
            req.dodge,
            req.counter,
            req.lifesteal,
            req.element,
        ),
    )
    return get_boss()


@app.post("/api/attack_boss")
def attack_boss(req: ActionReq):
    row = db.execute(
        "SELECT * FROM characters WHERE id=?", (req.char_id,), fetchone=True
    )
    boss = db.execute(
        "SELECT * FROM world_boss ORDER BY id DESC LIMIT 1", fetchone=True
    )
    if not row or not boss:
        raise HTTPException(404, "Dữ liệu không tồn tại.")
    if not boss["active"] or boss["hp"] <= 0:
        raise HTTPException(
            400, "Boss Thế Giới đã bị tiêu diệt! Hãy chờ DEV triệu hồi Boss mới."
        )

    char = parse_char(row)
    attempts = row["boss_attempts"] if row["boss_id_joined"] == boss["id"] else 0
    if attempts >= 5:
        raise HTTPException(
            400, "Bạn đã dùng hết 5/5 lượt khiêu chiến cho đời Boss này!"
        )

    c_stats = char["combat_stats"]
    p_hp = c_stats["hp"]
    b_hp = boss["hp"]
    total_dmg = 0
    logs = []

    # Xét tương khắc Ngũ Hành giữa Linh Căn người chơi và Hệ của Boss
    elem_mult = 1.0
    boss_elem = boss.get("element", "Hỏa")
    for el in char["active_elements"]:
        if el == "Hỗn Độn" or ELEMENT_COUNTER.get(el) == boss_elem:
            elem_mult = 1.20
            break
        elif ELEMENT_COUNTER.get(boss_elem) == el:
            elem_mult = 0.85

    if elem_mult > 1.0:
        logs.append(
            f"☯️ [NGŨ HÀNH TƯƠNG KHẮC] Linh căn của bạn khắc chế hệ {boss_elem}"
            " của Boss: +20% Sát thương!"
        )

    # Giao chiến tối đa 8 hiệp
    for turn in range(1, 9):
        if p_hp <= 0 or b_hp <= 0:
            break
        # Người chơi tấn công
        if random.uniform(0, 100) > boss["dodge"]:
            is_crit = random.uniform(0, 100) <= c_stats["crit"]
            raw = max(10, c_stats["atk"] - boss["def_val"])
            dmg = int(raw * (1.8 if is_crit else 1.0) * elem_mult)
            b_hp -= dmg
            total_dmg += dmg
            heal = int(dmg * (c_stats["lifesteal"] / 100.0)) + c_stats["hp_regen"]
            p_hp = min(c_stats["hp"], p_hp + heal)
            logs.append(
                f"Hiệp {turn}: Bạn giáng đòn {'BẠO KÍCH ' if is_crit else ''}gây"
                f" {dmg} ST lên {boss['name']} (Hồi +{heal} HP)."
            )
        else:
            logs.append(f"Hiệp {turn}: {boss['name']} thân pháp quỷ mị né được đòn!")

        if b_hp <= 0:
            break

        # Boss phản công
        if random.uniform(0, 100) > c_stats["dodge"]:
            b_dmg = int(
                max(15, boss["atk"] * (1.0 - c_stats["dmg_red"] / 100.0))
            )
            p_hp -= b_dmg
            logs.append(f"👹 {boss['name']} vung trảo gây {b_dmg} sát thương!")
        else:
            logs.append(f"💨 Bạn thi triển thân pháp né tránh thành công đòn của Boss!")

    new_b_hp = max(0, b_hp)
    active = 0 if new_b_hp == 0 else 1
    board = json.loads(boss["damage_board"])
    entry = board.get(
        req.char_id,
        {"char_id": req.char_id, "name": char["name"], "damage": 0},
    )
    entry["damage"] += total_dmg
    entry["name"] = char["name"]
    board[req.char_id] = entry

    stones_reward = int(total_dmg * 0.2) + 150
    new_stones = row["stones"] + stones_reward
    db.execute(
        "UPDATE characters SET stones=?, boss_attempts=?, boss_id_joined=?"
        " WHERE id=?",
        (new_stones, attempts + 1, boss["id"], req.char_id),
    )

    # Nếu Boss bị kết liễu -> Phát thưởng Top 10 Danh Hiệu & 10% cơ hội Nhẫn Quỷ cho Top 50
    if new_b_hp == 0 and boss["active"] == 1:
        sorted_p = sorted(
            board.values(), key=lambda x: x["damage"], reverse=True
        )
        top10_ids = [x["char_id"] for x in sorted_p[:10]]
        top50_ids = [x["char_id"] for x in sorted_p[:50]]
        drop_ghost_ring = random.uniform(0, 100) <= 10.0  # 10% xác suất toàn Top 50

        for cid in top50_ids:
            c_row = db.execute(
                "SELECT * FROM characters WHERE id=?", (cid,), fetchone=True
            )
            if not c_row:
                continue
            c_titles = json.loads(c_row["titles"])
            c_inv = json.loads(c_row["inventory"])
            if cid in top10_ids and "Vây Hạ Đại Boss" not in c_titles:
                c_titles.append("Vây Hạ Đại Boss")
            if drop_ghost_ring:
                ring_copy = dict(GHOST_RING_TEMPLATE)
                ring_copy["uid"] = (
                    f"ghost_ring_{int(time.time()*1000)}_{random.randint(10,99)}"
                )
                c_inv.append(ring_copy)
            db.execute(
                "UPDATE characters SET titles=?, inventory=? WHERE id=?",
                (json.dumps(c_titles), json.dumps(c_inv), cid),
            )

        logs.append(
            "🏆 [BOSS THẾ GIỚI ĐÃ BỊ TIÊU DIỆT] Top 10 BXH nhận danh hiệu [Vây"
            " Hạ Đại Boss] (+10% Né vượt trần)!"
        )
        if drop_ghost_ring:
            logs.append(
                "💍🔥 [THẦN KHÍ GIÁNG THẾ - 10% NỔ] Toàn bộ Top 50 BXH sát"
                " thương đã nhận được [Nhẫn Quỷ]!"
            )
        else:
            logs.append(
                "💨 Lần này sát khí tan biến, Nhẫn Quỷ (10% tỉ lệ) đã không"
                " xuất hiện."
            )

    db.execute(
        "UPDATE world_boss SET hp=?, active=?, damage_board=? WHERE id=?",
        (new_b_hp, active, json.dumps(board), boss["id"]),
    )

    updated_char = db.execute(
        "SELECT * FROM characters WHERE id=?", (req.char_id,), fetchone=True
    )
    return {
        "char": parse_char(updated_char),
        "boss_data": get_boss(),
        "logs": logs,
    }


@app.get("/api/arena_list/{char_id}")
def arena_list(char_id: str):
    rows = db.execute(
        "SELECT * FROM characters WHERE id != ? LIMIT 30",
        (char_id,),
        fetchall=True,
    )
    opponents = []
    for r in rows:
        c = parse_char(r)
        opponents.append({
            "id": c["id"],
            "name": c["name"],
            "realm_name": c["realm_name"],
            "power": c["combat_stats"]["power"],
            "equipped_title": c["equipped_title"],
        })
    opponents.sort(key=lambda x: x["power"], reverse=True)
    return {"opponents": opponents[:15]}


@app.post("/api/arena_fight")
def arena_fight(req: ActionReq):
    p_row = db.execute(
        "SELECT * FROM characters WHERE id=?", (req.char_id,), fetchone=True
    )
    e_id = req.extra.get("target_id")
    e_row = db.execute(
        "SELECT * FROM characters WHERE id=?", (e_id,), fetchone=True
    )
    if not p_row or not e_row:
        raise HTTPException(404, "Không tìm thấy đối thủ.")

    p = parse_char(p_row)
    e = parse_char(e_row)
    ps, es = p["combat_stats"], e["combat_stats"]
    p_hp, e_hp = ps["hp"], es["hp"]
    logs = [f"⚔️ Giao chiến Lôi Đài: [{p['name']}] VS [{e['name']}]!"]

    for turn in range(1, 10):
        if p_hp <= 0 or e_hp <= 0:
            break
        if random.uniform(0, 100) > es["dodge"]:
            dmg = int(max(10, ps["atk"] * (1.0 - es["dmg_red"] / 100.0)))
            e_hp -= dmg
            logs.append(f"Hiệp {turn}: Bạn tung chiêu gây {dmg} ST lên {e['name']}.")
        else:
            logs.append(f"Hiệp {turn}: {e['name']} né được đòn của bạn!")

        if e_hp <= 0:
            break

        if random.uniform(0, 100) > ps["dodge"]:
            edmg = int(max(10, es["atk"] * (1.0 - ps["dmg_red"] / 100.0)))
            p_hp -= edmg
            logs.append(f"Hiệp {turn}: {e['name']} phản kích gây {edmg} ST.")
        else:
            logs.append(f"Hiệp {turn}: Bạn né được đòn tấn công của {e['name']}!")

    win = p_hp >= e_hp
    reward = 250 if win else 60
    db.execute(
        "UPDATE characters SET stones = stones + ? WHERE id=?",
        (reward, req.char_id),
    )
    logs.append(
        f"🏁 Kết quả: {'CHIẾN THẮNG' if win else 'THẤT BẠI'}! Nhận +{reward} Linh"
        " Thạch."
    )
    updated = db.execute(
        "SELECT * FROM characters WHERE id=?", (req.char_id,), fetchone=True
    )
    return {"char": parse_char(updated), "win": win, "logs": logs}


# ==========================================
# 6. PHỤC VỤ GIAO DIỆN FRONTEND
# ==========================================
os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def serve_index():
    return FileResponse("static/index.html")
