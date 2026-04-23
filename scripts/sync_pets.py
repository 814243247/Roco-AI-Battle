import requests
import sqlite3
import json
import os
import re
from pathlib import Path

# Data Sources
DB_URL = "https://github.com/ColinHong10/NRC_AI/raw/refs/heads/main/data/nrc.db"
EVO_CSV_URL = "https://github.com/ColinHong10/NRC_AI/raw/refs/heads/main/data/spirit_evolution.csv"

# Configuration
BASE_DIR = Path(r"D:\Project\AutoPlayGame\MFAAvalonia-v2.11.8-win-x64")
OUTPUT_FILE = BASE_DIR / "config" / "pet_database_full.json"
TEMP_DB = BASE_DIR / "scripts" / "temp_nrc.db"

# Type Map (CN -> EN)
TYPE_MAP = {
    "普通": "normal",
    "火": "fire",
    "水": "water",
    "草": "grass",
    "冰": "ice",
    "电": "electric",
    "毒": "poison",
    "土": "ground",
    "地": "ground",
    "岩石": "rock",
    "石": "rock",
    "武": "fighting",
    "虫": "bug",
    "翼": "flying",
    "飞行": "flying",
    "萌": "psychic",
    "幽": "ghost",
    "幽灵": "ghost",
    "恶": "evil",
    "光": "light",
    "机械": "mechanical",
    "龙": "dragon",
    "幻": "illusion",
    "神": "god"
}

# Type Advantage Table (Attacker -> Defender)
# 1: Normal, 2: Super Effective, 0.5: Not Very Effective, 0: Immune
ADVANTAGE_CHART = {
    "fire": {"grass": 2, "ice": 2, "bug": 2, "mechanical": 2, "fire": 0.5, "water": 0.5, "rock": 0.5, "ground": 0.5, "dragon": 0.5},
    "water": {"fire": 2, "ground": 2, "rock": 2, "mechanical": 2, "water": 0.5, "grass": 0.5, "dragon": 0.5},
    "grass": {"water": 2, "ground": 2, "rock": 2, "fire": 0.5, "grass": 0.5, "poison": 0.5, "flying": 0.5, "bug": 0.5, "mechanical": 0.5, "dragon": 0.5},
    "electric": {"water": 2, "flying": 2, "electric": 0.5, "grass": 0.5, "dragon": 0.5, "ground": 0},
    "ice": {"grass": 2, "ground": 2, "flying": 2, "dragon": 2, "fire": 0.5, "water": 0.5, "ice": 0.5, "mechanical": 0.5},
    "fighting": {"normal": 2, "ice": 2, "rock": 2, "evil": 2, "mechanical": 2, "fighting": 1, "poison": 0.5, "flying": 0.5, "psychic": 0.5, "bug": 0.5, "fairy": 0.5, "ghost": 0},
    "poison": {"grass": 2, "fairy": 2, "poison": 0.5, "ground": 0.5, "rock": 0.5, "ghost": 0.5, "mechanical": 0},
    "ground": {"fire": 2, "electric": 2, "poison": 2, "rock": 2, "mechanical": 2, "grass": 0.5, "bug": 0.5, "flying": 0},
    "flying": {"grass": 2, "fighting": 2, "bug": 2, "electric": 0.5, "rock": 0.5, "mechanical": 0.5},
    "psychic": {"fighting": 2, "poison": 2, "psychic": 0.5, "mechanical": 0.5, "evil": 0},
    "bug": {"grass": 2, "psychic": 2, "evil": 2, "fire": 0.5, "fighting": 0.5, "poison": 0.5, "flying": 0.5, "ghost": 0.5, "mechanical": 0.5, "fairy": 0.5},
    "rock": {"fire": 2, "ice": 2, "flying": 2, "bug": 2, "fighting": 0.5, "ground": 0.5, "mechanical": 0.5},
    "ghost": {"ghost": 2, "psychic": 2, "light": 2, "evil": 0.5, "normal": 0},
    "dragon": {"dragon": 2, "mechanical": 0.5, "fairy": 0},
    "evil": {"psychic": 2, "ghost": 2, "light": 2, "fighting": 0.5, "evil": 0.5, "fairy": 0.5},
    "mechanical": {"ice": 2, "rock": 2, "fairy": 2, "fire": 0.5, "water": 0.5, "electric": 0.5, "mechanical": 0.5},
    "fairy": {"fighting": 2, "dragon": 2, "evil": 2, "fire": 0.5, "poison": 0.5, "mechanical": 0.5},
    "light": {"ghost": 2, "evil": 2, "dragon": 2, "light": 0.5, "grass": 0.5},
    "normal": {"rock": 0.5, "mechanical": 0.5, "ghost": 0},
    "illusion": {"psychic": 2, "ghost": 2, "illusion": 0.5},
    "god": {"normal": 2, "fire": 2, "water": 2, "grass": 2, "electric": 2, "ice": 2, "fighting": 2, "poison": 2, "ground": 2, "flying": 2, "psychic": 2, "bug": 2, "rock": 2, "ghost": 2, "dragon": 2, "evil": 2, "mechanical": 2, "fairy": 2, "light": 2, "illusion": 2}
 # Simplified: God is effective against everything except God
}

def calculate_weaknesses(type1, type2=None):
    weak_to = []
    double_weak_to = []
    resist = []
    double_resist = []
    immune = []
    
    types_list = list(ADVANTAGE_CHART.keys())
    
    for attacker_type in types_list:
        mult1 = ADVANTAGE_CHART.get(attacker_type, {}).get(type1, 1)
        mult2 = 1
        if type2:
            mult2 = ADVANTAGE_CHART.get(attacker_type, {}).get(type2, 1)
        
        final_mult = mult1 * mult2
        
        if final_mult == 0:
            immune.append(attacker_type)
        elif final_mult >= 4:
            double_weak_to.append(attacker_type)
        elif final_mult >= 2:
            weak_to.append(attacker_type)
        elif final_mult <= 0.25:
            double_resist.append(attacker_type)
        elif final_mult <= 0.5:
            resist.append(attacker_type)
            
    return {
        "weak_to": sorted(weak_to),
        "double_weak_to": sorted(double_weak_to),
        "resist": sorted(resist),
        "double_resist": sorted(double_resist),
        "immune": sorted(immune)
    }

def download_file(url, target):
    print(f"Downloading {url}...")
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        with open(target, 'wb') as f:
            f.write(r.content)
    except Exception as e:
        print(f"Download failed: {e}")
        raise

def main():
    if not os.path.exists(BASE_DIR / "scripts"):
        os.makedirs(BASE_DIR / "scripts")
        
    download_file(DB_URL, TEMP_DB)
    
    conn = sqlite3.connect(TEMP_DB)
    cursor = conn.cursor()
    
    # Check tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [row[0] for row in cursor.fetchall()]
    print(f"Tables found: {tables}")
    
    # We expect 'spirit' or 'pokemon' table
    # Based on NRC_AI repo exploration, it might be 'spirit'
    table_name = "spirit" if "spirit" in tables else "pokemon"
    
    cursor.execute(f"SELECT * FROM {table_name}")
    rows = cursor.fetchall()
    colnames = [description[0] for description in cursor.description]
    print(f"Columns in {table_name}: {colnames}")
    
    # Map column indexes based on observed schema: 
    # ['id', 'name', 'element', 'evo_stage', 'ability', 'base_hp', 'base_atk', 'base_spatk', 'base_def', 'base_spdef', 'base_speed', 'base_total', ...]
    try:
        idx_name = colnames.index("name")
        idx_type = colnames.index("element")
        # Base stats
        idx_hp = colnames.index("base_hp")
        idx_atk = colnames.index("base_atk")
        idx_def = colnames.index("base_def")
        idx_spatk = colnames.index("base_spatk")
        idx_spdef = colnames.index("base_spdef")
        idx_spd = colnames.index("base_speed")
    except ValueError as e:
        print(f"Error finding columns: {e}. Available columns: {colnames}")
        return

    pets = []
    unique_names = set()
    
    for row in rows:
        name = str(row[idx_name]).strip()
        
        # Skip forms users don't want (optional filter based on regex)
        if "首领" in name or "（异色）" in name or "（闪光）" in name:
            continue
            
        if name in unique_names:
            continue
        unique_names.add(name)
        
        raw_types = str(row[idx_type]).replace("，", ",").split(",")
        types = [TYPE_MAP.get(t.strip(), t.strip()) for t in raw_types if t.strip()]
        
        type1 = types[0] if len(types) > 0 else "normal"
        type2 = types[1] if len(types) > 1 else None
        
        stats = {
            "hp": float(row[idx_hp]),
            "atk": float(row[idx_atk]),
            "def": float(row[idx_def]),
            "spatk": float(row[idx_spatk]),
            "spdef": float(row[idx_spdef]),
            "spd": float(row[idx_spd])
        }
        
        pet = {
            "id": len(pets) + 1,
            "name": name,
            "type": type1,
            "secondary_type": type2,
            "base_stats": stats,
            "weaknesses": calculate_weaknesses(type1, type2)
        }
        pets.append(pet)
        
    result = {
        "version": "2026-04-21 Synchronized",
        "source": "NRC_AI SQLite Database",
        "total_count": len(pets),
        "pets": pets
    }
    
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        
    conn.close()
    os.remove(TEMP_DB)
    print(f"Successfully synchronized {len(pets)} pets to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
