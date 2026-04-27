"""
洛克王国世界 知识图谱可视化服务器
从 LanceDB + JSON 数据源构建知识图谱，提供 Web 可视化与实时同步
优化：聚类视图 + 按需展开 + 精简载荷
"""

import json
import os
import time
import hashlib
import threading
from pathlib import Path
from typing import Dict, List, Any

from flask import Flask, jsonify, request, send_from_directory
from flask_socketio import SocketIO, emit

BASE_DIR = Path(__file__).parent
CONFIG_DIR = BASE_DIR / "config"
RAG_DB_DIR = BASE_DIR / "scripts" / "rag_lancedb"

app = Flask(__name__, static_folder=str(BASE_DIR / "web" / "static"), template_folder=str(BASE_DIR / "web" / "templates"))
app.config["SECRET_KEY"] = "roco_kg_2026"
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

TYPE_EN_TO_CN = {
    "normal": "普通", "fire": "火", "water": "水", "grass": "草", "electric": "电",
    "ice": "冰", "fighting": "武", "poison": "毒", "ground": "地", "flying": "翼",
    "psychic": "超能", "bug": "虫", "rock": "岩", "ghost": "幽", "dragon": "龙",
    "dark": "恶", "evil": "恶", "steel": "机械", "fairy": "萌", "light": "光",
    "illusion": "幻", "god": "神系", "mechanical": "机械"
}

TYPE_COLORS = {
    "普通": "#A8A878", "火": "#F08030", "水": "#6890F0", "草": "#78C850", "电": "#F8D030",
    "冰": "#98D8D8", "武": "#C03028", "毒": "#A040A0", "地": "#E0C068", "翼": "#A890F0",
    "超能": "#F85888", "虫": "#A8B820", "岩": "#B8A038", "幽": "#705898", "龙": "#7038F8",
    "恶": "#705848", "机械": "#B8B8D0", "萌": "#EE99AC", "光": "#FFD700", "幻": "#DA70D6",
    "神系": "#FF6347"
}

CATEGORY_COLORS = {
    "属性优势": "#4CAF50", "属性劣势": "#F44336", "换宠策略": "#2196F3",
    "HP策略": "#FF9800", "血量策略": "#FF9800", "能量策略": "#9C27B0",
    "宠物策略": "#00BCD4", "技能策略": "#FF5722", "状态策略": "#795548",
    "反制策略": "#607D8B", "高阶策略": "#E91E63", "进阶策略": "#E91E63",
    "印记策略": "#AB47BC", "阵容协同": "#26A69A", "控制策略": "#5C6BC0"
}

_data_cache = {"hash": None, "timestamp": 0, "graph": None, "overview": None, "detail_index": None}


def load_json_data():
    pets_data = {}
    pet_path = CONFIG_DIR / "pet_database_full.json"
    if pet_path.exists():
        with open(pet_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        for pet in raw.get("pets", []):
            pet["type_cn"] = TYPE_EN_TO_CN.get(pet.get("type", ""), pet.get("type", ""))
            if pet.get("secondary_type"):
                pet["secondary_type_cn"] = TYPE_EN_TO_CN.get(pet["secondary_type"], pet["secondary_type"])
            pets_data[pet["name"]] = pet

    skills_data = {}
    skill_path = CONFIG_DIR / "skill_database.json"
    if skill_path.exists():
        with open(skill_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        for skill in raw.get("skills", []):
            skills_data[skill["name"]] = skill

    strategies_data = []
    strat_path = CONFIG_DIR / "combat_strategy_rag.jsonl"
    if strat_path.exists():
        with open(strat_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    strategies_data.append(json.loads(line))

    return pets_data, skills_data, strategies_data


def load_lancedb_data():
    strategies_from_db = []
    try:
        import lancedb
        if RAG_DB_DIR.exists():
            db = lancedb.connect(str(RAG_DB_DIR))
            if "battle_intel" in list(db.table_names()):
                table = db.open_table("battle_intel")
                df = table.to_pandas()
                for _, row in df.iterrows():
                    strategies_from_db.append({
                        "id": row.get("id", ""),
                        "category": row.get("category", ""),
                        "scenario": row.get("scenario", ""),
                        "action": row.get("action", ""),
                        "rationale": row.get("rationale", ""),
                        "source": row.get("source", ""),
                    })
    except Exception as e:
        print(f"[LanceDB] 加载失败: {e}")
    return strategies_from_db


def build_type_chart():
    type_chart = {
        "water": ["fire", "ground", "mechanical"],
        "fire": ["grass", "ice", "bug", "mechanical"],
        "grass": ["water", "ground", "rock"],
        "electric": ["water", "flying"],
        "ice": ["dragon", "flying", "grass", "ground"],
        "fighting": ["evil", "ghost", "ice", "mechanical", "normal"],
        "poison": ["grass", "mechanical"],
        "ground": ["fire", "electric", "poison", "mechanical", "rock"],
        "flying": ["bug", "grass", "fighting"],
        "psychic": ["fighting", "poison"],
        "bug": ["grass", "evil", "psychic"],
        "rock": ["fire", "flying", "ice", "bug"],
        "ghost": ["psychic", "ghost"],
        "dragon": ["dragon"],
        "dark": ["ghost", "light"],
        "steel": ["ice", "rock", "fairy"],
        "fairy": ["dragon", "dark", "fighting"],
        "light": ["evil", "ghost"],
        "illusion": ["ghost", "psychic"],
        "normal": [],
    }
    resist_chart = {
        "fire": ["fire", "grass", "ice", "bug", "mechanical", "fairy"],
        "water": ["fire", "water", "ice", "mechanical"],
        "grass": ["water", "grass", "ground", "electric"],
        "electric": ["electric", "flying", "mechanical"],
        "ice": ["ice"],
        "fighting": ["dark", "bug", "rock"],
        "poison": ["grass", "fighting", "poison", "bug", "fairy"],
        "ground": ["poison", "rock", "electric"],
        "flying": ["grass", "fighting", "bug"],
        "psychic": ["fighting", "psychic"],
        "bug": ["grass", "fighting", "ground"],
        "rock": ["fire", "flying", "poison", "normal"],
        "ghost": ["poison", "bug"],
        "dragon": ["fire", "water", "grass", "electric"],
        "dark": ["psychic", "ghost"],
        "steel": ["normal", "grass", "ice", "flying", "psychic", "bug", "rock", "dragon", "mechanical", "fairy"],
        "fairy": ["fighting", "bug", "dark"],
        "light": ["light"],
        "illusion": ["fighting", "poison"],
        "normal": [],
    }
    return type_chart, resist_chart


def build_overview_graph():
    """构建轻量级概览图：仅属性节点 + 策略类别 + 属性间克制/抵抗边"""
    nodes = []
    edges = []
    node_ids = set()
    edge_set = set()

    def add_node(nid, label, ntype, group, extra=None):
        if nid not in node_ids:
            node_ids.add(nid)
            n = {"id": nid, "label": label, "type": ntype, "group": group}
            if extra:
                n.update(extra)
            nodes.append(n)

    def add_edge(src, tgt, etype, label="", extra=None):
        key = f"{src}|{tgt}|{etype}"
        if key in edge_set:
            return
        edge_set.add(key)
        e = {"source": src, "target": tgt, "type": etype, "label": label}
        if extra:
            e.update(extra)
        edges.append(e)

    seen_cn = set()
    for en, cn in TYPE_EN_TO_CN.items():
        if cn not in seen_cn:
            seen_cn.add(cn)
            add_node(f"type_{cn}", cn, "属性", "属性", {"color": TYPE_COLORS.get(cn, "#999")})

    type_chart, resist_chart = build_type_chart()
    for atk, defs in type_chart.items():
        atk_cn = TYPE_EN_TO_CN.get(atk)
        if not atk_cn:
            continue
        for d in defs:
            d_cn = TYPE_EN_TO_CN.get(d)
            if d_cn:
                add_edge(f"type_{atk_cn}", f"type_{d_cn}", "克制", "2x", {"color": "#ef4444"})

    for defender, resist_types in resist_chart.items():
        def_cn = TYPE_EN_TO_CN.get(defender)
        if not def_cn:
            continue
        for r in resist_types:
            r_cn = TYPE_EN_TO_CN.get(r)
            if r_cn:
                add_edge(f"type_{r_cn}", f"type_{def_cn}", "抵抗", "0.5x", {"color": "#3b82f6", "style": "dashed"})

    pets_data, skills_data, strategies_data = load_json_data()
    lancedb_strategies = load_lancedb_data()
    all_strategies = strategies_data if strategies_data else lancedb_strategies

    seen_categories = set()
    for strat in all_strategies:
        cat = strat.get("category", "未知")
        if cat not in seen_categories:
            seen_categories.add(cat)
            add_node(f"cat_{cat}", cat, "策略类别", cat, {"color": CATEGORY_COLORS.get(cat, "#999")})

    type_pet_counts = {}
    for name, pet in pets_data.items():
        tc = TYPE_EN_TO_CN.get(pet.get("type", ""), pet.get("type", ""))
        type_pet_counts[tc] = type_pet_counts.get(tc, 0) + 1

    type_skill_counts = {}
    for name, skill in skills_data.items():
        tc = TYPE_EN_TO_CN.get(skill.get("type", ""), skill.get("type", ""))
        type_skill_counts[tc] = type_skill_counts.get(tc, 0) + 1

    cat_strat_counts = {}
    for strat in all_strategies:
        cat = strat.get("category", "未知")
        cat_strat_counts[cat] = cat_strat_counts.get(cat, 0) + 1

    stats = {
        "total_pets": len(pets_data),
        "total_skills": len(skills_data),
        "total_strategies": len(all_strategies),
        "total_nodes": len(nodes),
        "total_edges": len(edges),
        "type_count": len(seen_cn),
        "categories": list(seen_categories),
        "type_pet_counts": type_pet_counts,
        "type_skill_counts": type_skill_counts,
        "cat_strat_counts": cat_strat_counts
    }

    return {"nodes": nodes, "edges": edges, "stats": stats}


def build_detail_index():
    """构建按属性/类别分组的详细数据索引，用于按需加载"""
    pets_data, skills_data, strategies_data = load_json_data()
    lancedb_strategies = load_lancedb_data()
    all_strategies = strategies_data if strategies_data else lancedb_strategies

    index = {
        "pets_by_type": {},
        "skills_by_type": {},
        "strategies_by_cat": {},
        "top_pets": []
    }

    sorted_pets = sorted(
        pets_data.items(),
        key=lambda x: sum(v for v in x[1].get("base_stats", {}).values() if v),
        reverse=True
    )

    for name, pet in sorted_pets[:50]:
        tc = TYPE_EN_TO_CN.get(pet.get("type", ""), pet.get("type", ""))
        stats = pet.get("base_stats", {})
        total = sum(v for v in stats.values() if v)
        index["top_pets"].append({
            "name": name, "type_cn": tc, "total_stats": total,
            "color": TYPE_COLORS.get(tc, "#999")
        })

    for name, pet in pets_data.items():
        tc = TYPE_EN_TO_CN.get(pet.get("type", ""), pet.get("type", ""))
        if tc not in index["pets_by_type"]:
            index["pets_by_type"][tc] = []
        stats = pet.get("base_stats", {})
        total = sum(v for v in stats.values() if v)
        index["pets_by_type"][tc].append({
            "id": f"pet_{name}", "label": name, "type": "宠物", "group": tc,
            "color": TYPE_COLORS.get(tc, "#999"),
            "size": min(25 + total // 60, 45),
            "stats": stats, "type_cn": tc,
            "weaknesses": pet.get("weaknesses", {}),
            "secondary_type": pet.get("secondary_type", "")
        })

    for name, skill in skills_data.items():
        tc = TYPE_EN_TO_CN.get(skill.get("type", ""), skill.get("type", ""))
        if tc not in index["skills_by_type"]:
            index["skills_by_type"][tc] = []
        power = skill.get("power", 0)
        index["skills_by_type"][tc].append({
            "id": f"skill_{name}", "label": name, "type": "技能", "group": tc,
            "color": TYPE_COLORS.get(tc, "#999"),
            "size": min(12 + (power or 0) // 8, 35),
            "power": power, "type_cn": tc,
            "effect": skill.get("effect", ""),
            "energy": skill.get("energy", 0),
            "attack_type_cn": skill.get("attack_type_cn", "")
        })

    for strat in all_strategies:
        cat = strat.get("category", "未知")
        if cat not in index["strategies_by_cat"]:
            index["strategies_by_cat"][cat] = []
        strat_id = strat.get("id", f"strat_{hash(strat.get('scenario', ''))}")
        scenario = strat.get("scenario", "")
        label = scenario[:18] + "..." if len(scenario) > 18 else scenario
        index["strategies_by_cat"][cat].append({
            "id": f"strat_{strat_id}", "label": label, "type": "策略", "group": cat,
            "color": CATEGORY_COLORS.get(cat, "#999"),
            "size": 18,
            "full_scenario": scenario,
            "action": strat.get("action", ""),
            "rationale": strat.get("rationale", ""),
            "source": strat.get("source", "")
        })

    return index


def build_expanded_data(node_id):
    """按需展开某个聚类节点，返回该聚类的子节点和边"""
    pets_data, skills_data, strategies_data = load_json_data()
    lancedb_strategies = load_lancedb_data()
    all_strategies = strategies_data if strategies_data else lancedb_strategies

    nodes = []
    edges = []
    edge_set = set()

    def add_edge(src, tgt, etype, label="", extra=None):
        key = f"{src}|{tgt}|{etype}"
        if key in edge_set:
            return
        edge_set.add(key)
        e = {"source": src, "target": tgt, "type": etype, "label": label}
        if extra:
            e.update(extra)
        edges.append(e)

    if node_id.startswith("type_"):
        type_cn = node_id[5:]
        type_en = None
        for en, cn in TYPE_EN_TO_CN.items():
            if cn == type_cn:
                type_en = en
                break

        for name, pet in pets_data.items():
            pet_type_cn = TYPE_EN_TO_CN.get(pet.get("type", ""), pet.get("type", ""))
            if pet_type_cn != type_cn:
                continue
            stats = pet.get("base_stats", {})
            total = sum(v for v in stats.values() if v)
            nodes.append({
                "id": f"pet_{name}", "label": name, "type": "宠物", "group": type_cn,
                "color": TYPE_COLORS.get(type_cn, "#999"),
                "size": min(25 + total // 60, 45),
                "stats": stats, "type_cn": type_cn,
                "weaknesses": pet.get("weaknesses", {})
            })
            add_edge(f"pet_{name}", node_id, "属于", type_cn, {"color": "#475569"})

            sec = pet.get("secondary_type")
            if sec:
                sec_cn = TYPE_EN_TO_CN.get(sec, sec)
                if sec_cn:
                    add_edge(f"pet_{name}", f"type_{sec_cn}", "副属性", sec_cn, {"color": "#64748b", "style": "dashed"})

        for name, skill in skills_data.items():
            skill_type_cn = TYPE_EN_TO_CN.get(skill.get("type", ""), skill.get("type", ""))
            if skill_type_cn != type_cn:
                continue
            power = skill.get("power", 0)
            nodes.append({
                "id": f"skill_{name}", "label": name, "type": "技能", "group": type_cn,
                "color": TYPE_COLORS.get(type_cn, "#999"),
                "size": min(12 + (power or 0) // 8, 35),
                "power": power, "type_cn": type_cn,
                "effect": skill.get("effect", ""),
                "energy": skill.get("energy", 0),
                "attack_type_cn": skill.get("attack_type_cn", "")
            })
            add_edge(f"skill_{name}", node_id, "属于", type_cn, {"color": "#475569"})

    elif node_id.startswith("cat_"):
        cat = node_id[4:]
        for strat in all_strategies:
            if strat.get("category", "未知") != cat:
                continue
            strat_id = strat.get("id", f"strat_{hash(strat.get('scenario', ''))}")
            scenario = strat.get("scenario", "")
            label = scenario[:18] + "..." if len(scenario) > 18 else scenario
            nodes.append({
                "id": f"strat_{strat_id}", "label": label, "type": "策略", "group": cat,
                "color": CATEGORY_COLORS.get(cat, "#999"),
                "size": 18,
                "full_scenario": scenario,
                "action": strat.get("action", ""),
                "rationale": strat.get("rationale", ""),
                "source": strat.get("source", "")
            })
            add_edge(f"strat_{strat_id}", node_id, "属于类别", cat, {"color": CATEGORY_COLORS.get(cat, "#999")})

            for en, cn in TYPE_EN_TO_CN.items():
                if cn + "系" in scenario:
                    add_edge(f"strat_{strat_id}", f"type_{cn}", "涉及", cn, {"color": "#64748b", "style": "dotted"})

    return {"nodes": nodes, "edges": edges, "parent_id": node_id}


def build_full_graph():
    """构建完整图谱（用于搜索等场景）"""
    pets_data, skills_data, strategies_data = load_json_data()
    lancedb_strategies = load_lancedb_data()
    all_strategies = strategies_data if strategies_data else lancedb_strategies

    nodes = []
    edges = []
    node_ids = set()
    edge_set = set()

    def add_node(nid, label, ntype, group, extra=None):
        if nid not in node_ids:
            node_ids.add(nid)
            n = {"id": nid, "label": label, "type": ntype, "group": group}
            if extra:
                n.update(extra)
            nodes.append(n)

    def add_edge(src, tgt, etype, label="", extra=None):
        key = f"{src}|{tgt}|{etype}"
        if key in edge_set:
            return
        edge_set.add(key)
        e = {"source": src, "target": tgt, "type": etype, "label": label}
        if extra:
            e.update(extra)
        edges.append(e)

    seen_cn = set()
    for en, cn in TYPE_EN_TO_CN.items():
        if cn not in seen_cn:
            seen_cn.add(cn)
            add_node(f"type_{cn}", cn, "属性", "属性", {"color": TYPE_COLORS.get(cn, "#999")})

    type_chart, resist_chart = build_type_chart()
    for atk, defs in type_chart.items():
        atk_cn = TYPE_EN_TO_CN.get(atk)
        if not atk_cn:
            continue
        for d in defs:
            d_cn = TYPE_EN_TO_CN.get(d)
            if d_cn:
                add_edge(f"type_{atk_cn}", f"type_{d_cn}", "克制", "2x", {"color": "#ef4444"})

    for defender, resist_types in resist_chart.items():
        def_cn = TYPE_EN_TO_CN.get(defender)
        if not def_cn:
            continue
        for r in resist_types:
            r_cn = TYPE_EN_TO_CN.get(r)
            if r_cn:
                add_edge(f"type_{r_cn}", f"type_{def_cn}", "抵抗", "0.5x", {"color": "#3b82f6", "style": "dashed"})

    sorted_pets = sorted(
        pets_data.items(),
        key=lambda x: sum(v for v in x[1].get("base_stats", {}).values() if v),
        reverse=True
    )
    top_pet_names = set(name for name, _ in sorted_pets[:100])

    for name, pet in pets_data.items():
        pet_type = pet.get("type", "")
        type_cn = TYPE_EN_TO_CN.get(pet_type, pet_type)
        stats = pet.get("base_stats", {})
        total_stats = sum(v for v in stats.values() if v)

        add_node(f"pet_{name}", name, "宠物", type_cn, {
            "color": TYPE_COLORS.get(type_cn, "#999"),
            "size": min(25 + total_stats // 60, 45),
            "stats": stats, "type_cn": type_cn,
            "weaknesses": pet.get("weaknesses", {})
        })

        if type_cn in seen_cn:
            add_edge(f"pet_{name}", f"type_{type_cn}", "属于", type_cn, {"color": "#475569"})

        sec = pet.get("secondary_type")
        if sec:
            sec_cn = TYPE_EN_TO_CN.get(sec, sec)
            if sec_cn in seen_cn:
                add_edge(f"pet_{name}", f"type_{sec_cn}", "副属性", sec_cn, {"color": "#64748b", "style": "dashed"})

        if name in top_pet_names:
            weaknesses = pet.get("weaknesses", {})
            for weak_type in weaknesses.get("weak_to", []):
                weak_cn = TYPE_EN_TO_CN.get(weak_type, weak_type)
                if weak_cn in seen_cn:
                    add_edge(f"type_{weak_cn}", f"pet_{name}", "弱点", "被克制", {"color": "#f87171", "style": "dotted"})

    for name, skill in skills_data.items():
        skill_type = skill.get("type", "")
        type_cn = TYPE_EN_TO_CN.get(skill_type, skill.get("type_cn", skill_type))
        power = skill.get("power", 0)

        add_node(f"skill_{name}", name, "技能", type_cn, {
            "color": TYPE_COLORS.get(type_cn, "#999"),
            "size": min(12 + (power or 0) // 8, 35),
            "power": power, "type_cn": type_cn,
            "effect": skill.get("effect", ""),
            "energy": skill.get("energy", 0),
            "attack_type_cn": skill.get("attack_type_cn", "")
        })

        if type_cn in seen_cn:
            add_edge(f"skill_{name}", f"type_{type_cn}", "属于", type_cn, {"color": "#475569"})

    seen_categories = set()
    for strat in all_strategies:
        cat = strat.get("category", "未知")
        if cat not in seen_categories:
            seen_categories.add(cat)
            add_node(f"cat_{cat}", cat, "策略类别", cat, {"color": CATEGORY_COLORS.get(cat, "#999")})

        strat_id = strat.get("id", f"strat_{hash(strat.get('scenario', ''))}")
        scenario = strat.get("scenario", "")
        label = scenario[:18] + "..." if len(scenario) > 18 else scenario

        add_node(f"strat_{strat_id}", label, "策略", cat, {
            "color": CATEGORY_COLORS.get(cat, "#999"),
            "size": 18,
            "full_scenario": scenario,
            "action": strat.get("action", ""),
            "rationale": strat.get("rationale", ""),
            "source": strat.get("source", "")
        })

        add_edge(f"strat_{strat_id}", f"cat_{cat}", "属于类别", cat, {"color": CATEGORY_COLORS.get(cat, "#999")})

        for en, cn in TYPE_EN_TO_CN.items():
            if cn + "系" in scenario and cn in seen_cn:
                add_edge(f"strat_{strat_id}", f"type_{cn}", "涉及", cn, {"color": "#64748b", "style": "dotted"})

    stats_summary = {
        "total_pets": len(pets_data),
        "total_skills": len(skills_data),
        "total_strategies": len(all_strategies),
        "total_nodes": len(nodes),
        "total_edges": len(edges),
        "type_count": len(seen_cn),
        "categories": list(seen_categories)
    }

    return {"nodes": nodes, "edges": edges, "stats": stats_summary}


def get_data_hash():
    h = hashlib.md5()
    for fname in ["pet_database_full.json", "skill_database.json", "combat_strategy_rag.jsonl"]:
        fp = CONFIG_DIR / fname
        if fp.exists():
            h.update(str(fp.stat().st_mtime).encode())
    return h.hexdigest()


def get_cached(func_key, builder):
    current_hash = get_data_hash()
    cached = _data_cache.get(func_key)
    if cached and _data_cache.get("hash") == current_hash:
        return cached
    result = builder()
    _data_cache[func_key] = result
    _data_cache["hash"] = current_hash
    _data_cache["timestamp"] = time.time()
    return result


# ===== API 路由 =====

@app.route("/")
def index():
    return send_from_directory(str(BASE_DIR / "web" / "templates"), "index.html")


@app.route("/api/overview")
def api_overview():
    return jsonify(get_cached("overview", build_overview_graph))


@app.route("/api/graph")
def api_graph():
    return jsonify(get_cached("graph", build_full_graph))


@app.route("/api/expand/<node_id>")
def api_expand(node_id):
    return jsonify(build_expanded_data(node_id))


@app.route("/api/detail_index")
def api_detail_index():
    return jsonify(get_cached("detail_index", build_detail_index))


@app.route("/api/stats")
def api_stats():
    data = get_cached("overview", build_overview_graph)
    return jsonify(data["stats"])


@app.route("/api/pets")
def api_pets():
    pets_data, _, _ = load_json_data()
    pet_type = request.args.get("type")
    search = request.args.get("search", "").lower()
    result = []
    for name, pet in pets_data.items():
        if pet_type and pet.get("type") != pet_type:
            continue
        if search and search not in name.lower():
            continue
        result.append(pet)
    return jsonify({"pets": result, "total": len(result)})


@app.route("/api/skills")
def api_skills():
    _, skills_data, _ = load_json_data()
    skill_type = request.args.get("type")
    search = request.args.get("search", "").lower()
    result = []
    for name, skill in skills_data.items():
        if skill_type and skill.get("type") != skill_type:
            continue
        if search and search not in name.lower():
            continue
        result.append(skill)
    return jsonify({"skills": result, "total": len(result)})


@app.route("/api/strategies")
def api_strategies():
    _, _, strategies_data = load_json_data()
    category = request.args.get("category")
    search = request.args.get("search", "").lower()
    result = []
    for strat in strategies_data:
        if category and strat.get("category") != category:
            continue
        if search and search not in strat.get("scenario", "").lower() and search not in strat.get("action", "").lower():
            continue
        result.append(strat)
    return jsonify({"strategies": result, "total": len(result)})


@app.route("/api/type_chart")
def api_type_chart():
    return jsonify(TYPE_EN_TO_CN)


@app.route("/api/search")
def api_search():
    q = request.args.get("q", "").lower().strip()
    if not q:
        return jsonify({"nodes": [], "edges": []})

    graph = get_cached("graph", build_full_graph)
    matched_node_ids = set()
    for node in graph["nodes"]:
        label = (node.get("label", "") + " " + node.get("full_scenario", "") + " " + node.get("action", "") + " " + node.get("effect", "")).lower()
        if q in label:
            matched_node_ids.add(node["id"])

    connected = set(matched_node_ids)
    for edge in graph["edges"]:
        if edge["source"] in matched_node_ids or edge["target"] in matched_node_ids:
            connected.add(edge["source"])
            connected.add(edge["target"])

    result_nodes = [n for n in graph["nodes"] if n["id"] in connected]
    result_edges = [e for e in graph["edges"] if e["source"] in connected and e["target"] in connected]

    return jsonify({"nodes": result_nodes, "edges": result_edges, "matched": list(matched_node_ids)})


@app.route("/api/refresh", methods=["POST"])
def api_refresh():
    _data_cache["graph"] = None
    _data_cache["overview"] = None
    _data_cache["detail_index"] = None
    _data_cache["hash"] = None
    graph = get_cached("overview", build_overview_graph)
    socketio.emit("graph_updated", {"stats": graph["stats"]})
    return jsonify({"status": "ok", "stats": graph["stats"]})


# ===== WebSocket =====

@socketio.on("connect")
def on_connect():
    print(f"[WS] 客户端连接: {request.sid}")
    emit("connected", {"status": "ok"})


@socketio.on("disconnect")
def on_disconnect():
    print(f"[WS] 客户端断开: {request.sid}")


@socketio.on("request_graph")
def on_request_graph():
    graph = get_cached("overview", build_overview_graph)
    emit("graph_data", graph)


@socketio.on("expand_node")
def on_expand_node(data):
    node_id = data.get("node_id", "")
    result = build_expanded_data(node_id)
    emit("expanded_data", result)


@socketio.on("search")
def on_search(query):
    q = query.lower()
    graph = get_cached("graph", build_full_graph)
    matched_nodes = []
    for node in graph["nodes"]:
        label = node.get("label", "").lower()
        extra = (node.get("full_scenario", "") + " " + node.get("action", "") + " " + node.get("effect", "")).lower()
        if q in label or q in extra:
            matched_nodes.append(node["id"])
    emit("search_result", {"nodes": matched_nodes, "query": query})


# ===== 文件监控 =====

def file_watcher():
    last_hash = get_data_hash()
    while True:
        time.sleep(5)
        current_hash = get_data_hash()
        if current_hash != last_hash:
            last_hash = current_hash
            _data_cache["graph"] = None
            _data_cache["overview"] = None
            _data_cache["detail_index"] = None
            _data_cache["hash"] = None
            graph = get_cached("overview", build_overview_graph)
            socketio.emit("graph_updated", {"stats": graph["stats"], "hash": current_hash})
            print(f"[文件监控] 检测到数据变更，已推送更新")


def start_server(host="0.0.0.0", port=5000, debug=False):
    watcher = threading.Thread(target=file_watcher, daemon=True)
    watcher.start()
    print(f"\n{'='*60}")
    print(f"  洛克王国世界 知识图谱可视化服务器")
    print(f"  地址: http://{host}:{port}")
    print(f"  概览: http://{host}:{port}/api/overview")
    print(f"  展开: http://{host}:{port}/api/expand/<node_id>")
    print(f"  搜索: http://{host}:{port}/api/search?q=关键词")
    print(f"  实时同步: WebSocket (每5秒检测文件变更)")
    print(f"{'='*60}\n")
    socketio.run(app, host=host, port=port, debug=debug, allow_unsafe_werkzeug=True)


if __name__ == "__main__":
    start_server()
