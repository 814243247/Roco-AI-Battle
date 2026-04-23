"""
更新精灵数据库，添加被克制属性信息
"""

import json

# 完整的属性克制表
TYPE_CHART = {
    "grass": {
        "weak_to": ["fire", "ice", "bug", "flying", "poison"],
        "resist": ["water", "electric", "grass", "ground"],
        "immune": []
    },
    "fire": {
        "weak_to": ["water", "ground", "rock"],
        "resist": ["fire", "grass", "ice", "bug", "mechanical"],
        "immune": []
    },
    "water": {
        "weak_to": ["grass", "electric"],
        "resist": ["fire", "water", "ice", "mechanical"],
        "immune": []
    },
    "electric": {
        "weak_to": ["ground"],
        "resist": ["electric", "flying", "mechanical"],
        "immune": []
    },
    "ice": {
        "weak_to": ["fire", "fighting", "rock", "mechanical"],
        "resist": ["ice"],
        "immune": []
    },
    "rock": {
        "weak_to": ["water", "grass", "fighting", "ground", "mechanical"],
        "resist": ["normal", "fire", "poison", "flying"],
        "immune": []
    },
    "ground": {
        "weak_to": ["water", "grass", "ice"],
        "resist": ["poison", "rock"],
        "immune": ["electric"]
    },
    "flying": {
        "weak_to": ["electric", "ice", "rock"],
        "resist": ["grass", "bug", "fighting"],
        "immune": ["ground"]
    },
    "poison": {
        "weak_to": ["ground", "psychic"],
        "resist": ["grass", "fighting", "poison", "bug", "fairy"],
        "immune": []
    },
    "fighting": {
        "weak_to": ["flying", "psychic", "fairy"],
        "resist": ["rock", "bug", "evil"],
        "immune": []
    },
    "psychic": {
        "weak_to": ["bug", "ghost", "evil"],
        "resist": ["fighting", "psychic"],
        "immune": []
    },
    "evil": {
        "weak_to": ["fighting", "bug", "fairy"],
        "resist": ["ghost", "evil"],
        "immune": ["psychic"]
    },
    "ghost": {
        "weak_to": ["ghost", "evil"],
        "resist": ["poison", "bug"],
        "immune": ["normal", "fighting"]
    },
    "dragon": {
        "weak_to": ["dragon", "ice", "fairy"],
        "resist": ["fire", "water", "grass", "electric"],
        "immune": []
    },
    "mechanical": {
        "weak_to": ["fire", "water", "electric", "fighting", "ground"],
        "resist": ["normal", "grass", "ice", "flying", "psychic", "bug", "rock", "dragon", "mechanical", "fairy"],
        "immune": ["poison"]
    },
    "light": {
        "weak_to": ["ground", "ghost", "evil"],
        "resist": ["fire", "grass", "electric", "psychic"],
        "immune": []
    },
    "fairy": {
        "weak_to": ["poison", "mechanical"],
        "resist": ["fighting", "bug", "evil"],
        "immune": ["dragon"]
    },
    "divine_fairy": {
        "weak_to": ["fire", "ice", "bug", "flying", "poison"],
        "resist": ["water", "electric", "grass", "ground"],
        "immune": []
    },
    "divine_fire": {
        "weak_to": ["water", "ground", "rock"],
        "resist": ["fire", "grass", "ice", "bug", "mechanical"],
        "immune": []
    },
    "divine_water": {
        "weak_to": ["grass", "electric"],
        "resist": ["fire", "water", "ice", "mechanical"],
        "immune": []
    },
    "normal": {
        "weak_to": ["fighting"],
        "resist": [],
        "immune": ["ghost"]
    },
    "bug": {
        "weak_to": ["fire", "flying", "rock"],
        "resist": ["grass", "fighting", "ground"],
        "immune": []
    }
}

def calculate_weaknesses(type1, type2=None):
    """计算精灵的被克制属性"""
    if not type1 or type1 == "unknown":
        return {
            "weak_to": [],
            "double_weak_to": [],
            "resist": [],
            "double_resist": [],
            "immune": []
        }
    
    weaknesses = {
        "weak_to": set(),
        "double_weak_to": set(),
        "resist": set(),
        "double_resist": set(),
        "immune": set()
    }
    
    # 获取第一属性的克制关系
    chart1 = TYPE_CHART.get(type1, {})
    weak1 = chart1.get("weak_to", [])
    resist1 = chart1.get("resist", [])
    immune1 = chart1.get("immune", [])
    
    # 如果是单属性
    if not type2 or type2 == type1:
        weaknesses["weak_to"] = set(weak1)
        weaknesses["resist"] = set(resist1)
        weaknesses["immune"] = set(immune1)
    else:
        # 双属性计算
        chart2 = TYPE_CHART.get(type2, {})
        weak2 = chart2.get("weak_to", [])
        resist2 = chart2.get("resist", [])
        immune2 = chart2.get("immune", [])
        
        # 计算克制（4 倍克制）
        for w in weak1:
            if w in weak2:
                weaknesses["double_weak_to"].add(w)
            elif w not in resist2 and w not in immune2:
                weaknesses["weak_to"].add(w)
        
        for w in weak2:
            if w not in weak1 and w not in resist1 and w not in immune1:
                weaknesses["weak_to"].add(w)
        
        # 计算抵抗（4 倍抵抗）
        for r in resist1:
            if r in resist2:
                weaknesses["double_resist"].add(r)
            elif r not in weak2 and r not in immune2:
                weaknesses["resist"].add(r)
        
        for r in resist2:
            if r not in resist1 and r not in weak1 and r not in immune1:
                weaknesses["resist"].add(r)
        
        # 计算免疫
        weaknesses["immune"] = set(immune1) | set(immune2)
        
        # 移除冲突的属性（既有克制又有抵抗的抵消）
        weaknesses["weak_to"] -= weaknesses["resist"]
        weaknesses["weak_to"] -= weaknesses["immune"]
        weaknesses["resist"] -= weaknesses["weak_to"]
        weaknesses["resist"] -= weaknesses["immune"]
        
        # 4 倍克制不受抵抗影响
        weaknesses["double_weak_to"] -= weaknesses["resist"]
        weaknesses["double_weak_to"] -= weaknesses["immune"]
    
    # 转换为列表
    return {
        "weak_to": sorted(list(weaknesses["weak_to"])),
        "double_weak_to": sorted(list(weaknesses["double_weak_to"])),
        "resist": sorted(list(weaknesses["resist"])),
        "double_resist": sorted(list(weaknesses["double_resist"])),
        "immune": sorted(list(weaknesses["immune"]))
    }

def update_database():
    """更新精灵数据库，添加被克制属性"""
    print("=" * 60)
    print("更新精灵数据库 - 添加被克制属性")
    print("=" * 60)
    
    # 读取现有数据库
    with open("config/pet_database_full.json", "r", encoding="utf-8") as f:
        db = json.load(f)
    
    print(f"\n[读取] 数据库版本：{db.get('version', '未知')}")
    print(f"[读取] 精灵总数：{db.get('total_count', 0)}")
    
    # 为每只精灵添加被克制属性
    updated_count = 0
    for pet in db["pets"]:
        type1 = pet.get("type", "unknown")
        type2 = pet.get("secondary_type")
        
        # 计算被克制属性
        weaknesses = calculate_weaknesses(type1, type2)
        
        # 添加到精灵数据中
        pet["weaknesses"] = weaknesses
        updated_count += 1
    
    # 保存更新后的数据库
    with open("config/pet_database_full.json", "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)
    
    print(f"\n[完成] 已更新 {updated_count} 只精灵的被克制属性")
    print(f"[保存] 文件：config/pet_database_full.json")
    
    # 显示示例
    print("\n示例数据（前 5 只精灵）：")
    for pet in db["pets"][:5]:
        type_str = pet["type"]
        if pet.get("secondary_type"):
            type_str += f"/{pet['secondary_type']}"
        
        w = pet.get("weaknesses", {})
        weak_str = ", ".join(w.get("weak_to", [])) if w.get("weak_to") else "无"
        double_weak_str = ", ".join(w.get("double_weak_to", [])) if w.get("double_weak_to") else "无"
        resist_str = ", ".join(w.get("resist", [])) if w.get("resist") else "无"
        immune_str = ", ".join(w.get("immune", [])) if w.get("immune") else "无"
        
        print(f"\n  NO.{pet['id']:03d} {pet['name']:15s} [{type_str}]")
        print(f"    克制：{weak_str}")
        if w.get("double_weak_to"):
            print(f"    4 倍克制：{double_weak_str}")
        print(f"    抵抗：{resist_str}")
        print(f"    免疫：{immune_str}")
    
    print("\n" + "=" * 60)
    print("更新完成！")
    print("=" * 60)

if __name__ == "__main__":
    update_database()
