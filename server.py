import sqlite3
import json
import math
import random
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="Cultivation Game Engine Full")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_PATH = "game.db"

# --- KHỞI TẠO CƠ SỞ DỮ LIỆU ---
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
            realm TEXT DEFAULT 'Luyện Khí Tầng 1',
            age INTEGER DEFAULT 16,
            linh_thach INTEGER DEFAULT 1000,
            hammers INTEGER DEFAULT 0,
            pity_boss INTEGER DEFAULT 0,
            is_dev BOOLEAN DEFAULT 0,
            stats_json TEXT,
            roots_json TEXT,
            inventory_json TEXT,
            equipment_json TEXT,
            UNIQUE(telegram_id, slot_index)
        )
    """)
    conn.commit()
    conn.close()

init_db()

# --- HẰNG SỐ & COMBAT ENGINE ---
ARMOR_CONSTANT = 600.0
CAP_DODGE = 70.0
CAP_LIFESTEAL = 50.0
CAP_STAT = 40.0

DEFAULT_EQUIPMENT = {
    "vk1": None, "vk2": None, "mu": None, "ao": None,
    "quan": None, "giay": None, "nhan1": None, "nhan2": None, "nhan3": None
}

REALMS = [
    "Luyện Khí Tầng 1", "Luyện Khí Tầng 5", "Trúc Cơ Sơ Kỳ", "Trúc Cơ Viên Mãn",
    "Kim Đan Sơ Kỳ", "Kim Đan Cực Hạn", "Nguyên Anh Kỳ", "Hóa Thần Kỳ", "Độ Kiếp Viên Mãn", "Thần Đạo Cảnh"
]

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

def simulate_pvp_battle(f1: Fighter, f2: Fighter):
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
            logs.append(f"🌀 [Hiệp {turn}] {atk.name} hồi phục +{regen} MP ({atk.current_mp}/{atk.max_mp}).")

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
    
    return {"winner_id": winner.char_id, "winner_name": winner.name, "total_turns": turn, "logs": logs}

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

def calculate_character_total_stats(base_stats: dict, equipment: dict) -> dict:
    total = dict(base_stats)
    for slot, item in equipment.items():
        if item:
            enhance_mult = 1.0 + (item.get("enhance", 0) * 0.1)
            for k, v in item.get("stats", {}).items():
                if k in total:
                    total[k] += math.floor(v * enhance_mult)
                else:
                    total[k] = math.floor(v * enhance_mult)
    return total

# --- PDUANTIC SCHEMAS ---
class CreateCharRequest(BaseModel):
    telegram_id: str
    username: Optional[str] = "Đạo Hữu"
    slot_index: int
    name: str
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

# --- APIS QUẢN LÝ SLOT (ĐÃ SỬA LỖI TRIỆT ĐỂ) ---
@app.get("/api/slots/{telegram_id}")
def get_user_slots(telegram_id: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT slot_index, id, name, realm, age, linh_thach, hammers, pity_boss, is_dev, stats_json, roots_json, equipment_json, inventory_json 
        FROM characters WHERE telegram_id = ?
    """, (str(telegram_id),))
    rows = c.fetchall()
    conn.close()
    
    slots = {i: None for i in range(1, 6)}
    for r in rows:
        base_stats = json.loads(r[9])
        eq = json.loads(r[11]) if r[11] else DEFAULT_EQUIPMENT
        total_stats = calculate_character_total_stats(base_stats, eq)
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
            "base_stats": base_stats,
            "total_stats": total_stats,
            "roots": json.loads(r[10]),
            "equipment": eq,
            "inventory": json.loads(r[12]) if r[12] else []
        }
    return {"slots": slots}

@app.post("/api/characters/create")
def create_character(req: CreateCharRequest):
    if not (1 <= req.slot_index <= 5):
        raise HTTPException(400, "Slot không hợp lệ (1-5)")

    is_dev = (req.admin_password == "DevGame")
    if is_dev:
        stats = {
            "hp": 99999, "mp": 99999, "suc_manh": 5000, "toc_do": 1200, "thu": 1500,
            "ne_tranh": 70.0, "hut_mau": 50.0, "bao_kich": 40.0, "lien_kich": 40.0, "phan_kich": 40.0, "choang": 40.0, "khi_van": 100
        }
        roots = ["Tam Muội Chân Hỏa (SSS)", "Canh Kim Bạch Hổ (SSS)", "Ất Mộc Trường Sinh (SSS)", "Thiên Nhất Chân Thủy (SSS)", "Huyền Hoàng Tức Nhưỡng (SSS)", "Tử Tiêu Thần Lôi (SS)", "Hỗn Độn Linh Căn (SSS)"]
        realm = "Thần Đạo Cảnh"
        lt = 999999
        hammers = 99
    else:
        stats = {
            "hp": 100, "mp": 1000, "suc_manh": 100, "toc_do": 100, "thu": 50,
            "ne_tranh": 5.0, "hut_mau": 0.0, "bao_kich": 5.0, "lien_kich": 5.0, "phan_kich": 5.0, "choang": 0.0, "khi_van": 10
        }
        all_roots = ["Bính Hỏa (Bậc D)", "Ất Mộc (Bậc D)", "Huyền Thủy (Bậc D)", "Lôi Biến Dị (Bậc C)", "Băng Phách (Bậc C)", "Phong Linh Căn (Bậc C)"]
        roots = random.sample(all_roots, 2)
        realm = "Luyện Khí Tầng 1"
        lt = 1000
        hammers = 2

    starter_equip = dict(DEFAULT_EQUIPMENT)
    starter_equip["vk1"] = {"name": "Mộc Kiếm Phàm Phẩm", "type": "vk1", "enhance": 0, "stats": {"suc_manh": 30, "bao_kich": 2.0}, "price": 200}
    starter_equip["ao"] = {"name": "Thô Bố Y", "type": "ao", "enhance": 0, "stats": {"thu": 40, "hp": 50}, "price": 200}

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (telegram_id, username) VALUES (?, ?)", (str(req.telegram_id), req.username))
    
    # XÓA BẢN GHI RÁC ĐỂ TRÁNH XUNG ĐỘT KHÓA UNIQUE
    c.execute("DELETE FROM characters WHERE telegram_id = ? AND slot_index = ?", (str(req.telegram_id), req.slot_index))
    
    c.execute("""
        INSERT INTO characters (telegram_id, slot_index, name, realm, age, linh_thach, hammers, pity_boss, is_dev, stats_json, roots_json, inventory_json, equipment_json)
        VALUES (?, ?, ?, ?, 16, ?, ?, 0, ?, ?, ?, ?, ?)
    """, (
        str(req.telegram_id), req.slot_index, req.name, realm, lt, hammers,
        1 if is_dev else 0, json.dumps(stats), json.dumps(roots),
        json.dumps([]), json.dumps(starter_equip)
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

    # XÓA VĨNH VIỄN KHỎI DATABASE ĐỂ GIẢI PHÓNG SLOT
    c.execute("DELETE FROM characters WHERE id = ?", (row[0],))
    conn.commit()
    conn.close()
    return {"status": "success"}

# --- CÁC TÍNH NĂNG GAMEPLAY ---
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
    gain_lt = random.randint(150, 400)
    new_lt = row[2] + gain_lt
    stats = json.loads(row[4])
    stats["hp"] += 20
    stats["suc_manh"] += 10
    stats["mp"] += 50

    events = [
        f"Năm {age} tuổi: Bế quan tu luyện, hấp thu linh khí thiên địa, thu hoạch {gain_lt} Linh Thạch.",
        f"Năm {age} tuổi: Hoàn thành nhiệm vụ tông môn phân phó, được ban thưởng {gain_lt} Linh Thạch.",
        f"Năm {age} tuổi: Xuống núi diệt trừ yêu thú quấy phá phàm nhân, nhặt được {gain_lt} Linh Thạch trong sào huyệt."
    ]
    log = random.choice(events)

    new_realm = row[3]
    if age % 5 == 0:
        idx = min(len(REALMS)-1, REALMS.index(row[3]) + 1 if row[3] in REALMS else 0)
        new_realm = REALMS[idx]
        log += f" 🌟 ĐẠT CƠ DUYÊN ĐỘT PHÁ! Tiến nhập [{new_realm}]!"

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
    gain_lt = random.randint(300, 600)
    lt += gain_lt

    drop_rate = 1.0 + (stats.get("khi_van", 0) / 100.0)
    got_hammer = False

    if pity >= 80 or random.uniform(0, 100) <= drop_rate:
        got_hammer = True
        hammers += 1
        pity = 0
        msg = f"🎉 TRẢM SÁT THÀNH CÔNG YÊU VƯƠNG! Rơi 1 THIÊN CÔNG THẦN CHÙY (Búa)! (+{gain_lt} Linh Thạch)"
    else:
        msg = f"Đánh bại Boss Yêu Thú, thu hoạch +{gain_lt} Linh Thạch. Búa chưa xuất hiện. (Bảo hiểm: {pity}/80)"

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
    if hammers < 1 or lt < 300:
        conn.close()
        raise HTTPException(400, "Không đủ Búa Cường Hóa hoặc thiếu 300 Linh Thạch!")
    if item.get("enhance", 0) >= 20:
        conn.close()
        raise HTTPException(400, "Trang bị đã chạm trần Cực Hạn (+20)!")

    hammers -= 1
    lt -= 300
    current_lv = item.get("enhance", 0)
    success = random.uniform(0, 100) <= 75.0

    if success:
        item["enhance"] = current_lv + 1
        msg = f"✨ THÀNH CÔNG! {item['name']} đã thăng cấp lên +{item['enhance']}!"
    else:
        if current_lv > 15:
            item["enhance"] = max(15, current_lv - 1)
        elif current_lv > 10:
            item["enhance"] = max(10, current_lv - 1)
        msg = f"💔 THẤT BẠI! Cường hóa thất bại tiêu hao 1 Búa. Cấp hiện tại: +{item['enhance']}."

    equipment[req.slot_key] = item
    c.execute("UPDATE characters SET hammers = ?, linh_thach = ?, equipment_json = ? WHERE id = ?", (hammers, lt, json.dumps(equipment), req.char_id))
    conn.commit()
    conn.close()
    return {"status": "success", "msg": msg, "success": success, "new_enhance": item["enhance"], "hammers": hammers, "linh_thach": lt}

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
        raise HTTPException(400, "Vật phẩm không tồn tại trong túi!")

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
    "item_bua_ren": {"name": "Thiên Công Thần Chùy (Búa)", "type": "bua", "price": 2500}
}

@app.post("/api/action/buy_item")
def buy_item(req: BuyRequest):
    if req.item_id not in SHOP_CATALOG:
        raise HTTPException(400, "Vật phẩm không có trong thương các!")

    item_template = SHOP_CATALOG[req.item_id]
    cost = item_template["price"]

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
        raise HTTPException(400, "Linh thạch không đủ để giao dịch!")
    if len(inv) >= 500:
        conn.close()
        raise HTTPException(400, "Túi trữ vật đã đầy (500/500 slot)!")

    lt -= cost
    if req.item_id == "item_bua_ren":
        hammers += 1
        msg = "Mua thành công 1 Thiên Công Thần Chùy!"
    elif req.item_id == "item_dan_mp":
        inv.append({"name": item_template["name"], "type": "dan_duoc", "price": cost, "desc": item_template["effect"]})
        msg = f"Mua thành công {item_template['name']} (Cất vào túi đồ)."
    else:
        slot = item_template["type"]
        new_equip = {"name": item_template["name"], "type": slot, "enhance": 0, "stats": item_template["stats"], "price": cost}
        eq[slot] = new_equip
        msg = f"Mua thành công {item_template['name']} và đã tự động trang bị vào vị trí [{slot}]!"

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
        tot_st = calculate_character_total_stats(base_st, eq)
        res.append({
            "id": r[0], "name": r[1], "realm": r[2], "is_dev": bool(r[3]),
            "hp": tot_st.get("hp", 100), "speed": tot_st.get("toc_do", 100), "strength": tot_st.get("suc_manh", 100)
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

    tot1 = calculate_character_total_stats(json.loads(c1[2]), json.loads(c1[4]) if c1[4] else DEFAULT_EQUIPMENT)
    tot2 = calculate_character_total_stats(json.loads(c2[2]), json.loads(c2[4]) if c2[4] else DEFAULT_EQUIPMENT)

    f1 = Fighter(c1[0], c1[1], tot1, json.loads(c1[3]))
    f2 = Fighter(c2[0], c2[1], tot2, json.loads(c2[3]))
    return simulate_pvp_battle(f1, f2)

app.mount("/", StaticFiles(directory="static", html=True), name="static")
