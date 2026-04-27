"""
洛克王国世界 RAG 数据库测试工具（语义 + 算法纠错版）
"""

import sys
import os
import time
import json
import difflib
from pathlib import Path

try:
    import lancedb
    import pandas as pd
    LANCEDB_AVAILABLE = True
except ImportError:
    LANCEDB_AVAILABLE = False

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from roco_pvp_ai import simple_text_to_vector

# --- 向量化逻辑 ---
def get_llama_cpp_embedding(text: str) -> list:
    try:
        return simple_text_to_vector(text)
    except: pass
    return [0.0] * 768

class HybridSearchTester:
    def __init__(self):
        db_path = Path(__file__).parent / "rag_lancedb"
        self.db = lancedb.connect(str(db_path))
        self.pets_table = self.db.open_table("pets")
        self.skills_table = self.db.open_table("skills")
        
        # 加载模糊缓存
        self.pets_cache = {r['name']: r for r in self.pets_table.to_pandas().to_dict('records')}
        self.skills_cache = {r['name']: r for r in self.skills_table.to_pandas().to_dict('records')}

    def adaptive_search(self, text, cache, table):
        if not text or len(text) < 1:
            return {"name": "None", "source": "Empty", "distance": 1.0}
            
        # 1. 第一路：算法纠错 (difflib) - 返回的是相似度 (0-1)，转换为距离 (1-相似度)
        matches = difflib.get_close_matches(text, cache.keys(), n=1, cutoff=0.3)
        if matches:
            ratio = difflib.SequenceMatcher(None, text, matches[0]).ratio()
            return {"name": matches[0], "source": "Fuzzy", "distance": 1.0 - ratio}
        
        # 2. 第二路：语义召回 (llama.cpp)
        if LANCEDB_AVAILABLE:
            vec = get_llama_cpp_embedding(text)
            res = table.search(vec).limit(1).to_list()
            if res:
                # LanceDB 默认返回的是 _distance
                dist = res[0].get('_distance', 0.5)
                return {"name": res[0]['name'], "source": "llama.cpp", "distance": float(dist)}
        
        return {"name": "None", "source": "Failure", "distance": 1.0}

    def search_pet(self, text):
        res = self.adaptive_search(text, self.pets_cache, self.pets_table)
        return [res] if res["name"] != "None" else []

    def search_skill(self, text):
        res = self.adaptive_search(text, self.skills_cache, self.skills_table)
        return [res] if res["name"] != "None" else []

    def run_tests(self):
        print("=" * 60)
        print("RAG 混合检索（双路纠错）实测报告")
        print("=" * 60)
        
        test_cases = [
            ("落引", "罗隐", self.pets_cache, self.pets_table),
            ("泥江盖甲", "泥浆铠甲", self.skills_cache, self.skills_table),
            ("地面系强力护盾", "泥浆铠甲", self.skills_cache, self.skills_table) # 纯语义测试
        ]

        for query, expected, cache, table in test_cases:
            print(f"\n[测试项] 输入词: '{query}'")
            start = time.time()
            res = self.adaptive_search(query, cache, table)
            elapsed = time.time() - start
            
            status = "[PASS]" if expected in res['name'] else "[FAIL]"
            print(f"  结果: '{res['name']}'")
            print(f"  引擎: {res['source']}")
            print(f"  耗时: {elapsed:.3f}s")
            print(f"  结论: {status}")

        print("\n" + "=" * 60)

if __name__ == "__main__":
    if not LANCEDB_AVAILABLE:
        print("请安装依赖")
    else:
        tester = HybridSearchTester()
        tester.run_tests()
