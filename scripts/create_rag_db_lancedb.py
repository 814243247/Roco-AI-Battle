"""
洛克王国世界 RAG 数据库创建工具（Ollama + LanceDB 版）
使用本地 Ollama (nomic-embed-text) 模型生成高质量语义向量
"""

import json
import requests
import time
from pathlib import Path
from typing import List, Dict, Any

try:
    import lancedb
    import numpy as np
    LANCEDB_AVAILABLE = True
except ImportError:
    LANCEDB_AVAILABLE = False
    print("[ERROR] 未安装 lancedb 或 numpy")

EMBED_MODEL = "nomic-embed-text:latest"

def get_ollama_embedding(text: str) -> List[float]:
    """通过 Ollama 本地 API 获取向量"""
    try:
        url = "http://127.0.0.1:11434/api/embeddings"
        payload = {"model": EMBED_MODEL, "prompt": text}
        r = requests.post(url, json=payload, timeout=15)
        if r.status_code == 200:
            return r.json().get("embedding", [])
    except Exception as e:
        print(f"  [Error] Ollama 向量化失败: {e}")
    return [0.0] * 768 # 默认维度

def load_pet_database() -> List[Dict[str, Any]]:
    pet_db_path = Path(__file__).parent.parent / "config" / "pet_database_full.json"
    with open(pet_db_path, "r", encoding="utf-8") as f:
        return json.load(f).get("pets", [])

def load_skill_database() -> List[Dict[str, Any]]:
    skill_db_path = Path(__file__).parent.parent / "config" / "skill_database.json"
    with open(skill_db_path, "r", encoding="utf-8") as f:
        return json.load(f).get("skills", [])

def generate_pet_text(pet: Dict[str, Any]) -> str:
    return f"精灵:{pet['name']} | 属性:{pet.get('type_cn', pet.get('type', '未知'))} | 编号:{pet['id']}"

def generate_skill_text(skill: Dict[str, Any]) -> str:
    return f"技能:{skill['name']} | 效果:{skill.get('effect', '无')} | 威力:{skill.get('power', 0)}"

def create_rag_database():
    if not LANCEDB_AVAILABLE: return
    
    print("=" * 60)
    print("Ollama 语义数据库构建工具 (nomic-embed-text)")
    print("=" * 60)
    
    db_path = Path(__file__).parent / "rag_lancedb"
    db = lancedb.connect(str(db_path))
    
    # 1. 精灵入库
    pets = load_pet_database()
    print(f"\n[1/2] 正在生成 {len(pets)} 只精灵的语义向量...")
    pet_records = []
    for i, pet in enumerate(pets):
        doc = generate_pet_text(pet)
        vector = get_ollama_embedding(doc)
        pet_records.append({
            "id": pet["id"], "name": pet["name"], "type": pet.get("type", "unknown"),
            "text": doc, "vector": vector
        })
        if i % 50 == 0: print(f"  已处理 {i}/{len(pets)}...")

    db.create_table("pets", pet_records, mode="overwrite")
    print(f"[OK] 精灵表构建完成")

    # 2. 技能入库
    skills = load_skill_database()
    print(f"\n[2/2] 正在生成 {len(skills)} 个技能的语义向量...")
    skill_records = []
    for i, skill in enumerate(skills):
        doc = generate_skill_text(skill)
        vector = get_ollama_embedding(doc)
        skill_records.append({
            "id": skill["id"], "name": skill["name"], "power": skill.get("power", 0),
            "text": doc, "vector": vector
        })
        if i % 50 == 0: print(f"  已处理 {i}/{len(skills)}...")

    db.create_table("skills", skill_records, mode="overwrite")
    print(f"\n[完成] RAG 数据库已升级为 Ollama 768维语义索引")

if __name__ == "__main__":
    create_rag_database()
