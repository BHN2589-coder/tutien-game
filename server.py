import sqlite3
import json
import math
import random
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="Pham Nhan Tu Tien - Engine")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_PATH = "game.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
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
            realm TEXT DEFAULT 'Phàm Nhân',
            age INTEGER DEFAULT 1,
            linh_thach INTEGER DEFAULT 300,
            hammers INTEGER DEFAULT 0,
            pity_boss INTEGER DEFAULT 0,
            is_dev BOOLEAN DEFAULT 0,
            stats_json TEXT,
            roots_json TEXT,
            destiny_json TEXT,
            equipment_json TEXT,
            inventory_json TEXT,
            UNIQUE(telegram_id, slot_index)
        )
    """)
    conn.commit()
    conn.close()

init_db()

REALMS = [
    "Phàm Nhân", "Luyện Khí Tầng 1", "Luyện Khí Tầng 5", "Luyện Khí Viên Mãn",
    "Trúc Cơ Sơ Kỳ", "Trúc Cơ Viên Mãn", "Kim Đan Sơ Kỳ", "Kim Đan Cực Hạn",
    "Nguyên Anh Kỳ", "Hóa Thần Kỳ", "Độ Kiếp Viên Mãn", "Thần Đạo Cảnh"
]

ROOT_DATABASE = {
    "D": [
        {"name": "Bính Hỏa Linh Căn", "tier": "D", "desc": "Hỏa diễm thế tục, tăng 5% sát thương hỏa"},
        {"name": "Ất Mộc Linh Căn", "tier": "D", "desc": "Mộc khí sơ khai, tăng 5% hồi phục"},
        {"name": "Huyền Thủy Linh Căn", "tier": "D", "desc": "Thủy lưu nhu hòa, tăng 5% né tránh"},
        {"name": "Canh Kim Linh Căn", "tier": "D", "desc": "Kim khí thô sơ, tăng 5% giáp"},
        {"name": "Mậu Thổ Linh Căn", "tier": "D", "desc": "Thổ nhưỡng bình thường, tăng 5% HP"}
    ],
    "C": [
        {"name": "Tử Lôi Biến Dị", "tier": "C", "desc": "Sấm sét cuồng bạo, kích hoạt 4% Choáng"},
        {"name": "Huyền Băng Dị Căn", "tier": "C", "desc": "Băng hàn thấu cốt, giảm tốc đối thủ"},
        {"name": "Cương Phong Dị Thể", "tier": "C", "desc": "Gió lốc hộ thân, tăng 8% Tốc độ"}
    ],
    "B": [
        {"name": "Viêm Lôi Hợp Thể", "tier": "B", "desc": "Lôi Hỏa đan xen, tăng 10% Bạo Kích"},
        {"name": "Băng Phách Huyền Thủy", "tier": "B", "desc": "Đóng băng vạn vật, tăng 8% Né Tránh"}
    ],
    "A": [
        {"name": "Thái Cực Âm Dương Căn", "tier": "A", "desc": "Hóa giải sát thương, phản 8% đòn đánh"},
        {"name": "Hỗn Nguyên Kim Cương Căn", "tier": "A", "desc": "Thân thể bất hoại, tăng 12% Giáp"}
    ],
    "S": [
        {"name": "Tử Tiêu Thần Lôi Căn", "tier": "S", "desc": "Lôi kiếp tối thượng, 12% bỏ qua giáp"},
        {"name": "Đại Nhật Kim Ô Căn", "tier": "S", "desc": "Thiêu đốt chân nguyên đối phương"}
    ],
    "SS": [
        {"name": "Hỗn Độn Diệt Thế Lôi", "tier": "SS", "desc": "Diệt tuyệt sinh cơ, tăng 20% sát thương bạo"},
        {"name": "Hư Không Thời Không Căn", "tier": "SS", "desc": "Khống chế thời gian, tăng 15% Né và Tiên thủ"}
    ],
    "SSS": [
        {"name": "Tam Muội Chân Hỏa", "tier": "SSS", "desc": "Ngũ Đại Đỉnh Cao: Hỏa thần bất diệt, thiêu rụi giáp"},
        {"name": "Canh Kim Bạch Hổ", "tier": "SSS", "desc": "Ngũ Đại Đỉnh Cao: Sát phạt đệ nhất, tăng 25% Bạo kích"},
        {"name": "Ất Mộc Trường Sinh", "tier": "SSS", "desc": "Ngũ Đại Đỉnh Cao: Trường sinh bất tử, tăng 30% Hút máu"},
        {"name": "Thiên Nhất Chân Thủy", "tier": "SSS", "desc": "Ngũ Đại Đỉnh Cao: Hóa giải vạn pháp, tăng 20% Né tránh"},
        {"name": "Huyền Hoàng Tức Nhưỡng", "tier": "SSS", "desc": "Ngũ Đại Đỉnh Cao: Thổ thần vô địch, tăng 300 điểm Giáp"}
    ]
}

DESTINY_DATABASE = [
    {"name": "Khí Vận Chi Tử", "type": "Thiên Mệnh", "desc": "Thiên Đạo che chở, tăng gấp đôi tỉ lệ rơi Búa và Kỳ Ngộ"},
    {"name": "Chí Tôn Cốt", "type": "Dị Cốt", "desc": "Trời sinh Thần cốt, tăng vĩnh viễn 15% Sức mạnh và Bạo kích"},
    {"name": "Trùng Đồng Chi Nhãn", "type": "Dị Cốt", "desc": "Nhìn thấu kinh mạch, tăng 15% Né tránh"},
    {"name": "Bất Diệt Chân Huyết", "type": "Dị Cốt", "desc": "Khí huyết vô tận, tăng 25% HP tối đa"},
    {"name": "Hàn Băng Thần Thể", "type": "Dị Cốt", "desc": "Thân thể hàn băng, tăng 15% Giáp và phản kích"}
]

DEFAULT_EQUIPMENT = {
    "vk1": None, "vk2": None, "mu": None, "ao": None,
    "quan": None, "giay": None, "nhan1": None, "nhan2": None, "nhan3": None
}

ARMOR_CONSTANT = 600.0
CAP_DODGE = 70.0
CAP_LIFESTEAL = 50.0
CAP_STAT = 40.0

def calculate_total_stats(base: dict, eq: dict) -> dict:
    total = dict(base)
    for slot, item in eq.items():
        if item:
            mult = 1.0 + (item.get("enhance", 0) * 0.1)
            for k, v in item.get("stats", {}).items():
                total[k] = total.get(k, 0) + math.floor(v * mult)
    return total

class Fighter:
    def __init__(self, char_id: int, name: str, stats: dict, roots: list):
        self.char_id = char_id
        self.name = name
        self.max_hp = stats.get("hp", 100)
        self.current_hp = self.max_hp
        self.max_mp = stats.get("mp", 1000)
        self.current_mp = self.max_mp
        self.strength = stats.get("suc_manh", 100)
        self.speed = stats.get("toc_do", 100)
        self.armor = stats.get("thu", 0)
        
        self.dodge = min(CAP_DODGE, float(stats.get("ne_tranh", 0.0)))
        self.lifesteal = min(CAP_LIFESTEAL, float(stats.get("hut_mau", 0.0)))
        self.crit = min(CAP_STAT, float(stats.get("bao_kich", 0.0)))
        self.combo = min(CAP_STAT, float(stats.get("lien_kich", 0.0)))
        self.counter = min(CAP_STAT, float(stats.get("phan_kich", 0.0)))
        self.stun = min(CAP_STAT, float(stats.get("choang", 0.0)))
        self.is_stunned = False
        self.roots = roots

    def get_mitigation(self) -> float:
        if self.armor <= 0:
            return 0.0
        return self.armor / (self.armor + ARMOR_CONSTANT)

def simulate_battle(f1: Fighter, f2: Fighter):
    logs = []
    if f1.speed >= f2.speed:
        atk, df = f1, f2
    else:
        atk, df = f2, f1

    logs.append(f"⚡ Khởi tranh! {atk.name} (Tốc {atk.speed}) đoạt TIÊN THỦ trước {df.name} (Tốc {df.speed}).")
    turn = 0
    max_turns = 30

    while turn < max_turns and f1.current_hp > 0 and f2.current_hp > 0:
        turn += 1
        if turn % 2 == 0 and atk.current_mp < atk.max_mp:
            regen = max(1, math.floor(atk.max_mp * 0.01))
            atk.current_mp = min(atk.max_mp, atk.current_mp + regen)
            logs.append(f"🌀 [Hiệp {turn}] {atk.name} vận chuyển công pháp, hồi phục +{regen} MP ({atk.current_mp}/{atk.max_mp}).")

        if atk.is_stunned:
            logs.append(f"💫 [Hiệp {turn}] {atk.name} bị CHOÁNG, mất lượt thi triển!")
            atk.is_stunned = False
        else:
            execute_strike(atk, df, logs, turn, is_counter=False)
            if df.current_hp > 0 and random.uniform(0, 100) <= atk.combo:
                logs.append(f"⚡ [Hiệp {turn} - Liên Kích] {atk.name} bồi thêm một tuyệt kỹ áp sát!")
                execute_strike(atk, df, logs, turn, is_counter=False)

        if df.current_hp <= 0:
            break
        atk, df = df, atk

    winner = f1 if f1.current_hp > 0 and (f2.current_hp <= 0 or (f1.current_hp/f1.max_hp >= f2.current_hp/f2.max_hp)) else f2
    loser = f2 if winner == f1 else f1
    logs.append(f"🏆 KẾT THÚC! {winner.name} đã đả bại {loser.name}!")
    return {"winner_name": winner.name, "total_turns": turn, "logs": logs}

def execute_strike(atk: Fighter, df: Fighter, logs: list, turn: int, is_counter: bool = False):
    if random.uniform(0, 100) <= df.dodge:
        logs.append(f"💨 [Hiệp {turn}] {df.name} NÉ THÀNH CÔNG đòn đánh của {atk.name}!")
        if not is_counter and random.uniform(0, 100) <= (df.counter / 2.0):
            logs.append(f"⚡ [Hiệp {turn} - Né Phản] {df.name} mượn thế né đòn, lập tức PHẢN KÍCH!")
            execute_strike(df, atk, logs, turn, is_counter=True)
        return

    raw_dmg = atk.strength * (2 if random.uniform(0, 100) <= atk.crit else 1)
    is_crit = raw_dmg > atk.strength
    mitigation = df.get_mitigation()
    actual_dmg = max(1, math.floor(raw_dmg * (1.0 - mitigation)))
    df.current_hp = max(0, df.current_hp - actual_dmg)

    crit_tag = "💥 BẠO KÍCH! " if is_crit else ""
    counter_tag = "[Phản Đòn] " if is_counter else ""
    logs.append(f"⚔️ [Hiệp {turn}] {counter_tag}{atk.name} đánh trúng {crit_tag}gây {actual_dmg} ST (Giáp cản {mitigation*100:.1f}%). {df.name} còn {df.current_hp}/{df.max_hp} HP.")

    if atk.lifesteal > 0 and actual_dmg > 0:
        healed = max(1, math.floor(actual_dmg * (atk.lifesteal / 100.0)))
        atk.current_hp = min(atk.max_hp, atk.current_hp + healed)
        logs.append(f"🩸 {atk.name} hút {healed} HP.")

    if df.current_hp <= 0:
        return

    if random.uniform(0, 100) <= atk.stun:
        df.is_stunned = True
        logs.append(f"💫 {df.name} rơi vào trạng thái CHOÁNG!")
        return

    if not is_counter and random.uniform(0, 100) <= df.counter:
        logs.append(f"🛡️ [Hiệp {turn} - Phản Kích] {df.name} gồng mình đánh trả!")
        execute_strike(df, atk, logs, turn, is_counter=True)

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

@app.get("/api/slots/{telegram_id}")
def get_slots(telegram_id: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT slot_index, id, name, realm, age, linh_thach, hammers, pity_boss, is_dev, stats_json, roots_json, destiny_json, equipment_json, inventory_json 
        FROM characters WHERE telegram_id = ?
    """, (str(telegram_id),))
    rows = c.fetchall()
    conn.close()
    
    slots = {i: None for i in range(1, 6)}
    for r in rows:
        base_st = json.loads(r[9])
        eq = json.loads(r[12]) if r[12] else DEFAULT_EQUIPMENT
        tot_st = calculate_total_stats(base_st, eq)
        slots[r[0]] = {
            "char_id": r[1],
            "slot_index": r[0],
            "name": r[2],
            "realm": r[3],
            "age": r[4],
            "linh_thach": r[5],
            "hammers": r[6],
            "pity_boss": r[7],
            "is_dev": bool(r[8]),
            "base_stats": base_st,
            "total_stats": tot_st,
            "roots": json.loads(r[10]),
            "destiny": json.loads(r[11]) if r[11] else None,
            "equipment": eq,
            "inventory": json.loads(r[13]) if r[13] else []
        }
    return {"slots": slots}

@app.post("/api/characters/create")
def create_character(req: RollCharacterRequest):
    if not (1 <= req.slot_index <= 5):
        raise HTTPException(400, "Slot không hợp lệ (1-5)")

    is_dev = (req.admin_password == "DevGame")
    if is_dev:
        stats = {
            "hp": 99999, "mp": 99999, "suc_manh": 5000, "toc_do": 1200, "thu": 1500,
            "ne_tranh": 70.0, "hut_mau": 50.0, "bao_kich": 40.0, "lien_kich": 40.0, "phan_kich": 40.0, "choang": 40.0, "khi_van": 100
        }
        roots = ROOT_DATABASE["SSS"][:5] + ROOT_DATABASE["SS"][:2]
        destiny = {"name": "Chí Tôn Cốt & Khí Vận Chi Tử", "type": "Song Sinh Chí Tôn", "desc": "Mở khóa toàn bộ uy năng thiên địa"}
        realm = "Thần Đạo Cảnh"
        lt = 999999
        hammers = 99
    else:
        tc = req.allocated_points.get("the_chat", 8)
        sm = req.allocated_points.get("suc_manh", 8)
        tp = req.allocated_points.get("than_phap", 7)
        cc = req.allocated_points.get("can_cot", 7)

        stats = {
            "hp": 100 + tc * 25,
            "mp": 1000,
            "suc_manh": 50 + sm * 8,
            "toc_do": 50 + tp * 6,
            "thu": 20 + cc * 5,
            "ne_tranh": min(CAP_DODGE, float(tp * 0.5)),
            "bao_kich": min(CAP_STAT, float(sm * 0.5)),
            "lien_kich": 5.0,
            "phan_kich": min(CAP_STAT, float(cc * 0.5)),
            "choang": 0.0,
            "hut_mau": 0.0,
            "khi_van": random.randint(10, 30)
        }

        root_count = random.choices([1, 2, 3, 4, 5], weights=[35, 30, 20, 10, 5])[0]
        chosen_roots = []
        for _ in range(root_count):
            tier = random.choices(["D", "C", "B", "A", "S", "SS", "SSS"], weights=[50, 25, 12, 7, 4, 1.5, 0.5])[0]
            root_item = random.choice(ROOT_DATABASE[tier])
            if root_item not in chosen_roots:
                chosen_roots.append(root_item)

        roots = chosen_roots
        destiny = random.choice(DESTINY_DATABASE)
        realm = "Phàm Nhân"
        lt = 300
        hammers = 1

    starter_equip = dict(DEFAULT_EQUIPMENT)
    starter_equip["vk1"] = {"name": "Mộc Kiếm Phàm Phẩm", "type": "vk1", "enhance": 0, "stats": {"suc_manh": 20, "bao_kich": 2.0}, "price": 100}

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (telegram_id, username) VALUES (?, ?)", (str(req.telegram_id), req.username))
    c.execute("DELETE FROM characters WHERE telegram_id = ? AND slot_index = ?", (str(req.telegram_id), req.slot_index))
    
    c.execute("""
        INSERT INTO characters (telegram_id, slot_index, name, realm, age, linh_thach, hammers, pity_boss, is_dev, stats_json, roots_json, destiny_json, equipment_json, inventory_json)
        VALUES (?, ?, ?, ?, 1, ?, ?, 0, ?, ?, ?, ?, ?, ?)
    """, (
        str(req.telegram_id), req.slot_index, req.name, realm, lt, hammers,
        1 if is_dev else 0, json.dumps(stats), json.dumps(roots), json.dumps(destiny),
        json.dumps(starter_equip), json.dumps([])
    ))
    conn.commit()
    conn.close()
    return {"status": "success", "is_dev": is_dev}

@app.post("/api/characters/delete")
def delete_character(req: DeleteCharRequest):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, name FROM characters WHERE telegram_id = ? AND slot_index = ?", (str(req.telegram_id), req.slot_index))
    row = c.fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, "Không tìm thấy nhân vật!")
    if row[1].strip() != req.confirm_name.strip():
        conn.close()
        raise HTTPException(400, "Tên xác nhận không trùng khớp!")

    c.execute("DELETE FROM characters WHERE id = ?", (row[0],))
    conn.commit()
    conn.close()
    return {"status": "success"}

# --- CỐT TRUYỆN PHÀM NHÂN TU TIÊN (TỈ LỆ RƠI LINH THẠCH CÓ XÁC SUẤT) ---
@app.post("/api/action/story_step")
def story_step(req: ActionRequest):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, age, linh_thach, realm, stats_json FROM characters WHERE id = ?", (req.char_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, "Không tìm thấy nhân vật!")

    age = row[1] + 1
    curr_lt = row[2]
    stats = json.loads(row[4])
    stats["hp"] += 20
    stats["suc_manh"] += 8
    stats["mp"] += 30

    # Phân loại biến cố theo xác suất:
    # 40% Bế quan bình cảnh (0 Linh Thạch)
    # 35% Thu hoạch bình thường (50 - 180 Linh Thạch)
    # 15% Kỳ ngộ Chưởng Thiên Bình (300 - 600 Linh Thạch + buff mạnh)
    # 10% Tán tu cướp bóc / Hao hụt chi phí (-40 đến -100 Linh Thạch)
    roll_event = random.uniform(0, 100)
    gain_lt = 0

    if age <= 9:
        if age <= 5:
            events_early = [
                f"Năm {age} tuổi: Sinh ra tại Thanh Ngưu Trấn, gia cảnh bần hàn, hàng ngày giúp phụ mẫu đốn củi chăn trâu.",
                f"Năm {age} tuổi: Thân hình gầy gò đen đúa nhưng tính tình trầm ổn kiên nghị, bắt đầu nhận biết sự đời.",
                f"Năm {age} tuổi: Cùng đám trẻ trong thôn nô đùa bên bờ suối, cơ thể khỏe mạnh cứng cáp dần."
            ]
            log = random.choice(events_early)
        else:
            if roll_event < 60:
                log = f"Năm {age} tuổi: Được Tam Thúc tiến cử lên Thất Huyền Môn, nhẫn nại vượt qua khảo sát Thần Kê Cốc."
            elif roll_event < 90:
                gain_lt = random.randint(30, 80)
                log = f"Năm {age} tuổi: Được Mặc Đại Phu thu nhận làm đệ tử ký danh tại Thần Thủ Cốc, được thưởng ít bạc vụn quy đổi thành {gain_lt} Linh Thạch."
            else:
                log = f"Năm {age} tuổi: Khổ luyện Trường Xuân Công nhưng tiến độ cực kỳ chậm chạp do tư chất bình thường, không có thu hoạch."
    elif age <= 15:
        if roll_event < 40:
            # Bình cảnh
            log = f"Năm {age} tuổi: Khổ tu Trường Xuân Công nhưng đan điền bế tắc, tiến độ dậm chân tại chỗ, không thu hoạch được Linh Thạch."
        elif roll_event < 75:
            # Nhặt dược liệu / Chế thuốc
            gain_lt = random.randint(60, 150)
            log = f"Năm {age} tuổi: Lên núi hái thuốc phụ giúp Mặc Đại Phu bào chế độc dược, lén giữ lại ít thảo dược quý bán đổi {gain_lt} Linh Thạch."
        elif roll_event < 90:
            # Kỳ ngộ Chưởng Thiên Bình
            gain_lt = random.randint(250, 500)
            stats["suc_manh"] += 20
            log = f"Năm {age} tuổi: ✨ [KỲ NGỘ] Nhặt được Lục Sắc Tiểu Bình (Chưởng Thiên Bình) hấp thu ánh trăng ngưng tụ lục dịch! Thúc chín hoàng tinh ngàn năm, bán thu về {gain_lt} Linh Thạch!"
        else:
            # Trắc trở
            gain_lt = -random.randint(40, 80)
            log = f"Năm {age} tuổi: Mặc Đại Phu nổi sát tâm mưu toan Đoạt Xá! Bạn phải kích hoạt phù chú tự vệ tiêu tốn nhiều tài nguyên ({gain_lt} Linh Thạch) để phản sát!"
    elif age <= 25:
        if roll_event < 40:
            log = f"Năm {age} tuổi: Bế quan trong Bách Dược Viên của Hoàng Phong Cốc, ngày đêm ngồi thiền thổ nạp mà chưa phá được bình cảnh."
        elif roll_event < 75:
            gain_lt = random.randint(80, 200)
            log = f"Năm {age} tuổi: Trồng trọt linh điền, nộp cống nạp tông môn đầy đủ, được ban thưởng {gain_lt} Linh Thạch."
        elif roll_event < 90:
            gain_lt = random.randint(300, 600)
            stats["hp"] += 50
            log = f"Năm {age} tuổi: 💥 Đại náo Huyết Sắc Thí Luyện! Dùng trí trảm sát các đệ tử Ma Đạo đoạt bảo hòm thuốc quý, thu về {gain_lt} Linh Thạch!"
        else:
            gain_lt = -random.randint(60, 120)
            log = f"Năm {age} tuổi: Bị phong ba tranh đoạt Trúc Cơ Đan cuốn vào, phải dùng linh thạch mua bùa chú hộ mệnh chạy trốn ({gain_lt} Linh Thạch)."
    else:
        if roll_event < 40:
            log = f"Năm {age} tuổi: Tại Loạn Tinh Hải xa xôi bế quan ngưng tụ nội đan, tu vi tăng tiến nhưng linh thạch không đổi."
        elif roll_event < 75:
            gain_lt = random.randint(120, 250)
            log = f"Năm {age} tuổi: Đi thuyền săn giết Yêu Thú biển sâu lấy nội đan, giao dịch tại Thiên Tinh Thành thu về {gain_lt} Linh Thạch."
        elif roll_event < 90:
            gain_lt = random.randint(400, 800)
            stats["suc_manh"] += 30
            log = f"Năm {age} tuổi: 🌟 Khám phá di tích cổ trận Loạn Tinh Hải, nhặt được di vật của bậc tiền bối hóa thần! (+{gain_lt} Linh Thạch)."
        else:
            gain_lt = -random.randint(80, 150)
            log = f"Năm {age} tuổi: Chạm trán Đảo Chủ tà tu chặn đường cướp bóc, giao tranh dữ dội làm hư hao pháp bảo ({gain_lt} Linh Thạch)."

    new_lt = max(0, curr_lt + gain_lt)

    # Đột phá cảnh giới
    new_realm = row[3]
    if age == 8 and row[3] == "Phàm Nhân":
        new_realm = "Luyện Khí Tầng 1"
        log += " 🌟 [ĐỘT PHÁ] Cảm ứng được linh khí thiên địa, chính thức bước vào [Luyện Khí Tầng 1]!"
    elif age % 6 == 0 and row[3] in REALMS:
        curr_idx = REALMS.index(row[3])
        if curr_idx < len(REALMS) - 1:
            new_realm = REALMS[curr_idx + 1]
            log += f" 🌟 [ĐỘT PHÁ] Trúc cơ thành tựu / Ngưng đan hóa thần, tấn thăng [{new_realm}]!"

    c.execute("UPDATE characters SET age = ?, linh_thach = ?, realm = ?, stats_json = ? WHERE id = ?", (age, new_lt, new_realm, json.dumps(stats), req.char_id))
    conn.commit()
    conn.close()
    return {"status": "success", "log": log, "age": age, "linh_thach": new_lt, "realm": new_realm}

@app.post("/api/action/hunt_boss")
def hunt_boss(req: ActionRequest):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, linh_thach, hammers, pity_boss, stats_json FROM characters WHERE id = ?", (req.char_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, "Không tìm thấy nhân vật!")

    lt, hammers, pity = row[1], row[2], row[3] + 1
    stats = json.loads(row[4])
    gain_lt = random.randint(250, 500)
    lt += gain_lt

    drop_rate = 1.0 + (stats.get("khi_van", 0) / 100.0)
    got_hammer = False

    if pity >= 80 or random.uniform(0, 100) <= drop_rate:
        got_hammer = True
        hammers += 1
        pity = 0
        msg = f"🎉 TRẢM SÁT THÀNH CÔNG YÊU VƯƠNG! Rơi 1 THIÊN CÔNG THẦN CHÙY (Búa)! (+{gain_lt} Linh Thạch)"
    else:
        msg = f"Trảm sát Yêu Thú Loạn Tinh Hải, thu hoạch nội đan đổi +{gain_lt} Linh Thạch. Búa chưa xuất hiện. (Bảo hiểm: {pity}/80)"

    c.execute("UPDATE characters SET linh_thach = ?, hammers = ?, pity_boss = ? WHERE id = ?", (lt, hammers, pity, req.char_id))
    conn.commit()
    conn.close()
    return {"status": "success", "msg": msg, "got_hammer": got_hammer, "hammers": hammers, "linh_thach": lt, "pity": pity}

@app.post("/api/action/enhance")
def enhance_equipment(req: EnhanceRequest):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, hammers, linh_thach, equipment_json FROM characters WHERE id = ?", (req.char_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, "Không tìm thấy nhân vật!")

    hammers, lt = row[1], row[2]
    equipment = json.loads(row[3])
    item = equipment.get(req.slot_key)

    if not item:
        conn.close()
        raise HTTPException(400, "Vị trí này chưa đeo trang bị!")
    if hammers < 1 or lt < 250:
        conn.close()
        raise HTTPException(400, "Không đủ Búa Cường Hóa hoặc thiếu 250 Linh Thạch!")
    if item.get("enhance", 0) >= 20:
        conn.close()
        raise HTTPException(400, "Trang bị đã chạm trần Cực Hạn (+20)!")

    hammers -= 1
    lt -= 250
    current_lv = item.get("enhance", 0)
    success = random.uniform(0, 100) <= 75.0

    if success:
        item["enhance"] = current_lv + 1
        msg = f"✨ THÀNH CÔNG! {item['name']} thăng cấp lên +{item['enhance']}!"
    else:
        if current_lv > 15:
            item["enhance"] = max(15, current_lv - 1)
        elif current_lv > 10:
            item["enhance"] = max(10, current_lv - 1)
        msg = f"💔 THẤT BẠI! Cường hóa trượt tiêu hao 1 Búa. Cấp bảo toàn: +{item['enhance']}."

    equipment[req.slot_key] = item
    c.execute("UPDATE characters SET hammers = ?, linh_thach = ?, equipment_json = ? WHERE id = ?", (hammers, lt, json.dumps(equipment), req.char_id))
    conn.commit()
    conn.close()
    return {"status": "success", "msg": msg, "new_enhance": item["enhance"], "hammers": hammers, "linh_thach": lt}

@app.post("/api/action/sell_item")
def sell_item(req: SellRequest):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, linh_thach, inventory_json FROM characters WHERE id = ?", (req.char_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, "Không tìm thấy nhân vật!")

    lt = row[1]
    inv = json.loads(row[2])
    if req.inv_index < 0 or req.inv_index >= len(inv):
        conn.close()
        raise HTTPException(400, "Vật phẩm không tồn tại!")

    item = inv.pop(req.inv_index)
    refund = math.floor(item.get("price", 100) * 0.7)
    lt += refund

    c.execute("UPDATE characters SET linh_thach = ?, inventory_json = ? WHERE id = ?", (lt, json.dumps(inv), req.char_id))
    conn.commit()
    conn.close()
    return {"status": "success", "msg": f"Đã bán {item['name']}, hoàn lại {refund} Linh Thạch (70%).", "linh_thach": lt}

SHOP_CATALOG = {
    "item_dan_mp": {"name": "Cửu Chuyển Hồi Linh Đan", "type": "dan_duoc", "effect": "Hồi 35% Max MP", "price": 400},
    "item_vk_kiem": {"name": "Thanh Vân Tiên Kiếm (Huyền Phẩm)", "type": "vk2", "stats": {"suc_manh": 120, "lien_kich": 6.0}, "price": 1200},
    "item_ao_giap": {"name": "Huyền Vũ Hộ Tâm Giáp", "type": "ao", "stats": {"thu": 180, "hp": 400}, "price": 1500},
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

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, linh_thach, hammers, inventory_json, equipment_json FROM characters WHERE id = ?", (req.char_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, "Không tìm thấy nhân vật!")

    lt, hammers = row[1], row[2]
    inv = json.loads(row[3])
    eq = json.loads(row[4])

    if lt < cost:
        conn.close()
        raise HTTPException(400, "Không đủ Linh Thạch!")
    if len(inv) >= 500:
        conn.close()
        raise HTTPException(400, "Túi trữ vật đã đầy (500 slot)!")

    lt -= cost
    if req.item_id == "item_bua_ren":
        hammers += 1
        msg = "Mua thành công 1 Búa Cường Hóa!"
    elif req.item_id == "item_dan_mp":
        inv.append({"name": item["name"], "type": "dan_duoc", "price": cost, "desc": item["effect"]})
        msg = f"Mua thành công {item['name']} (Đã cất vào túi)."
    else:
        slot = item["type"]
        eq[slot] = {"name": item["name"], "type": slot, "enhance": 0, "stats": item["stats"], "price": cost}
        msg = f"Mua thành công {item['name']} và đã tự động trang bị vào vị trí [{slot}]!"

    c.execute("UPDATE characters SET linh_thach = ?, hammers = ?, inventory_json = ?, equipment_json = ? WHERE id = ?", (lt, hammers, json.dumps(inv), json.dumps(eq), req.char_id))
    conn.commit()
    conn.close()
    return {"status": "success", "msg": msg, "linh_thach": lt, "hammers": hammers}

@app.get("/api/pvp/lobby")
def get_pvp_lobby(exclude_id: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT id, name, realm, is_dev, stats_json, equipment_json 
        FROM characters WHERE id != ? ORDER BY id DESC LIMIT 25
    """, (exclude_id,))
    rows = c.fetchall()
    conn.close()
    
    res = []
    for r in rows:
        base_st = json.loads(r[4])
        eq = json.loads(r[5]) if r[5] else DEFAULT_EQUIPMENT
        tot_st = calculate_total_stats(base_st, eq)
        res.append({
            "id": r[0], "name": r[1], "realm": r[2], "is_dev": bool(r[3]),
            "hp": tot_st.get("hp", 100), "speed": tot_st.get("toc_do", 100)
        })
    return {"opponents": res}

@app.post("/api/pvp/challenge")
def challenge_opponent(req: ChallengeRequest):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, name, stats_json, roots_json, equipment_json FROM characters WHERE id = ?", (req.challenger_char_id,))
    c1 = c.fetchone()
    c.execute("SELECT id, name, stats_json, roots_json, equipment_json FROM characters WHERE id = ?", (req.target_char_id,))
    c2 = c.fetchone()
    conn.close()

    if not c1 or not c2:
        raise HTTPException(404, "Nhân vật không tồn tại!")

    tot1 = calculate_total_stats(json.loads(c1[2]), json.loads(c1[4]) if c1[4] else DEFAULT_EQUIPMENT)
    tot2 = calculate_total_stats(json.loads(c2[2]), json.loads(c2[4]) if c2[4] else DEFAULT_EQUIPMENT)

    f1 = Fighter(c1[0], c1[1], tot1, json.loads(c1[3]))
    f2 = Fighter(c2[0], c2[1], tot2, json.loads(c2[3]))
    return simulate_battle(f1, f2)

app.mount("/", StaticFiles(directory="static", html=True), name="static")
