"""
洛克王国世界 战斗策略同步工具 (LanceDB 版)
将 distilled 战术情报同步至向量数据库，供 AI 实时检索
"""

import json
import requests
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

def simple_text_to_vector(text: str) -> List[float]:
    """本地文本向量化 (与 roco_pvp_ai.py 保持一致)"""
    import numpy as np
    vector = np.zeros(768, dtype=np.float32)
    for i, char in enumerate(text):
        vector[i % 768] += ord(char) / 1000.0
    norm = np.linalg.norm(vector)
    if norm > 0:
        vector = vector / norm
    return vector.tolist()

def get_llama_cpp_embedding(text: str) -> List[float]:
    """强制使用本地向量化以加速同步"""
    return simple_text_to_vector(text)

def load_strategy_data() -> List[Dict[str, Any]]:
    strategy_path = Path(__file__).parent.parent / "config" / "combat_strategy_rag.jsonl"
    strategies = []
    if not strategy_path.exists():
        print(f"[Warning] 策略文件不存在: {strategy_path}")
        return []
    
    with open(strategy_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                strategies.append(json.loads(line))
    return strategies

def generate_strategy_text(strat: Dict[str, Any]) -> str:
    """生成用于向量化的描述文本"""
    # 拼接场景和战术，增加搜索相关性
    return f"场景: {strat['scenario']} | 动作: {strat['action']} | 理由: {strat['rationale']}"

def sync_strategies():
    if not LANCEDB_AVAILABLE: return
    
    print("=" * 60)
    print("智能战术 RAG 数据库同步工具")
    print("=" * 60)
    
    db_path = Path(__file__).parent / "rag_lancedb"
    db = lancedb.connect(str(db_path))
    
    strategies = load_strategy_data()
    if not strategies:
        print("[Abort] 没有找到可同步的策略数据")
        return

    print(f"\n正在生成 {len(strategies)} 条战术情报的语义向量...")
    records = []
    for i, strat in enumerate(strategies):
        doc = generate_strategy_text(strat)
        vector = get_llama_cpp_embedding(doc)
        records.append({
            "id": strat["id"],
            "category": strat["category"],
            "scenario": strat["scenario"],
            "action": strat["action"],
            "text": doc,
            "vector": vector,
            "source": strat.get("source", "unknown")
        })
        print(f"  [{i+1}/{len(strategies)}] 处理完成: {strat['id']}")

    # 创建/更新战术表
    db.create_table("battle_intel", records, mode="overwrite")
    print(f"\n[完成] 战术表 'battle_intel' 已更新。共计 {len(strategies)} 条情报。")

if __name__ == "__main__":
    sync_strategies()
