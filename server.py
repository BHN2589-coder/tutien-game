import sqlite3
import json
import math
import random
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="Cultivation Game Engine")

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
            realm TEXT DEFAULT 'Luyện Khí Tầng 1',
            is_dev BOOLEAN DEFAULT 0,
            stats_json TEXT,
            roots_json TEXT,
            inventory_json TEXT,
            equipment_json TEXT,
            is_deleted BOOLEAN DEFAULT 0,
            UNIQUE(telegram_id, slot_index)
        )
    """)
    conn.commit()
    conn.close()

init_db()

ARMOR_CONSTANT = 600.0
CAP_DODGE = 70.0
CAP_LIFESTEAL = 50.0
CAP_STAT = 40.0

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
        
        self.dodge = min(CAP_DODGE, stats.get("ne_tranh", 0.0))
        self.lifesteal = min(CAP_LIFESTEAL, stats.get("hut_mau", 0.0))
        self.crit = min(CAP_STAT, stats.get("bao_kich", 0.0))
        self.combo = min(CAP_STAT, stats.get("lien_kich", 0.0))
        self.counter = min(CAP_STAT, stats.get("phan_kich", 0.0))
        self.stun = min(CAP_STAT, stats.get("choang", 0.0))
        
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

    logs.append(f"⚡ Khởi tranh! {atk.name} (Tốc {atk.speed}) giành TIÊN THỦ trước {df.name} (Tốc {df.speed}).")
    turn = 0
    max_turns = 30

    while turn < max_turns and f1.current_hp > 0 and f2.current_hp > 0:
        turn += 1
        if turn % 2 == 0 and atk.current_mp < atk.max_mp:
            regen = max(1, math.floor(atk.max_mp * 0.01))
            atk.current_mp = min(atk.max_mp, atk.current_mp + regen)
            logs.append(f"🌀 [Hiệp {turn}] {atk.name} hồi phục +{regen} MP ({atk.current_mp}/{atk.max_mp}).")

        if atk.is_stunned:
            logs.append(f"💫 [Hiệp {turn}] {atk.name} bị CHOÁNG, mất lượt!")
            atk.is_stunned = False
        else:
            execute_strike(atk, df, logs, turn, is_counter=False)
            if df.current_hp > 0 and random.uniform(0, 100) <= atk.combo:
                logs.append(f"⚡ [Hiệp {turn} - Liên Kích] {atk.name} bồi thêm một kích!")
                execute_strike(atk, df, logs, turn, is_counter=False)

        if df.current_hp <= 0:
            break
        atk, df = df, atk

    winner = f1 if f1.current_hp > 0 and (f2.current_hp <= 0 or (f1.current_hp/f1.max_hp >= f2.current_hp/f2.max_hp)) else f2
    loser = f2 if winner == f1 else f1
    logs.append(f"🏆 KẾT THÚC! {winner.name} đả bại {loser.name}!")
    
    return {"winner_id": winner.char_id, "winner_name": winner.name, "total_turns": turn, "logs": logs}

def execute_strike(atk: Fighter, df: Fighter, logs: list, turn: int, is_counter: bool = False):
    if random.uniform(0, 100) <= df.dodge:
        logs.append(f"💨 [Hiệp {turn}] {df.name} NÉ THÀNH CÔNG đòn đánh của {atk.name}!")
        if not is_counter and random.uniform(0, 100) <= (df.counter / 2.0):
            logs.append(f"⚡ [Hiệp {turn} - Né Phản] {df.name} mượn thế né, PHẢN KÍCH!")
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
        logs.append(f"🛡️ [Hiệp {turn} - Phản Kích] {df.name} đánh trả!")
        execute_strike(df, atk, logs, turn, is_counter=True)

class CreateCharRequest(BaseModel):
    telegram_id: str
    username: Optional[str] = "Đạo Hữu"
    slot_index: int
    name: str
    stats: dict
    roots: list
    admin_password: Optional[str] = None

class ChallengeRequest(BaseModel):
    challenger_char_id: int
    target_char_id: int

class DeleteCharRequest(BaseModel):
    telegram_id: str
    slot_index: int
    confirm_name: str

@app.get("/api/slots/{telegram_id}")
def get_user_slots(telegram_id: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT slot_index, id, name, realm, is_dev, stats_json, roots_json FROM characters WHERE telegram_id = ? AND is_deleted = 0", (telegram_id,))
    rows = c.fetchall()
    conn.close()
    
    slots = {i: None for i in range(1, 6)}
    for r in rows:
        slots[r[0]] = {
            "char_id": r[1],
            "name": r[2],
            "realm": r[3],
            "is_dev": bool(r[4]),
            "stats": json.loads(r[5]),
            "roots": json.loads(r[6])
        }
    return {"slots": slots}

@app.post("/api/characters/create")
def create_character(req: CreateCharRequest):
    if not (1 <= req.slot_index <= 5):
        raise HTTPException(400, "Slot không hợp lệ (1-5)")

    is_dev = (req.admin_password == "DevGame")
    final_stats = req.stats
    if not is_dev:
        final_stats = {
            "hp": 100, "mp": 1000, "suc_manh": 100, "toc_do": 100, "thu": 0,
            "ne_tranh": 0, "hut_mau": 0, "bao_kich": 0, "lien_kich": 0, "phan_kich": 0, "choang": 0
        }

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (telegram_id, username) VALUES (?, ?)", (req.telegram_id, req.username))
    try:
        c.execute("""
            INSERT INTO characters (telegram_id, slot_index, name, is_dev, stats_json, roots_json, inventory_json, equipment_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            req.telegram_id, req.slot_index, req.name, 1 if is_dev else 0,
            json.dumps(final_stats), json.dumps(req.roots[:7]), json.dumps([]), json.dumps({})
        ))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(400, "Slot này đã có nhân vật!")
    conn.close()
    return {"status": "success", "is_dev": is_dev}

@app.post("/api/characters/delete")
def delete_character(req: DeleteCharRequest):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, name FROM characters WHERE telegram_id = ? AND slot_index = ? AND is_deleted = 0", (req.telegram_id, req.slot_index))
    row = c.fetchone()
    if not row or row[1].strip() != req.confirm_name.strip():
        conn.close()
        raise HTTPException(400, "Tên xác nhận không trùng khớp!")
    c.execute("UPDATE characters SET is_deleted = 1 WHERE id = ?", (row[0],))
    conn.commit()
    conn.close()
    return {"status": "success"}

@app.get("/api/pvp/lobby")
def get_pvp_lobby(exclude_id: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, name, realm, is_dev, stats_json FROM characters WHERE id != ? AND is_deleted = 0 ORDER BY id DESC LIMIT 20", (exclude_id,))
    rows = c.fetchall()
    conn.close()
    return {"opponents": [{
        "id": r[0], "name": r[1], "realm": r[2], "is_dev": bool(r[3]),
        "hp": json.loads(r[4]).get("hp", 100), "speed": json.loads(r[4]).get("toc_do", 100)
    } for r in rows]}

@app.post("/api/pvp/challenge")
def challenge_opponent(req: ChallengeRequest):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, name, stats_json, roots_json FROM characters WHERE id = ?", (req.challenger_char_id,))
    c1 = c.fetchone()
    c.execute("SELECT id, name, stats_json, roots_json FROM characters WHERE id = ?", (req.target_char_id,))
    c2 = c.fetchone()
    conn.close()

    if not c1 or not c2:
        raise HTTPException(404, "Nhân vật không tồn tại!")

    return simulate_pvp_battle(
        Fighter(c1[0], c1[1], json.loads(c1[2]), json.loads(c1[3])),
        Fighter(c2[0], c2[1], json.loads(c2[2]), json.loads(c2[3]))
    )

app.mount("/", StaticFiles(directory="static", html=True), name="static")
