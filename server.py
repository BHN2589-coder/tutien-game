import os
import time
import sqlite3
import json
import math
import random
from typing import Optional
from contextlib import contextmanager
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="Pham Nhan Tu Tien - Engine 2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_PATH = "game.db"

@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db():
    with get_db() as conn:
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                telegram_id TEXT PRIMARY KEY,
                username TEXT,
                active_slot INTEGER DEFAULT 1
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS characters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id TEXT,
                slot_index INTEGER,
                name TEXT,
                realm_idx INTEGER DEFAULT 0,
                realm_level INTEGER DEFAULT 1,
                exp INTEGER DEFAULT 0,
                exp_max INTEGER DEFAULT 100,
                age INTEGER DEFAULT 1,
                max_age INTEGER DEFAULT 100,
                linh_thach INTEGER DEFAULT 300,
                hammers INTEGER DEFAULT 0,
                pity_boss INTEGER DEFAULT 0,
                rebirth_count INTEGER DEFAULT 0,
                free_points INTEGER DEFAULT 0,
                is_dev BOOLEAN DEFAULT 0,
                last_cultivate_time REAL DEFAULT 0,
                stats_json TEXT,
                roots_json TEXT,
                destiny_json TEXT,
                equipment_json TEXT,
                inventory_json TEXT,
                UNIQUE(telegram_id, slot_index)
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS world_boss (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                max_hp INTEGER,
                current_hp INTEGER,
                attack INTEGER,
                armor INTEGER,
                dodge REAL,
                counter REAL,
                lifesteal REAL,
                is_alive BOOLEAN DEFAULT 1,
                created_at REAL
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS boss_attacks (
                boss_id INTEGER,
                char_id INTEGER,
                attack_count INTEGER DEFAULT 0,
                PRIMARY KEY (boss_id, char_id)
            )
        """)

init_db()

# --- HỆ THỐNG CẢNH GIỚI VÀ THỌ NGUYÊN ---
REALM_NAMES = [
    "Phàm Nhân", "Luyện Khí", "Trúc Cơ", "Kim Đan", "Nguyên Anh",
    "Hóa Thần", "Luyện Hư", "Hợp Thể", "Đại Thừa", "Độ Kiếp", "Chân Tiên Cảnh"
]
REALM_LIFESPANS = [100, 150, 250, 500, 1000, 2000, 4000, 8000, 15000, 30000, 999999]

def get_sub_stage(level: int) -> str:
    if level <= 3: return "Sơ Kỳ"
    if level <= 6: return "Trung Kỳ"
    if level <= 9: return "Hậu Kỳ"
    return "Viên Mãn"

def get_full_realm_title(realm_idx: int, level: int) -> str:
    base = REALM_NAMES[min(realm_idx, len(REALM_NAMES)-1)]
    if realm_idx == 0:
        return f"{base} (Cấp {level})"
    stage = get_sub_stage(level)
    return f"{base} {stage} (Cấp {level})"

ROOT_DATABASE = {
    "D": [
        {"name": "Bính Hỏa Linh Căn", "tier": "D", "desc": "Tăng 5% sát thương hỏa"},
        {"name": "Ất Mộc Linh Căn", "tier": "D", "desc": "Tăng 5% hồi phục khí huyết"},
        {"name": "Huyền Thủy Linh Căn", "tier": "D", "desc": "Tăng 5% né tránh"},
        {"name": "Canh Kim Linh Căn", "tier": "D", "desc": "Tăng 5% phòng ngự"},
        {"name": "Mậu Thổ Linh Căn", "tier": "D", "desc": "Tăng 5% lượng máu tối đa"}
    ],
    "C": [
        {"name": "Tử Lôi Biến Dị", "tier": "C", "desc": "Kích hoạt 4% gây choáng"},
        {"name": "Huyền Băng Dị Căn", "tier": "C", "desc": "Hàn khí thấu cốt, giảm tốc đối phương"},
        {"name": "Cương Phong Dị Thể", "tier": "C", "desc": "Tăng 8% Thân pháp tốc độ"}
    ],
    "B": [
        {"name": "Viêm Lôi Hợp Thể", "tier": "B", "desc": "Lôi hỏa giao hòa, tăng 10% bạo kích"},
        {"name": "Băng Phách Huyền Thủy", "tier": "B", "desc": "Đóng băng vạn vật, tăng 8% né tránh"}
    ],
    "A": [
        {"name": "Thái Cực Âm Dương Căn", "tier": "A", "desc": "Hóa giải sát thương, phản 8% đòn đánh"},
        {"name": "Hỗn Nguyên Kim Cương Căn", "tier": "A", "desc": "Thân thể bất hoại, tăng 15% giáp"}
    ],
    "S": [
        {"name": "Tử Tiêu Thần Lôi Căn", "tier": "S", "desc": "Lôi kiếp tối thượng, 15% bỏ qua giáp"},
        {"name": "Đại Nhật Kim Ô Căn", "tier": "S", "desc": "Chân hỏa thái dương, thiêu đốt nguyên thần"}
    ],
    "SS": [
        {"name": "Hỗn Độn Diệt Thế Lôi", "tier": "SS", "desc": "Tăng 25% sát thương bạo kích"},
        {"name": "Thời Không Chi Dực", "tier": "SS", "desc": "Tăng 18% Né tránh và Tiên thủ đoạt chiêu"}
    ],
    "SSS": [
        {"name": "Tam Muội Chân Hỏa", "tier": "SSS", "desc": "Ngũ Đại Đỉnh Cao: Thiêu rụi toàn bộ giáp hộ thể"},
        {"name": "Canh Kim Bạch Hổ", "tier": "SSS", "desc": "Ngũ Đại Đỉnh Cao: Sát phạt tuyệt đối, +30% Bạo kích"},
        {"name": "Ất Mộc Trường Sinh", "tier": "SSS", "desc": "Ngũ Đại Đỉnh Cao: Trường sinh bất tử, +35% Hút máu"},
        {"name": "Thiên Nhất Chân Thủy", "tier": "SSS", "desc": "Ngũ Đại Đỉnh Cao: Hóa giải vạn pháp, +25% Né tránh"},
        {"name": "Huyền Hoàng Tức Nhưỡng", "tier": "SSS", "desc": "Ngũ Đại Đỉnh Cao: Thổ thần vô địch, +300 điểm Giáp"}
    ]
}

DESTINY_DATABASE = [
    {"name": "Khí Vận Chi Tử", "type": "Thiên Mệnh", "desc": "Nhân vật chính hào quang, tăng gấp đôi tỉ lệ rơi bảo vật"},
    {"name": "Chí Tôn Cốt", "type": "Dị Cốt", "desc": "Trời sinh thần cốt, tăng 15% Sức mạnh và Bạo kích"},
    {"name": "Trùng Đồng Chi Nhãn", "type": "Dị Cốt", "desc": "Nhìn thấu sơ hở, tăng 15% Né tránh"},
    {"name": "Bất Diệt Chân Huyết", "type": "Dị Cốt", "desc": "Khí huyết vô tận, tăng 25% Máu tối đa"},
    {"name": "Hàn Băng Thần Thể", "type": "Dị Cốt", "desc": "Thân thể băng sương, tăng 15% Giáp và phản kích"}
]

DEFAULT_EQUIPMENT = {
    "vk1": None, "vk2": None, "mu": None, "ao": None,
    "quan": None, "giay": None, "nhan1": None, "nhan2": None, "nhan3": None
}

ARMOR_CONSTANT = 600.0

def calculate_total_stats(base_stats: dict, eq: dict) -> dict:
    total = {
        "hp": 100 + int(base_stats.get("the_chat", 0) * 30 * (1.0 + 0.09 * base_stats.get("the_chat", 0))),
        "mp": 1000 + int(base_stats.get("linh_luc", 0) * 20),
        "suc_manh": 50 + int(base_stats.get("linh_luc", 0) * 5 * (1.0 + 0.09 * base_stats.get("linh_luc", 0))),
        "toc_do": 50 + int(base_stats.get("toc_do", 0) * 4),
        "thu": 20 + int(base_stats.get("the_chat", 0) * 3),
        "ne_tranh": min(50.0, float(base_stats.get("toc_do", 0) * 0.5)),
        "bao_kich": 5.0,
        "lien_kich": 5.0,
        "phan_kich": 5.0,
        "choang": 0.0,
        "hut_mau": 0.0,
        "khi_van": base_stats.get("khi_van", 0),
        "ngo_tinh": base_stats.get("ngo_tinh", 0)
    }

    for slot, item in eq.items():
        if item:
            mult = 1.0 + (item.get("enhance", 0) * 0.1)
            for k, v in item.get("stats", {}).items():
                if k in ["ne_tranh", "bao_kich", "lien_kich", "phan_kich", "choang", "hut_mau"]:
                    total[k] = min(70.0 if k == "ne_tranh" else 40.0, total.get(k, 0.0) + (v * mult))
                else:
                    total[k] = total.get(k, 0) + math.floor(v * mult)
    return total

class Fighter:
    def __init__(self, name: str, stats: dict):
        self.name = name
        self.max_hp = stats.get("hp", 100)
        self.current_hp = self.max_hp
        self.strength = stats.get("suc_manh", 50)
        self.speed = stats.get("toc_do", 50)
        self.armor = stats.get("thu", 0)
        self.dodge = min(60.0, float(stats.get("ne_tranh", 0.0)))
        self.lifesteal = min(50.0, float(stats.get("hut_mau", 0.0)))
        self.crit = min(50.0, float(stats.get("bao_kich", 0.0)))
        self.combo = min(40.0, float(stats.get("lien_kich", 0.0)))
        self.counter = min(40.0, float(stats.get("phan_kich", 0.0)))
        self.stun = min(30.0, float(stats.get("choang", 0.0)))
        self.is_stunned = False

    def get_mitigation(self) -> float:
        if self.armor <= 0: return 0.0
        return self.armor / (self.armor + ARMOR_CONSTANT)

def simulate_battle(f1: Fighter, f2: Fighter, max_turns: int = 30):
    logs = []
    atk, df = (f1, f2) if f1.speed >= f2.speed else (f2, f1)
    logs.append(f"⚡ Khởi tranh! {atk.name} (Tốc {atk.speed}) đoạt TIÊN THỦ trước {df.name} (Tốc {df.speed}).")

    turn = 0
    while turn < max_turns and f1.current_hp > 0 and f2.current_hp > 0:
        turn += 1
        if atk.is_stunned:
            logs.append(f"💫 [Hiệp {turn}] {atk.name} bị CHOÁNG, mất lượt thi triển!")
            atk.is_stunned = False
        else:
            execute_strike(atk, df, logs, turn, is_counter=False)
            if df.current_hp > 0 and random.uniform(0, 100) <= atk.combo:
                logs.append(f"⚡ [Hiệp {turn} - Liên Kích] {atk.name} áp sát tung thêm đòn liên kích!")
                execute_strike(atk, df, logs, turn, is_counter=False)

        if df.current_hp <= 0: break
        atk, df = df, atk

    winner = f1 if f1.current_hp > 0 and (f2.current_hp <= 0 or (f1.current_hp/f1.max_hp >= f2.current_hp/f2.max_hp)) else f2
    loser = f2 if winner == f1 else f1
    logs.append(f"🏆 KẾT THÚC! {winner.name} đã đả bại {loser.name}!")
    return {"winner_name": winner.name, "total_turns": turn, "logs": logs, "damage_dealt_to_f2": f2.max_hp - max(0, f2.current_hp)}

def execute_strike(atk: Fighter, df: Fighter, logs: list, turn: int, is_counter: bool = False):
    if random.uniform(0, 100) <= df.dodge:
        logs.append(f"💨 [Hiệp {turn}] {df.name} NÉ ĐÒN xuất sắc của {atk.name}!")
        if not is_counter and random.uniform(0, 100) <= (df.counter / 2.0):
            logs.append(f"⚡ [Hiệp {turn} - Né Phản] {df.name} mượn thế phản kích!")
            execute_strike(df, atk, logs, turn, is_counter=True)
        return

    is_crit = random.uniform(0, 100) <= atk.crit
    raw_dmg = atk.strength * (2 if is_crit else 1)
    mitigation = df.get_mitigation()
    actual_dmg = max(1, math.floor(raw_dmg * (1.0 - mitigation)))
    df.current_hp = max(0, df.current_hp - actual_dmg)

    crit_tag = "💥 BẠO KÍCH! " if is_crit else ""
    counter_tag = "[Phản Kích] " if is_counter else ""
    logs.append(f"⚔️ [Hiệp {turn}] {counter_tag}{atk.name} đánh trúng {crit_tag}gây {actual_dmg} ST. {df.name} còn {df.current_hp}/{df.max_hp} HP.")

    if atk.lifesteal > 0 and actual_dmg > 0:
        healed = max(1, math.floor(actual_dmg * (atk.lifesteal / 100.0)))
        atk.current_hp = min(atk.max_hp, atk.current_hp + healed)
        logs.append(f"🩸 {atk.name} hút {healed} HP.")

    if df.current_hp <= 0: return

    if random.uniform(0, 100) <= atk.stun:
        df.is_stunned = True
        logs.append(f"💫 {df.name} trúng đòn rơi vào trạng thái CHOÁNG!")
        return

    if not is_counter and random.uniform(0, 100) <= df.counter:
        logs.append(f"🛡️ [Hiệp {turn} - Phản Pháo] {df.name} phản đòn chớp nhoáng!")
        execute_strike(df, atk, logs, turn, is_counter=True)

# --- MODELS REQUEST ---
class RollCharacterRequest(BaseModel):
    telegram_id: str
    username: Optional[str] = "Đạo Hữu"
    slot_index: int
    name: str
    allocated_points: dict
    admin_password: Optional[str] = None

class ActionRequest(BaseModel):
    char_id: int

class EnhanceRequest(BaseModel):
    char_id: int
    slot_key: str

class SellRequest(BaseModel):
    char_id: int
    inv_index: int

class BuyRequest(BaseModel):
    char_id: int
    item_id: str

class ChallengeRequest(BaseModel):
    challenger_char_id: int
    target_char_id: int

class DeleteCharRequest(BaseModel):
    telegram_id: str
    slot_index: int
    confirm_name: str

class AddStatPointRequest(BaseModel):
    char_id: int
    stat_key: str

class SpawnBossRequest(BaseModel):
    admin_password: str
    name: str
    hp: int
    attack: int
    armor: int
    dodge: float
    counter: float
    lifesteal: float

# --- API ENDPOINTS ---

@app.get("/api/slots/{telegram_id}")
def get_slots(telegram_id: str):
    with get_db() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT id, slot_index, name, realm_idx, realm_level, exp, exp_max, age, max_age,
                   linh_thach, hammers, pity_boss, rebirth_count, free_points, is_dev,
                   last_cultivate_time, stats_json, roots_json, destiny_json, equipment_json, inventory_json
            FROM characters WHERE telegram_id = ?
        """, (str(telegram_id),))
        rows = c.fetchall()

    slots = {i: None for i in range(1, 6)}
    for r in rows:
        base_st = json.loads(r["stats_json"])
        eq = json.loads(r["equipment_json"]) if r["equipment_json"] else DEFAULT_EQUIPMENT
        tot_st = calculate_total_stats(base_st, eq)
        realm_title = get_full_realm_title(r["realm_idx"], r["realm_level"])

        slots[r["slot_index"]] = {
            "char_id": r["id"],
            "slot_index": r["slot_index"],
            "name": r["name"],
            "realm_idx": r["realm_idx"],
            "realm_level": r["realm_level"],
            "realm_title": realm_title,
            "exp": r["exp"],
            "exp_max": r["exp_max"],
            "age": r["age"],
            "max_age": r["max_age"],
            "linh_thach": r["linh_thach"],
            "hammers": r["hammers"],
            "pity_boss": r["pity_boss"],
            "rebirth_count": r["rebirth_count"],
            "free_points": r["free_points"],
            "is_dev": bool(r["is_dev"]),
            "last_cultivate_time": r["last_cultivate_time"],
            "base_stats": base_st,
            "total_stats": tot_st,
            "roots": json.loads(r["roots_json"]),
            "destiny": json.loads(r["destiny_json"]) if r["destiny_json"] else None,
            "equipment": eq,
            "inventory": json.loads(r["inventory_json"]) if r["inventory_json"] else []
        }
    return {"slots": slots}

@app.post("/api/characters/create")
def create_character(req: RollCharacterRequest):
    if not (1 <= req.slot_index <= 5):
        raise HTTPException(400, "Slot không hợp lệ (1-5)")

    is_dev = (req.admin_password == "DevGame")
    if is_dev:
        stats = {"linh_luc": 100, "the_chat": 100, "toc_do": 100, "khi_van": 100, "ngo_tinh": 100}
        roots = ROOT_DATABASE["SSS"][:5] + ROOT_DATABASE["SS"][:2]
        destiny = {"name": "Chí Tôn Cốt & Khí Vận Chi Tử", "type": "Song Sinh Chí Tôn", "desc": "Mở khóa toàn bộ uy năng thiên địa"}
        realm_idx, realm_level = 10, 10
        lt, hammers = 999999, 99
        max_age = 999999
    else:
        # Chuẩn hóa 5 chỉ số từ request (tổng 30đ)
        ll = int(req.allocated_points.get("linh_luc", 6))
        tc = int(req.allocated_points.get("the_chat", 6))
        td = int(req.allocated_points.get("toc_do", 6))
        kv = int(req.allocated_points.get("khi_van", 6))
        nt = int(req.allocated_points.get("ngo_tinh", 6))
        stats = {"linh_luc": ll, "the_chat": tc, "toc_do": td, "khi_van": kv, "ngo_tinh": nt}

        root_count = random.choices([1, 2, 3, 4], weights=[45, 35, 15, 5])[0]
        chosen_roots = []
        for _ in range(root_count):
            tier = random.choices(["D", "C", "B", "A", "S", "SS", "SSS"], weights=[55, 25, 10, 5, 3, 1.5, 0.5])[0]
            r_item = random.choice(ROOT_DATABASE[tier])
            if r_item not in chosen_roots:
                chosen_roots.append(r_item)

        roots = chosen_roots
        destiny = random.choice(DESTINY_DATABASE)
        realm_idx, realm_level = 0, 1
        lt, hammers = 300, 1
        max_age = REALM_LIFESPANS[0]

    starter_equip = dict(DEFAULT_EQUIPMENT)
    starter_equip["vk1"] = {"name": "Mộc Kiếm Phàm Phẩm", "type": "vk1", "enhance": 0, "stats": {"suc_manh": 20, "bao_kich": 2.0}, "price": 100}

    with get_db() as conn:
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO users (telegram_id, username) VALUES (?, ?)", (str(req.telegram_id), req.username))
        c.execute("DELETE FROM characters WHERE telegram_id = ? AND slot_index = ?", (str(req.telegram_id), req.slot_index))
        c.execute("""
            INSERT INTO characters (telegram_id, slot_index, name, realm_idx, realm_level, exp, exp_max, age, max_age,
                                   linh_thach, hammers, pity_boss, rebirth_count, free_points, is_dev, last_cultivate_time,
                                   stats_json, roots_json, destiny_json, equipment_json, inventory_json)
            VALUES (?, ?, ?, ?, ?, 0, 100, 1, ?, ?, ?, 0, 0, 0, ?, 0, ?, ?, ?, ?, ?)
        """, (
            str(req.telegram_id), req.slot_index, req.name, realm_idx, realm_level, max_age,
            lt, hammers, 1 if is_dev else 0, json.dumps(stats), json.dumps(roots),
            json.dumps(destiny), json.dumps(starter_equip), json.dumps([])
        ))
    return {"status": "success", "is_dev": is_dev}

# --- CỐT TRUYỆN & TU LUYỆN (GIỚI HẠN 10 GIÂY) ---
@app.post("/api/action/story_step")
def story_step(req: ActionRequest):
    now = time.time()
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM characters WHERE id = ?", (req.char_id,))
        row = c.fetchone()
        if not row:
            raise HTTPException(404, "Không tìm thấy nhân vật!")

        # 1. Kiểm tra giới hạn 10 giây
        last_time = row["last_cultivate_time"] or 0
        remain_cooldown = 10.0 - (now - last_time)
        if remain_cooldown > 0:
            raise HTTPException(429, f"Tâm cảnh chưa ổn định! Cần điều tức thêm {math.ceil(remain_cooldown)} giây.")

        age = row["age"] + 1
        max_age = row["max_age"]
        if age >= max_age:
            raise HTTPException(400, f"Thọ nguyên đã cạn ({age}/{max_age} tuổi)! Hãy chọn [Niết Bàn Trùng Sinh] để tái tạo tiên cơ.")

        curr_lt = row["linh_thach"]
        realm_idx = row["realm_idx"]
        realm_lvl = row["realm_level"]
        exp = row["exp"]
        exp_max = row["exp_max"]
        free_pts = row["free_points"]
        stats = json.loads(row["stats_json"])

        # Tính tu vi thu được trong năm (chịu ảnh hưởng bởi Ngộ Tính & Linh Lực)
        ngo_tinh = stats.get("ngo_tinh", 0)
        linh_luc = stats.get("linh_luc", 0)
        exp_gained = math.floor(15 + (linh_luc * 0.5) + (ngo_tinh * 0.8))
        exp += exp_gained

        # Phân phối sự kiện Phàm Nhân Tu Tiên theo cảnh giới
        roll = random.uniform(0, 100)
        gain_lt = 0

        if realm_idx == 0:  # Phàm Nhân
            if age <= 5:
                log = f"Năm {age} tuổi: Sinh ra tại Thanh Ngưu Trấn nghèo khó, hàng ngày giúp gia đình chăn trâu đốn củi. Thu hoạch +{exp_gained} Tu Vi."
            elif age <= 10:
                log = f"Năm {age} tuổi: Tam Thúc giới thiệu gia nhập Thất Huyền Môn, nhẫn nại rèn luyện thể lực tại Thần Kê Cốc. (+{exp_gained} Tu Vi)"
            else:
                gain_lt = random.randint(30, 80)
                log = f"Năm {age} tuổi: Được Mặc Đại Phu chọn làm đệ tử ký danh Thần Thủ Cốc, bắt đầu tiếp xúc thảo dược quý. (+{gain_lt} Linh Thạch, +{exp_gained} Tu Vi)"
        elif realm_idx == 1:  # Luyện Khí Kỳ
            if roll < 35:
                log = f"Năm {age} tuổi: Khổ luyện Trường Xuân Công bên sườn núi, đan điền linh khí luân chuyển. (+{exp_gained} Tu Vi)"
            elif roll < 70:
                gain_lt = random.randint(50, 120)
                log = f"Năm {age} tuổi: ✨ Dùng Chưởng Thiên Bình nhỏ giọt lục dịch thúc chín linh thảo ngàn năm bán đổi {gain_lt} Linh Thạch! (+{exp_gained} Tu Vi)"
            elif roll < 90:
                gain_lt = random.randint(150, 300)
                log = f"Năm {age} tuổi: 💥 Tham gia Huyết Sắc Thí Luyện, liên thủ trảm sát cường địch ma đạo thu thập thảo dược quý! (+{gain_lt} Linh Thạch, +{exp_gained} Tu Vi)"
            else:
                gain_lt = -random.randint(30, 70)
                log = f"Năm {age} tuổi: Đụng độ Dã Lang Bang phục kích, phải tiêu hao phù chú hộ thân thoát thân (-{abs(gain_lt)} Linh Thạch). (+{exp_gained} Tu Vi)"
        elif realm_idx == 2:  # Trúc Cơ Kỳ
            if roll < 40:
                log = f"Năm {age} tuổi: Bế quan trong Bách Dược Viên Hoàng Phong Cốc, ngày đêm vững chắc Trúc Cơ Linh Hải. (+{exp_gained} Tu Vi)"
            elif roll < 80:
                gain_lt = random.randint(120, 250)
                log = f"Năm {age} tuổi: Ma Đạo Lục Tông xâm lấn Thiên Nam, phụng mệnh tuần tra chiến trường thu chiến lợi phẩm (+{gain_lt} Linh Thạch). (+{exp_gained} Tu Vi)"
            else:
                gain_lt = random.randint(300, 500)
                log = f"Năm {age} tuổi: 🌟 Lĩnh ngộ tầng thứ nhất Đại Diễn Quyết, thần thức tăng vọt! (+{gain_lt} Linh Thạch, +{exp_gained} Tu Vi)"
        elif realm_idx == 3:  # Kim Đan Kỳ
            if roll < 45:
                log = f"Năm {age} tuổi: Lưu lạc tới Loạn Tinh Hải, mượn động phủ Thiên Tinh Thành ngưng kết Kim Đan. (+{exp_gained} Tu Vi)"
            elif roll < 85:
                gain_lt = random.randint(250, 600)
                log = f"Năm {age} tuổi: Tiến vào Hư Thiên Điện tranh đoạt Hư Thiên Đỉnh, dùng Thanh Trúc Ong Vân Kiếm trảm địch đoạt bảo (+{gain_lt} Linh Thạch). (+{exp_gained} Tu Vi)"
            else:
                gain_lt = -random.randint(100, 200)
                log = f"Năm {age} tuổi: Bị Cực Huyễn Lão Ma truy nã phong tỏa vùng biển, tiêu tốn linh thạch kích hoạt Cổ Truyền Tống Trận thoát thân (-{abs(gain_lt)} Linh Thạch)."
        elif realm_idx == 4:  # Nguyên Anh Kỳ
            gain_lt = random.randint(400, 900)
            log = f"Năm {age} tuổi: Trở về Thiên Nam làm Trưởng Lão Lạc Vân Tông, đại náo Trụy Ma Cốc thu thập Cổ Bảo Vạn Niên! (+{gain_lt} Linh Thạch, +{exp_gained} Tu Vi)"
        else:  # Hóa Thần & Thượng Giới
            gain_lt = random.randint(800, 2000)
            log = f"Năm {age} tuổi: Đột phá Hóa Thần phi thăng Linh Giới, độ kiếp lôi đình chấn động chư thiên! (+{gain_lt} Linh Thạch, +{exp_gained} Tu Vi)"

        new_lt = max(0, curr_lt + gain_lt)

        # Xử lý Tăng Cấp độ (Level 1-10) và Đột phá Cảnh Giới
        leveled_up = False
        while exp >= exp_max:
            exp -= exp_max
            if realm_lvl < 10:
                realm_lvl += 1
                exp_max = math.floor(exp_max * 1.35)
                log += f" 🌟 [THĂNG TIẾN] Chạm tới Cấp {realm_lvl} ({get_sub_stage(realm_lvl)})!"
                # Mỗi 10 cấp tích lũy hoặc mỗi lần thăng tiến tặng điểm
                if realm_lvl % 5 == 0:
                    free_pts += 1
                    log += " (Nhận +1 Điểm Tiềm Năng!)"
            else:
                # Đang ở Cấp 10 Viên Mãn -> Đột phá lên Cảnh Giới mới
                if realm_idx < len(REALM_NAMES) - 1:
                    realm_idx += 1
                    realm_lvl = 1
                    exp_max = math.floor(exp_max * 1.6)
                    max_age = REALM_LIFESPANS[realm_idx]
                    free_pts += 2
                    log += f" ⚡⚡ [ĐỘT PHÁ CẢNH GIỚI] Tấn thăng [{REALM_NAMES[realm_idx]}]! Thọ nguyên tăng lên {max_age} năm, nhận +2 Điểm Tiềm Năng!"
                break

        c.execute("""
            UPDATE characters
            SET age = ?, max_age = ?, linh_thach = ?, realm_idx = ?, realm_level = ?,
                exp = ?, exp_max = ?, free_points = ?, last_cultivate_time = ?
            WHERE id = ?
        """, (age, max_age, new_lt, realm_idx, realm_lvl, exp, exp_max, free_pts, now, req.char_id))

    return {
        "status": "success",
        "log": log,
        "age": age,
        "max_age": max_age,
        "linh_thach": new_lt,
        "realm_title": get_full_realm_title(realm_idx, realm_lvl),
        "exp": exp,
        "exp_max": exp_max,
        "free_points": free_pts
    }

# --- CỘNG ĐIỂM TIỀM NĂNG TỰ DO ---
@app.post("/api/action/add_stat_point")
def add_stat_point(req: AddStatPointRequest):
    valid_keys = ["linh_luc", "the_chat", "toc_do", "khi_van", "ngo_tinh"]
    if req.stat_key not in valid_keys:
        raise HTTPException(400, "Thuộc tính không hợp lệ!")

    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT free_points, stats_json FROM characters WHERE id = ?", (req.char_id,))
        row = c.fetchone()
        if not row:
            raise HTTPException(404, "Nhân vật không tồn tại!")

        free_pts = row["free_points"]
        if free_pts < 1:
            raise HTTPException(400, "Không còn điểm tiềm năng tự do!")

        stats = json.loads(row["stats_json"])
        if stats.get(req.stat_key, 0) >= 100:
            raise HTTPException(400, "Thuộc tính này đã đạt giới hạn tối đa 100 điểm!")

        stats[req.stat_key] += 1
        free_pts -= 1
        c.execute("UPDATE characters SET free_points = ?, stats_json = ? WHERE id = ?", (free_pts, json.dumps(stats), req.char_id))

    return {"status": "success", "new_stat_val": stats[req.stat_key], "remain_points": free_pts}

# --- NIẾT BÀN TRÙNG SINH ---
@app.post("/api/action/rebirth")
def rebirth_character(req: ActionRequest):
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM characters WHERE id = ?", (req.char_id,))
        row = c.fetchone()
        if not row:
            raise HTTPException(404, "Không tìm thấy nhân vật!")

        rebirth_count = row["rebirth_count"] + 1
        bonus_points = 10  # Mỗi lần trùng sinh thưởng 10 điểm tiềm năng vĩnh viễn
        new_free_points = row["free_points"] + bonus_points

        # Đặt lại tuổi về 1, cảnh giới về Phàm Nhân cấp 1
        new_realm_idx = 0
        new_realm_lvl = 1
        new_max_age = REALM_LIFESPANS[0]

        c.execute("""
            UPDATE characters
            SET age = 1, max_age = ?, realm_idx = ?, realm_level = ?, exp = 0, exp_max = 100,
                rebirth_count = ?, free_points = ?
            WHERE id = ?
        """, (new_max_age, new_realm_idx, new_realm_lvl, rebirth_count, new_free_points, req.char_id))

    return {
        "status": "success",
        "msg": f"Niết Bàn Trùng Sinh lần thứ {rebirth_count} thành công! Tuổi tái lập về 1, nhận thêm +{bonus_points} Điểm Tiềm Năng vĩnh viễn!",
        "rebirth_count": rebirth_count,
        "free_points": new_free_points
    }

# --- RANDOM LINH CĂN BẰNG 1000 LINH THẠCH ---
@app.post("/api/action/gacha_root")
def gacha_root(req: ActionRequest):
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT linh_thach, roots_json FROM characters WHERE id = ?", (req.char_id,))
        row = c.fetchone()
        if not row:
            raise HTTPException(404, "Không tìm thấy nhân vật!")

        lt = row["linh_thach"]
        if lt < 1000:
            raise HTTPException(400, "Cần 1.000 Linh Thạch để tẩy luyện gacha Linh Căn!")

        lt -= 1000
        roots = json.loads(row["roots_json"])
        if len(roots) >= 7:
            raise HTTPException(400, "Linh căn xuất chiến đã đầy tối đa (7/7)! Hãy xóa bớt hoặc dung luyện.")

        tier = random.choices(["D", "C", "B", "A", "S", "SS", "SSS"], weights=[50, 25, 12, 7, 4, 1.5, 0.5])[0]
        new_root = random.choice(ROOT_DATABASE[tier])
        roots.append(new_root)

        c.execute("UPDATE characters SET linh_thach = ?, roots_json = ? WHERE id = ?", (lt, json.dumps(roots), req.char_id))

    return {"status": "success", "msg": f"Cơ duyên giáng hạ! Thu nhận thành công [{new_root['tier']}] {new_root['name']}!", "new_root": new_root, "linh_thach": lt}

# --- SĂN BOSS ĐƠN (LOẠN TINH HẢI) ---
@app.post("/api/action/hunt_boss")
def hunt_boss(req: ActionRequest):
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT linh_thach, hammers, pity_boss, stats_json FROM characters WHERE id = ?", (req.char_id,))
        row = c.fetchone()
        if not row:
            raise HTTPException(404, "Không tìm thấy nhân vật!")

        lt, hammers, pity = row["linh_thach"], row["hammers"], row["pity_boss"] + 1
        stats = json.loads(row["stats_json"])
        gain_lt = random.randint(250, 500)
        lt += gain_lt

        drop_rate = 1.0 + (stats.get("khi_van", 0) / 50.0)
        got_hammer = False

        if pity >= 80 or random.uniform(0, 100) <= drop_rate:
            got_hammer = True
            hammers += 1
            pity = 0
            msg = f"🎉 TRẢM SÁT THÀNH CÔNG YÊU VƯƠNG! Rơi 1 THIÊN CÔNG THẦN CHÙY (Búa)! (+{gain_lt} Linh Thạch)"
        else:
            msg = f"Trảm sát Yêu Thú Loạn Tinh Hải đổi +{gain_lt} Linh Thạch. Búa chưa rơi. (Bảo hiểm: {pity}/80)"

        c.execute("UPDATE characters SET linh_thach = ?, hammers = ?, pity_boss = ? WHERE id = ?", (lt, hammers, pity, req.char_id))

    return {"status": "success", "msg": msg, "got_hammer": got_hammer, "hammers": hammers, "linh_thach": lt, "pity": pity}

# --- BOSS THẾ GIỚI (WORLD BOSS - DÀNH CHO DEV SPAM & TOÀN SERVER ĐÁNH) ---
@app.post("/api/dev/spawn_world_boss")
def spawn_world_boss(req: SpawnBossRequest):
    if req.admin_password != "DevGame":
        raise HTTPException(403, "Mật mã DEV không chính xác!")

    with get_db() as conn:
        c = conn.cursor()
        # Đóng boss cũ
        c.execute("UPDATE world_boss SET is_alive = 0 WHERE is_alive = 1")
        # Tạo boss mới
        c.execute("""
            INSERT INTO world_boss (name, max_hp, current_hp, attack, armor, dodge, counter, lifesteal, is_alive, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
        """, (req.name, req.hp, req.hp, req.attack, req.armor, req.dodge, req.counter, req.lifesteal, time.time()))
        # Reset lượt đánh
        c.execute("DELETE FROM boss_attacks")

    return {"status": "success", "msg": f"Đã giáng lâm Boss Thế Giới: [{req.name}] với {req.hp} HP!"}

@app.get("/api/world_boss/status")
def get_world_boss_status(char_id: int):
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM world_boss WHERE is_alive = 1 ORDER BY id DESC LIMIT 1")
        boss = c.fetchone()
        if not boss:
            return {"active": False}

        c.execute("SELECT attack_count FROM boss_attacks WHERE boss_id = ? AND char_id = ?", (boss["id"], char_id))
        att_row = c.fetchone()
        attacks_left = 5 - (att_row["attack_count"] if att_row else 0)

    return {
        "active": True,
        "boss": {
            "id": boss["id"],
            "name": boss["name"],
            "max_hp": boss["max_hp"],
            "current_hp": boss["current_hp"],
            "attack": boss["attack"],
            "armor": boss["armor"],
            "dodge": boss["dodge"],
            "counter": boss["counter"],
            "lifesteal": boss["lifesteal"],
            "attacks_left": max(0, attacks_left)
        }
    }

@app.post("/api/world_boss/attack")
def attack_world_boss(req: ActionRequest):
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM world_boss WHERE is_alive = 1 ORDER BY id DESC LIMIT 1")
        boss = c.fetchone()
        if not boss or boss["current_hp"] <= 0:
            raise HTTPException(400, "Hiện tại không có Boss Thế Giới còn sống!")

        c.execute("SELECT attack_count FROM boss_attacks WHERE boss_id = ? AND char_id = ?", (boss["id"], req.char_id))
        att_row = c.fetchone()
        cnt = att_row["attack_count"] if att_row else 0
        if cnt >= 5:
            raise HTTPException(400, "Đạo hữu đã dùng hết 5 lượt khiêu chiến Boss Thế Giới này!")

        c.execute("SELECT id, name, stats_json, equipment_json, linh_thach, hammers FROM characters WHERE id = ?", (req.char_id,))
        char = c.fetchone()
        if not char:
            raise HTTPException(404, "Nhân vật không tồn tại!")

        tot_stats = calculate_total_stats(json.loads(char["stats_json"]), json.loads(char["equipment_json"]) if char["equipment_json"] else DEFAULT_EQUIPMENT)
        f_player = Fighter(char["name"], tot_stats)

        boss_stats = {
            "hp": boss["current_hp"],
            "suc_manh": boss["attack"],
            "toc_do": 80,
            "thu": boss["armor"],
            "ne_tranh": boss["dodge"],
            "phan_kich": boss["counter"],
            "hut_mau": boss["lifesteal"],
            "bao_kich": 10.0,
            "lien_kich": 5.0,
            "choang": 5.0
        }
        f_boss = Fighter(boss["name"], boss_stats)

        res = simulate_battle(f_player, f_boss, max_turns=15)
        dmg_dealt = max(0, boss["current_hp"] - f_boss.current_hp)
        new_boss_hp = max(0, boss["current_hp"] - dmg_dealt)

        # Cập nhật máu boss và lượt đánh
        c.execute("UPDATE world_boss SET current_hp = ?, is_alive = ? WHERE id = ?", (new_boss_hp, 1 if new_boss_hp > 0 else 0, boss["id"]))
        c.execute("""
            INSERT INTO boss_attacks (boss_id, char_id, attack_count) VALUES (?, ?, 1)
            ON CONFLICT(boss_id, char_id) DO UPDATE SET attack_count = attack_count + 1
        """, (boss["id"], req.char_id))

        # Thưởng dựa trên sát thương gây ra
        reward_lt = math.floor(dmg_dealt * 0.1) + 100
        new_lt = char["linh_thach"] + reward_lt
        new_hammers = char["hammers"] + (1 if (f_boss.current_hp <= 0 or random.uniform(0, 100) < 15) else 0)
        c.execute("UPDATE characters SET linh_thach = ?, hammers = ? WHERE id = ?", (new_lt, new_hammers, req.char_id))

    return {
        "status": "success",
        "damage_dealt": dmg_dealt,
        "boss_remaining_hp": new_boss_hp,
        "reward_lt": reward_lt,
        "logs": res["logs"],
        "attacks_left": 5 - (cnt + 1)
    }

# --- CƯỜNG HÓA TRANG BỊ (+20 CỰC HẠN) ---
@app.post("/api/action/enhance")
def enhance_equipment(req: EnhanceRequest):
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT hammers, linh_thach, equipment_json FROM characters WHERE id = ?", (req.char_id,))
        row = c.fetchone()
        if not row:
            raise HTTPException(404, "Không tìm thấy nhân vật!")

        hammers, lt = row["hammers"], row["linh_thach"]
        equipment = json.loads(row["equipment_json"])
        item = equipment.get(req.slot_key)

        if not item:
            raise HTTPException(400, "Vị trí này chưa đeo trang bị!")
        if hammers < 1 or lt < 250:
            raise HTTPException(400, "Cần tối thiểu 1 Búa Cường Hóa và 250 Linh Thạch!")
        if item.get("enhance", 0) >= 20:
            raise HTTPException(400, "Trang bị đã đạt phẩm cấp Cực Hạn (+20)!")

        hammers -= 1
        lt -= 250
        current_lv = item.get("enhance", 0)
        success = random.uniform(0, 100) <= 75.0

        if success:
            item["enhance"] = current_lv + 1
            msg = f"✨ THÀNH CÔNG! {item['name']} thăng hoa lên cấp +{item['enhance']}!"
        else:
            if current_lv > 15: item["enhance"] = max(15, current_lv - 1)
            elif current_lv > 10: item["enhance"] = max(10, current_lv - 1)
            msg = f"💔 THẤT BẠI! Búa gãy tiêu hao 250 Linh Thạch. Cấp hiện tại: +{item['enhance']}."

        equipment[req.slot_key] = item
        c.execute("UPDATE characters SET hammers = ?, linh_thach = ?, equipment_json = ? WHERE id = ?", (hammers, lt, json.dumps(equipment), req.char_id))

    return {"status": "success", "msg": msg, "new_enhance": item["enhance"], "hammers": hammers, "linh_thach": lt}

# --- SHOP VẠN BẢO CÁC ---
SHOP_CATALOG = {
    "item_dan_mp": {"name": "Cửu Chuyển Hồi Linh Đan", "type": "dan_duoc", "effect": "Hồi phục 35% Max MP", "price": 400},
    "item_dan_hp": {"name": "Hồi Xuân Chân Đan", "type": "dan_duoc", "effect": "Gia tăng 500 Khí Huyết vĩnh viễn", "price": 800},
    "item_vk_kiem": {"name": "Thanh Vân Tiên Kiếm (Huyền Phẩm)", "type": "vk2", "stats": {"suc_manh": 120, "lien_kich": 6.0}, "price": 1200},
    "item_ao_giap": {"name": "Huyền Vũ Hộ Tâm Giáp (Áo)", "type": "ao", "stats": {"thu": 180, "hp": 400}, "price": 1500},
    "item_nhan_bao": {"name": "Lưu Ly Giới Chỉ (Nhẫn 1)", "type": "nhan1", "stats": {"bao_kich": 8.0, "hut_mau": 5.0}, "price": 1800},
    "item_nhan_choang": {"name": "U Hồn Nhẫn (Nhẫn 2)", "type": "nhan2", "stats": {"choang": 8.0, "thu": 60}, "price": 1800},
    "item_nhan_phan": {"name": "Thiên Diệp Giới (Nhẫn 3)", "type": "nhan3", "stats": {"phan_kich": 8.0, "ne_tranh": 5.0}, "price": 1800},
    "item_bua_ren": {"name": "Thiên Công Thần Chùy (Búa)", "type": "bua", "price": 2000}
}

@app.post("/api/action/buy_item")
def buy_item(req: BuyRequest):
    if req.item_id not in SHOP_CATALOG:
        raise HTTPException(400, "Vật phẩm không tồn tại!")

    item = SHOP_CATALOG[req.item_id]
    cost = item["price"]

    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT linh_thach, hammers, inventory_json, equipment_json FROM characters WHERE id = ?", (req.char_id,))
        row = c.fetchone()
        if not row:
            raise HTTPException(404, "Không tìm thấy nhân vật!")

        lt, hammers = row["linh_thach"], row["hammers"]
        inv = json.loads(row["inventory_json"])
        eq = json.loads(row["equipment_json"])

        if lt < cost:
            raise HTTPException(400, "Không đủ Linh Thạch!")

        lt -= cost
        if req.item_id == "item_bua_ren":
            hammers += 1
            msg = "Đã thu nhận 1 Thiên Công Thần Chùy!"
        elif item["type"] == "dan_duoc":
            inv.append({"name": item["name"], "type": "dan_duoc", "price": cost, "desc": item["effect"]})
            msg = f"Đã cất {item['name']} vào túi trữ vật."
        else:
            slot = item["type"]
            eq[slot] = {"name": item["name"], "type": slot, "enhance": 0, "stats": item["stats"], "price": cost}
            msg = f"Đã trang bị [{item['name']}] vào vị trí [{slot}]!"

        c.execute("UPDATE characters SET linh_thach = ?, hammers = ?, inventory_json = ?, equipment_json = ? WHERE id = ?", (lt, hammers, json.dumps(inv), json.dumps(eq), req.char_id))

    return {"status": "success", "msg": msg, "linh_thach": lt, "hammers": hammers}

@app.post("/api/action/sell_item")
def sell_item(req: SellRequest):
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT linh_thach, inventory_json FROM characters WHERE id = ?", (req.char_id,))
        row = c.fetchone()
        if not row:
            raise HTTPException(404, "Không tìm thấy nhân vật!")

        inv = json.loads(row["inventory_json"])
        if req.inv_index < 0 or req.inv_index >= len(inv):
            raise HTTPException(400, "Vật phẩm không tồn tại!")

        item = inv.pop(req.inv_index)
        refund = math.floor(item.get("price", 100) * 0.7)
        new_lt = row["linh_thach"] + refund
        c.execute("UPDATE characters SET linh_thach = ?, inventory_json = ? WHERE id = ?", (new_lt, json.dumps(inv), req.char_id))

    return {"status": "success", "msg": f"Đã bán {item['name']}, thu hồi {refund} Linh Thạch.", "linh_thach": new_lt}

@app.delete("/api/action/remove_root")
def remove_root(char_id: int, root_index: int):
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT roots_json FROM characters WHERE id = ?", (char_id,))
        row = c.fetchone()
        if not row:
            raise HTTPException(404, "Không tìm thấy nhân vật!")

        roots = json.loads(row["roots_json"])
        if root_index < 0 or root_index >= len(roots):
            raise HTTPException(400, "Vị trí linh căn không hợp lệ!")

        removed = roots.pop(root_index)
        c.execute("UPDATE characters SET roots_json = ? WHERE id = ?", (json.dumps(roots), char_id))

    return {"status": "success", "msg": f"Đã xóa linh căn [{removed['name']}] khỏi xuất chiến!"}

# --- PVP LÔI ĐÀI ---
@app.get("/api/pvp/lobby")
def get_pvp_lobby(exclude_id: int):
    with get_db() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT id, name, realm_idx, realm_level, is_dev, stats_json, equipment_json
            FROM characters WHERE id != ? ORDER BY id DESC LIMIT 20
        """, (exclude_id,))
        rows = c.fetchall()

    res = []
    for r in rows:
        tot_st = calculate_total_stats(json.loads(r["stats_json"]), json.loads(r["equipment_json"]) if r["equipment_json"] else DEFAULT_EQUIPMENT)
        res.append({
            "id": r["id"], "name": r["name"],
            "realm": get_full_realm_title(r["realm_idx"], r["realm_level"]),
            "is_dev": bool(r["is_dev"]), "hp": tot_st.get("hp", 100), "speed": tot_st.get("toc_do", 100)
        })
    return {"opponents": res}

@app.post("/api/pvp/challenge")
def challenge_opponent(req: ChallengeRequest):
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT id, name, stats_json, equipment_json FROM characters WHERE id = ?", (req.challenger_char_id,))
        c1 = c.fetchone()
        c.execute("SELECT id, name, stats_json, equipment_json FROM characters WHERE id = ?", (req.target_char_id,))
        c2 = c.fetchone()

    if not c1 or not c2:
        raise HTTPException(404, "Đối thủ không tồn tại!")

    tot1 = calculate_total_stats(json.loads(c1["stats_json"]), json.loads(c1["equipment_json"]) if c1["equipment_json"] else DEFAULT_EQUIPMENT)
    tot2 = calculate_total_stats(json.loads(c2["stats_json"]), json.loads(c2["equipment_json"]) if c2["equipment_json"] else DEFAULT_EQUIPMENT)

    f1 = Fighter(c1["name"], tot1)
    f2 = Fighter(c2["name"], tot2)
    return simulate_battle(f1, f2)

@app.post("/api/characters/delete")
def delete_character(req: DeleteCharRequest):
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT id, name FROM characters WHERE telegram_id = ? AND slot_index = ?", (str(req.telegram_id), req.slot_index))
        row = c.fetchone()
        if not row:
            raise HTTPException(404, "Không tìm thấy nhân vật!")
        if row["name"].strip() != req.confirm_name.strip():
            raise HTTPException(400, "Tên xác nhận không khớp!")
        c.execute("DELETE FROM characters WHERE id = ?", (row["id"],))

    return {"status": "success"}

os.makedirs("static", exist_ok=True)
app.mount("/", StaticFiles(directory="static", html=True), name="static")
