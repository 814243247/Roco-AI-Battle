import os
import sys

# --- MaaFramework 环境引导：必须在 import maa 之前执行 ---
# 锁定 DLL 加载路径，防止 FileNotFoundError: ...\bin does not exist
MAAFW_PATH = os.path.join(os.path.dirname(__file__), "runtimes", "win-x64", "native")
if os.path.exists(MAAFW_PATH):
    os.environ["MAAFW_BINARY_PATH"] = MAAFW_PATH
# 同时也需要将绑定路径加入 Python 搜索路径（针对 Demo 目录）
BINDING_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "MaaFramework_demo", "source", "binding", "Python"))
if BINDING_PATH not in sys.path:
    sys.path.insert(0, BINDING_PATH)

import ctypes
from ctypes import wintypes
import psutil
import time
import cv2
import numpy as np
import traceback
import re
import json
import hmac
import hashlib
import base64
import threading
import websocket
import ssl
import urllib.parse
import requests
import difflib
from datetime import datetime
from time import mktime
from wsgiref.handlers import format_date_time
from maa.toolkit import Toolkit
from maa.resource import Resource
from maa.controller import Win32Controller
from maa.tasker import Tasker
from maa.custom_action import CustomAction
from maa.context import Context

try:
    import lancedb
    LANCEDB_AVAILABLE = True
except ImportError:
    LANCEDB_AVAILABLE = False
    print("[WARNING] LanceDB 未安装，数据库搜索功能将不可用")

GLOBAL_AI_CLIENT = None
resource = Resource()

def simple_text_to_vector(text: str) -> list:
    vector = np.zeros(768, dtype=np.float32)
    for i, char in enumerate(text):
        vector[i % 768] += ord(char) / 1000.0
    norm = np.linalg.norm(vector)
    if norm > 0:
        vector = vector / norm
    return vector.tolist()

# 属性类型中英文映射 (用于语义化输出)
# 洛克王国世界官方18属性: 普通, 草, 火, 水, 光, 地, 冰, 龙, 电, 毒, 虫, 武, 翼, 萌, 幽, 恶, 机械, 幻
# 数据库英文对应: normal, grass, fire, water, light, ground, ice, dragon, electric, poison, bug, fighting, flying, fairy, ghost, evil, mechanical, illusion
TYPE_EN_TO_CN = {
    "normal": "普通",
    "grass": "草",
    "fire": "火",
    "water": "水",
    "light": "光",
    "ground": "地",
    "ice": "冰",
    "dragon": "龙",
    "electric": "电",
    "poison": "毒",
    "bug": "虫",
    "fighting": "武",
    "flying": "翼",
    "fairy": "萌",
    "ghost": "幽",
    "evil": "恶",
    "mechanical": "机械",
    "illusion": "幻",
    "god": "神",
    "psychic": "超能",
}

class RAGDatabase:
    def __init__(self, db_path=None):
        self.pets = []
        self.skills = []
        self.pet_names = []
        self.skill_names = []
        
        try:
            pet_db_path = os.path.join(os.path.dirname(__file__), "config", "pet_database_full.json")
            with open(pet_db_path, "r", encoding="utf-8") as f:
                self.pets = json.load(f).get("pets", [])
                self.pet_names = [p["name"] for p in self.pets]
                
            skill_db_path = os.path.join(os.path.dirname(__file__), "config", "skill_database.json")
            with open(skill_db_path, "r", encoding="utf-8") as f:
                self.skills = json.load(f).get("skills", [])
                self.skill_names = [s["name"] for s in self.skills]
            print(f"[RAG 数据库] JSON 本地加载成功 | 精灵: {len(self.pets)} | 技能: {len(self.skills)}")
        except Exception as e:
            print(f"[RAG 数据库] 加载失败: {e}")
    
    def search_pet_by_name(self, ocr_text: str, limit: int = 3) -> list:
        if not self.pets or not ocr_text or len(ocr_text) < 2:
            return []
            
        ignore_list = ["更换", "逃跑", "背包", "捕捉", "战报", "技能", "聚能", "首发", "确认"]
        if any(ignore_word in ocr_text for ignore_word in ignore_list):
            return []
        
        matches = []
        for p_name in self.pet_names:
            if (p_name in ocr_text or ocr_text in p_name) and p_name not in matches:
                matches.append(p_name)
                
        if len(ocr_text) >= 2:
            cutoff = 0.7 if len(ocr_text) <= 3 else 0.6
            fuzzy_matches = difflib.get_close_matches(ocr_text, self.pet_names, n=limit, cutoff=cutoff)
            for fm in fuzzy_matches:
                if fm not in matches:
                    matches.append(fm)
                    
        if len(matches) > 0:
            print(f"      [DEBUG] OCR='{ocr_text}' -> 匹配精灵={matches[:limit]}")
                
        matched_pets = []
        for match in matches[:limit]:
            for pet in self.pets:
                if pet["name"] == match:
                    matched_pets.append({
                        "name": pet.get("name", ""),
                        "type": pet.get("type", ""),
                        "secondary_type": pet.get("secondary_type"),
                        "id": pet.get("id", 0)
                    })
                    break
        return matched_pets
    
    def _normalize_ocr(self, text: str) -> str:
        """OCR 结果规范化：处理常见误识别字符"""
        replacements = {
            "关": "矢",  # 风关 -> 风矢
            "诊": "",   # 单字误识别，直接移除
            "风关": "风矢",
        }
        for wrong, right in replacements.items():
            text = text.replace(wrong, right)
        return text

    def search_skill_by_name(self, ocr_text: str, limit: int = 5) -> list:
        if not self.skills or not ocr_text or len(ocr_text) < 2:
            return []

        ignore_list = ["更换", "逃跑", "背包", "捕捉", "战报", "技能", "聚能"]
        if any(ignore_word in ocr_text for ignore_word in ignore_list):
            return []

        # OCR 纠错预处理
        normalized_text = self._normalize_ocr(ocr_text)
        search_candidates = [ocr_text, normalized_text] if normalized_text != ocr_text else [ocr_text]

        # 阶段1: 精确子串匹配（优先级最高）
        exact_matches = []
        for candidate in search_candidates:
            for s_name in self.skill_names:
                if candidate == s_name and s_name not in exact_matches:
                    exact_matches.append(s_name)

        # 阶段2: 包含关系匹配（OCR文本包含技能名 或 技能名包含OCR文本）
        # 限制：技能名包含OCR文本时，要求OCR文本长度>=3，避免"超导"匹配"超导加速"
        contain_matches = []
        for candidate in search_candidates:
            for s_name in self.skill_names:
                if s_name in exact_matches:
                    continue
                # OCR文本包含技能名：如"回旋风暴"包含"风暴"（允许）
                if s_name in candidate and s_name not in contain_matches:
                    contain_matches.append(s_name)
                # 技能名包含OCR文本：要求OCR文本长度>=3，避免短文本误匹配
                # 如"超导"(2字)不应匹配"超导加速"(4字)
                elif candidate in s_name and len(candidate) >= 3 and s_name not in contain_matches:
                    contain_matches.append(s_name)

        # 阶段3: 模糊匹配（仅当精确和包含匹配不足时）
        fuzzy_matches = []
        if len(exact_matches) + len(contain_matches) < limit:
            for candidate in search_candidates:
                cutoff = 0.7 if len(candidate) <= 3 else 0.6
                fm_list = difflib.get_close_matches(candidate, self.skill_names, n=limit, cutoff=cutoff)
                for fm in fm_list:
                    if fm not in exact_matches and fm not in contain_matches and fm not in fuzzy_matches:
                        fuzzy_matches.append(fm)

        # 按优先级合并结果
        matches = exact_matches + contain_matches + fuzzy_matches

        if len(matches) > 0:
            print(f"      [DEBUG] OCR='{ocr_text}' -> 匹配技能={matches[:limit]}")

        matched_skills = []
        for match in matches[:limit]:
            for skill in self.skills:
                if skill["name"] == match:
                    matched_skills.append({
                        "name": skill.get("name", ""),
                        "type": skill.get("type", ""),
                        "attack_type": skill.get("attack_type", ""),
                        "power": skill.get("power", 0),
                        "effect": skill.get("effect", ""),
                        "energy_cost": skill.get("energy"),   # 数据库直接提供能耗
                        "id": skill.get("id", 0)
                    })
                    break
        return matched_skills
    
    def search_skill_by_exact_name(self, skill_name: str) -> dict:
        if not self.skills:
            return None
            
        for skill in self.skills:
            if skill["name"] == skill_name:
                return {
                    "name": skill.get("name", ""),
                    "type": skill.get("type", ""),
                    "attack_type": skill.get("attack_type", ""),
                    "power": skill.get("power", 0),
                    "effect": skill.get("effect", ""),
                    "id": skill.get("id", 0)
                }
        return None

class SparkWSClient:
    def __init__(self, app_id, api_key, api_secret, spark_url, domain="spark-x"):
        self.app_id = app_id
        self.api_key = api_key
        self.api_secret = api_secret
        self.domain = domain
        self.host = urllib.parse.urlparse(spark_url).netloc
        self.path = urllib.parse.urlparse(spark_url).path
        self.spark_url = spark_url
        self.answer = ""
        self.prompt_ready = threading.Event()
        self.response_done = threading.Event()
        self.current_prompt = ""
        self.current_image_base64 = None
        self.ws = None
        self.is_connected = False
        self._is_connecting = False
        self._threads = []

    def disconnect(self):
        self.is_connected = False
        if self.ws:
            try:
                self.ws.close()
            except Exception:
                pass
            self.ws = None
        self.response_done.set()
        self.prompt_ready.set()

    def create_url(self) -> str:
        now = datetime.now()
        date = format_date_time(mktime(now.timetuple()))
        signature_origin = f"host: {self.host}\ndate: {date}\nGET {self.path} HTTP/1.1"
        signature_sha = hmac.new(self.api_secret.encode('utf-8'), signature_origin.encode('utf-8'), digestmod=hashlib.sha256).digest()
        signature_sha_base64 = base64.b64encode(signature_sha).decode(encoding='utf-8')
        authorization_origin = f'api_key="{self.api_key}", algorithm="hmac-sha256", headers="host date request-line", signature="{signature_sha_base64}"'
        authorization = base64.b64encode(authorization_origin.encode('utf-8')).decode(encoding='utf-8')
        v = {"authorization": authorization, "date": date, "host": self.host}
        return self.spark_url + '?' + urllib.parse.urlencode(v)

    def on_message(self, ws, message):
        try:
            data = json.loads(message)
            header = data.get('header', {})
            if header.get('code') != 0:
                self.is_connected = False
            else:
                choices = data.get('payload', {}).get('choices', {})
                status = choices.get('status')
                text_list = choices.get('text', [])
                if text_list: self.answer += text_list[0].get('content', "")
                if status == 2: self.response_done.set()
        except: pass

    def on_error(self, ws, error):
        self.is_connected = False
        self.response_done.set()

    def on_close(self, ws, status, msg):
        self.is_connected = False

    def on_open(self, ws):
        self.is_connected = True
        self._is_connecting = False
        print("  [WebSocket] Spark X 视觉链路已就绪。", flush=True)
        def run_thread():
            while self.is_connected:
                if self.prompt_ready.wait(timeout=1.0):
                    self.response_done.clear()
                    content_list = []
                    if self.current_image_base64:
                        content_list.append({"role": "user", "content": self.current_image_base64, "content_type": "image"})
                    content_list.append({"role": "user", "content": self.current_prompt})
                    data = {
                        "header": {"app_id": self.app_id, "uid": "roco_vlm"},
                        "parameter": {"chat": {"domain": self.domain, "max_tokens": 512}},
                        "payload": {"message": {"text": content_list}}
                    }
                    ws.send(json.dumps(data))
                    self.prompt_ready.clear()
        t = threading.Thread(target=run_thread, daemon=True)
        self._threads.append(t)
        t.start()

    def connect(self):
        if self.is_connected or self._is_connecting: return
        self._is_connecting = True
        ws_url = self.create_url()
        self.ws = websocket.WebSocketApp(ws_url, on_message=self.on_message, on_error=self.on_error, on_close=self.on_close, on_open=self.on_open)
        t = threading.Thread(target=self.ws.run_forever, kwargs={"sslopt": {"cert_reqs": ssl.CERT_NONE}, "ping_interval": 5}, daemon=True)
        self._threads.append(t)
        t.start()

    def ask_vlm(self, prompt, image_base64=None):
        if not self.is_connected:
            self.connect()
            wait_st = time.time()
            while not self.is_connected and time.time() - wait_st < 5: time.sleep(0.1)
        if not self.is_connected: return None
        self.answer = ""
        self.current_prompt = prompt
        self.current_image_base64 = image_base64
        self.response_done.clear()
        self.prompt_ready.set()
        return self.answer if self.response_done.wait(timeout=30) else None

class SparkMaaSClient:
    """讯飞星辰 MaaS HTTP 推理服务（OpenAI 兼容接口）"""
    def __init__(self, api_key: str, model_id: str, base_url: str = "https://maas-api.cn-huabei-1.xf-yun.com/v2", proxy=None):
        self.api_key = api_key      # 格式: "APIKey:APISecret"
        self.model_id = model_id
        self.base_url = base_url.rstrip("/")
        self.proxy = proxy
        self.is_connected = True
        self.url = f"{self.base_url}/chat/completions"

    def connect(self): pass

    def ask_vlm(self, prompt: str, image_base64: str = None) -> str:
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": self.model_id,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "temperature": 0.5,
                "max_tokens": 4096,
            }
            proxies = {"http": self.proxy, "https": self.proxy} if self.proxy else None
            start_t = time.time()
            print(f"  [VLM] 正在通过 讯飞MaaS {self.model_id} 进行决策请求...", flush=True)
            response = requests.post(self.url, headers=headers, json=payload, timeout=30, proxies=proxies)
            latency = time.time() - start_t

            if response.status_code != 200:
                print(f"  [MaaS 错误] HTTP {response.status_code} | 耗时 {latency:.2f}s")
                try:
                    print(f"  [错误详情]: {response.json()}")
                except:
                    print(f"  [响应内容]: {response.text[:200]}")
                return None

            result = response.json()
            choices = result.get("choices", [])
            if choices:
                raw_text = choices[0].get("message", {}).get("content", "")
                print(f"  [AI 原始回执]: \"{raw_text.strip()}\" (耗时: {latency:.2f}s)", flush=True)
                return raw_text
            return None
        except Exception as e:
            print(f"  [MaaS 通讯异常] {str(e)}")
            return None

class DoubaoClient:
    def __init__(self, api_key, model_id="doubao-seed-2-0-lite-260215", proxy=None):
        self.api_key = api_key
        self.model_id = model_id
        self.proxy = proxy
        self.url = "https://ark.cn-beijing.volces.com/api/v3/responses"
        
    def ask_vlm(self, prompt: str, image_base64: str) -> str:
        try:
            payload_size_kb = len(image_base64) / 1024
            print(f"  [监测] 图像 Payload 体积：{payload_size_kb:.1f} KB", flush=True)
            
            image_data_uri = f"data:image/jpeg;base64,{image_base64}"
            
            payload = {
                "model": self.model_id,
                "input": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_image",
                                "image_url": image_data_uri
                            },
                            {
                                "type": "input_text",
                                "text": prompt
                            }
                        ]
                    }
                ]
            }
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            proxies = {"http": self.proxy, "https": self.proxy} if self.proxy else None
            start_t = time.time()
            print(f"  [VLM] 正在通过 {self.model_id} 进行决策请求...", flush=True)
            response = requests.post(self.url, headers=headers, json=payload, timeout=60, proxies=proxies)
            latency = time.time() - start_t
            
            if response.status_code == 429:
                print(f"  [豆包限流] 请求过于频繁，等待 60 秒后重试... | 耗时 {latency:.2f}s")
                time.sleep(60)
                return self.ask_vlm(prompt, image_base64)
                
            if response.status_code != 200:
                print(f"  [豆包错误] HTTP {response.status_code} | 耗时 {latency:.2f}s")
                try:
                    error_data = response.json()
                    print(f"  [错误详情]: {error_data}")
                except:
                    print(f"  [响应内容]: {response.text}")
                return None
                
            result = response.json()
            choices = result.get("choices", [])
            if choices:
                raw_text = choices[0].get("message", {}).get("content", "")
                print(f"  [AI 原始回执]: \"{raw_text.strip()}\" (耗时：{latency:.2f}s)", flush=True)
                return raw_text
            return None
        except Exception as e:
            print(f"  [豆包通讯异常] {str(e)}")
            return None

class GeminiClient:
    def __init__(self, api_key, model_id="gemini-2.5-flash", proxy=None):
        self.api_key = api_key
        self.model_id = model_id
        self.proxy = proxy
        self.is_connected = True
        self.url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent?key={self.api_key}"

    def connect(self): pass

    def ask_vlm(self, prompt: str, image_base64: str = None) -> str:
        try:
            parts = [{"text": prompt}]
            if image_base64:
                payload_size_kb = len(image_base64) / 1024
                print(f"  [监测] 图像 Payload 体积: {payload_size_kb:.1f} KB", flush=True)
                parts.append({"inline_data": {"mime_type": "image/jpeg", "data": image_base64}})

            payload = {"contents": [{"parts": parts}]}
            headers = {"Content-Type": "application/json"}
            proxies = {"http": self.proxy, "https": self.proxy} if self.proxy else None
            start_t = time.time()
            print(f"  [VLM] 正在通过 {self.model_id} 进行决策请求...", flush=True)
            response = requests.post(self.url, headers=headers, json=payload, timeout=60, proxies=proxies)
            latency = time.time() - start_t
            if response.status_code != 200:
                print(f"  [Gemini 错误] HTTP {response.status_code} | 耗时 {latency:.2f}s")
                try:
                    print(f"  [错误详情]: {response.json()}")
                except:
                    print(f"  [响应内容]: {response.text[:300]}")
                return None
            result = response.json()
            candidates = result.get("candidates", [])
            if candidates:
                raw_text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                print(f"  [AI 原始回执]: \"{raw_text.strip()}\" (耗时: {latency:.2f}s)", flush=True)
                return raw_text
            return None
        except Exception as e:
            print(f"  [Gemini 通讯异常] {str(e)}")
            return None


class OllamaClient:
    def __init__(self, base_url="http://127.0.0.1:11434", model_id="gemma4:e2b", proxy=None, no_think=True):
        self.base_url = base_url.rstrip("/")
        self.model_id = model_id
        self.proxy = proxy
        self.no_think = no_think
        self.is_connected = True
        self.chat_url = f"{self.base_url}/api/chat"

    def connect(self):
        """预热模型：keep_alive=-1 让模型常驻内存，避免冷启动超时"""
        print(f"  [Ollama] 正在预热模型 {self.model_id}，首次加载可能需要 30-60 秒...", flush=True)
        try:
            payload = {
                "model": self.model_id,
                "messages": [{"role": "user", "content": "hi"}],
                "stream": False,
                "keep_alive": -1,
                "options": {"num_predict": 1}
            }
            start = time.time()
            resp = requests.post(self.chat_url, json=payload, timeout=120, proxies=None)
            elapsed = time.time() - start
            if resp.status_code == 200:
                print(f"  [Ollama] 模型预热完成，已常驻内存 | 耗时: {elapsed:.1f}s", flush=True)
                self.is_connected = True
            else:
                print(f"  [Ollama] 预热返回 HTTP {resp.status_code}，将在首次对战时重试。", flush=True)
        except Exception as e:
            print(f"  [Ollama] 预热失败（{e}），将在首次对战时重试。", flush=True)

    def ask_vlm(self, prompt: str, image_base64: str) -> str:
        try:
            payload_size_kb = len(image_base64) / 1024
            # Ollama 原生支持 vision 的格式
            # qwen3.5:4b 支持多模态，使用 /api/chat 接口
            content = prompt
            if self.no_think:
                # 关闭思考模式：在提示词前添加 /no_think 指令
                content = "/no_think\n" + prompt

            # Ollama 仅发送文字提示词，图片由前置 OCR 流程已完整提取
            message_payload = {
                "role": "user",
                "content": content,
            }

            payload = {
                "model": self.model_id,
                "messages": [message_payload],
                "stream": False,
                "keep_alive": -1,   # 保持模型常驻内存
                "options": {
                    "temperature": 0.1,
                    "top_p": 0.85,
                    "num_predict": 800,
                }
            }

            # Ollama 通常运行在本地，强制不走代理以避免 127.0.0.1 环路超时和性能损耗
            proxies = None
            start_t = time.time()
            print(f"  [VLM] 正在通过 Ollama {self.model_id} 进行决策请求...", flush=True)
            response = requests.post(self.chat_url, json=payload, timeout=60, proxies=proxies)
            latency = time.time() - start_t

            if response.status_code != 200:
                print(f"  [Ollama 错误] HTTP {response.status_code} | 耗时 {latency:.2f}s")
                try:
                    error_data = response.json()
                    print(f"  [错误详情]: {error_data}")
                except:
                    print(f"  [响应内容]: {response.text[:500]}")
                return None

            result = response.json()
            msg = result.get("message", {})
            raw_text = msg.get("content", "")
            thinking_text = msg.get("thinking", "")
            
            # 如果 content 为空但 thinking 有内容，说明模型在思考模式下只输出了 thinking
            if not raw_text and thinking_text:
                print(f"  [Ollama 提示] content为空，尝试从 thinking 提取...")
                raw_text = thinking_text
            
            if raw_text:
                print(f"  [AI 原始回执]: \"{raw_text.strip()}\" (耗时: {latency:.2f}s)", flush=True)
                return raw_text
            return None
        except Exception as e:
            print(f"  [Ollama 通讯异常] {str(e)}")
            return None

@resource.custom_action("PvPAction")
class PvPAction(CustomAction):
    def __init__(self):
        super().__init__()
        global GLOBAL_AI_CLIENT
        if GLOBAL_AI_CLIENT is None:
            GLOBAL_AI_CLIENT = self.init_ai_client()
        self.ai_client = GLOBAL_AI_CLIENT
        self.rag_db = RAGDatabase()
        self.team_list = []
        self.last_team_req = 0
        
        # 决策冷却机制：防止Ollama无响应时重复请求
        self._last_decision_time = 0
        self._decision_cooldown = 8.0  # 决策冷却8秒

        # --- LanceDB 战术情报检索系统初始化 ---
        self.lance_db = None
        self.battle_intel_table = None
        self._lance_db_initialized = False
        if LANCEDB_AVAILABLE:
            try:
                import lancedb
                db_path = os.path.join(os.path.dirname(__file__), "scripts", "rag_lancedb")
                if os.path.exists(db_path):
                    self.lance_db = lancedb.connect(db_path)
                    self.battle_intel_table = self.lance_db.open_table("battle_intel")
                    self._lance_db_initialized = True
                    print(f"[战术情报] LanceDB 已连接 | battle_intel 表就绪")
                else:
                    print(f"[战术情报] LanceDB 路径不存在: {db_path}")
            except Exception as e:
                print(f"[战术情报] LanceDB 初始化失败: {e}")

        # 缓存机制：避免重复查询相同状态
        self._cache_key = None
        self._cached_intel = []
        self._cache_ttl = 3.0  # 缓存有效期3秒
        self._cache_timestamp = 0

    def __del__(self):
        if self.lance_db:
            try:
                self.lance_db = None
            except Exception:
                pass

    def init_ai_client(self):
        config_path = os.path.join(os.path.dirname(__file__), "config", "ai_config.json")
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                c = json.load(f)
            engine = c.get("current_engine", "gemini")
            proxy = c.get("http_proxy", None)
            if engine == "doubao":
                api_key = c.get("doubao_api_key")
                model_id = c.get("doubao_model_id")
                if api_key and model_id:
                    print(f"  [系统] AI 核心单例化成功：{model_id}", flush=True)
                    return DoubaoClient(api_key, model_id, proxy)
            elif engine == "gemini":
                api_key = c.get("gemini_apikey")
                model_id = c.get("gemini_model_id")
                if api_key and model_id:
                    print(f"  [系统] AI 核心单例化成功：{model_id}", flush=True)
                    return GeminiClient(api_key, model_id, proxy)
            elif engine == "ollama":
                base_url = c.get("ollama_base_url")
                model_id = c.get("ollama_model_id")
                no_think = c.get("ollama_no_think")
                if base_url and model_id:
                    print(f"  [系统] AI 核心单例化成功：Ollama {model_id} (no_think={no_think})", flush=True)
                    client = OllamaClient(base_url, model_id, proxy, no_think)
                    client.connect()  # 预热：将模型加载进内存并设置常驻
                    return client
            elif engine == "spark_maas":
                api_key = c.get("spark_maas_apikey")   # 格式: "APIKey:APISecret"
                model_id = c.get("spark_maas_model_id")
                base_url = c.get("spark_maas_base_url", "https://maas-api.cn-huabei-1.xf-yun.com/v2")
                if api_key and model_id:
                    print(f"  [系统] AI 核心单例化成功：讯飞MaaS {model_id}", flush=True)
                    return SparkMaaSClient(api_key, model_id, base_url, proxy)
            return SparkWSClient(c.get("spark_appid"), c.get("spark_apikey"), c.get("spark_apisecret"), c.get("spark_url"))
        except Exception as e:
            print(f"  [系统] AI 核心初始化失败: {e}")
            return None

    def ocr_roi(self, context: Context, image: np.ndarray, roi: list, upscale: int = 3) -> str:
        x, y, w, h = roi
        crop = image[y:y+h, x:x+w]
        if crop.size == 0: return ""
        enlarged = cv2.resize(crop, None, fx=upscale, fy=upscale, interpolation=cv2.INTER_CUBIC)
        res = context.run_recognition("TempOCR", enlarged, 
            pipeline_override={"TempOCR": {"recognition": "OCR", "roi": [0,0,enlarged.shape[1],enlarged.shape[0]]}})
        return res.best_result.text.strip() if res and res.hit else ""

    def parse_team_ui(self, context: Context, image: np.ndarray):
        h, w = image.shape[:2]
        roi_x0, roi_x1 = 0, int(w * 0.45)
        roi_y0, roi_y1 = int(h * 0.1), int(h * 0.9)
        crop = image[roi_y0:roi_y1, roi_x0:roi_x1]
        
        # 放大 1.5 倍
        enl = cv2.resize(crop, None, fx=1.5, fy=1.5, interpolation=cv2.INTER_CUBIC)
        res = context.run_recognition('TempOCR', enl, pipeline_override={'TempOCR': {'recognition': 'OCR', 'roi': [0, 0, enl.shape[1], enl.shape[0]]}})
        
        pets = []
        if res and res.hit:
            for b in res.all_results:
                txt = b.text
                base_y = b.box[1]
                # 提取潜在精灵名
                p_hits = self.rag_db.search_pet_by_name(txt, limit=1)
                for hit in p_hits:
                    if not any(p['data']['name'] == hit['name'] for p in pets):
                        pets.append({'data': hit, 'y': base_y})
        
        # 按 y 坐标排序
        pets.sort(key=lambda item: item['y'])
        self.team_list = [p['data'] for p in pets[:6]]

    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        try:
            img_job = context.tasker.controller.post_screencap().wait()
            if not img_job.succeeded: return False
            image = img_job.get()
            h, w = image.shape[:2]
            
            enlarged = cv2.resize(image, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
            res = context.run_recognition('TempOCR', enlarged, pipeline_override={'TempOCR': {'recognition': 'OCR', 'roi': [0, 0, w*2, h*2]}})
            
            found_battle = found_team_ui = False
            found_start = found_confirm = None
            if res and res.hit:
                for box in res.all_results:
                    txt = box.text
                    cx, cy = int((box.box[0]+box.box[2]//2)/2.0), int((box.box[1]+box.box[3]//2)/2.0)
                    if ("开始" in txt or "挑战" in txt) and cx > w*0.5: found_start = [cx, cy]
                    elif ("确认" in txt or "首发" in txt) and cy > h*0.5: found_confirm = [cx, cy]
                    elif "逃跑" in txt or "倒计时" in txt or "技能" in txt: found_battle = True
                    elif "大世界小队" in txt or "大世界" in txt or "小队" in txt: found_team_ui = True

            if found_battle:
                return self.run_vlm_battle(context, image)
            
            # 队伍状态检测
            if not self.team_list:
                if found_team_ui:
                    print("  [系统] 捕获到团队排布界面，正在建立大世界小队名册...")
                    self.parse_team_ui(context, image)
                    print(f"  [队伍] 解析完毕 (共{len(self.team_list)}只): {[p['name'] for p in self.team_list]}")
                    context.tasker.controller.post_press_key(27).wait() # Esc退出队伍UI
                    time.sleep(2)
                    return True
                else:
                    now = time.time()
                    if now - self.last_team_req > 8:
                        print("  [系统] 当前小队名册为空 (非战态)，按下 `~` 键请求侦察...")
                        context.tasker.controller.post_press_key(192).wait() # VK_OEM_3
                        self.last_team_req = now
                    return True
            
            if found_confirm:
                context.tasker.controller.post_touch_down(found_confirm[0], found_confirm[1]).wait()
                context.tasker.controller.post_touch_up().wait()
                return True
            elif found_start:
                context.tasker.controller.post_touch_down(found_start[0], found_start[1]).wait()
                context.tasker.controller.post_touch_up().wait()
                return True
            
            time.sleep(1)
            return True
        except:
            print(f"[异常] {traceback.format_exc()}")
            return False

    def _get_pet_type(self, pet_name: str) -> str:
        """从 RAG 数据库查询宠物属性类型"""
        if not self.rag_db or not self.rag_db.pets:
            return ""
        for pet in self.rag_db.pets:
            if pet.get("name") == pet_name:
                return pet.get("type", "")
        return ""
    
    # 定义属性克制关系 (攻击方 -> 被克制方)
    # 数据来源: pet_database_full.json weaknesses字段统计推导
    # 覆盖类型: bug, dragon, electric, evil, fairy, fighting, fire, flying, ghost, grass, ground, ice, illusion, light, mechanical, normal, poison, psychic, water, god
    TYPE_CHART = {
        "water": ["fire", "ground", "mechanical"],
        "fire": ["bug", "grass", "ice", "mechanical"],
        "grass": ["ground", "water"],
        "electric": ["flying", "ground", "water"],
        "ice": ["dragon", "flying", "grass", "ground"],
        "fighting": ["evil", "ice", "mechanical", "normal"],
        "poison": ["grass", "mechanical"],
        "ground": ["electric", "fire", "flying", "mechanical", "poison"],
        "flying": ["bug", "fighting", "grass"],
        "psychic": ["evil", "fighting", "poison"],
        "bug": ["evil", "grass", "psychic"],
        "ghost": ["ghost", "light", "normal", "psychic"],
        "dragon": ["dragon"],
        "fairy": ["dragon", "evil", "fighting"],
        "light": ["dragon", "evil", "ghost"],
        "evil": ["ghost", "light", "psychic"],
        "god": ["bug", "dragon", "electric", "evil", "fighting", "fire", "flying", "ghost", "grass", "ground", "ice", "illusion", "light", "mechanical", "normal", "poison", "psychic", "water"],
        "illusion": ["ghost", "psychic"],
        "mechanical": ["ice"],
        "normal": ["ghost"],
    }
    
    # 定义属性抵抗关系 (防御方 -> 抵抗的攻击方)
    # 数据来源: pet_database_full.json weaknesses字段统计推导
    RESIST_CHART = {
        "water": ["fire", "ice", "mechanical", "water"],
        "fire": ["bug", "fairy", "fire", "grass", "ice", "mechanical"],
        "grass": ["electric", "grass", "ground", "light", "water"],
        "electric": ["electric", "flying", "mechanical"],
        "ice": ["ice"],
        "fighting": ["bug", "evil", "rock"],
        "poison": ["bug", "fairy", "fighting", "grass", "poison"],
        "ground": ["fire", "poison", "rock"],
        "flying": ["bug", "fighting", "grass"],
        "psychic": ["fighting", "psychic"],
        "bug": ["fighting", "grass", "ground"],
        "ghost": ["bug", "poison"],
        "dragon": ["electric", "fire", "grass", "water"],
        "fairy": [],
        "light": ["light"],
        "evil": ["evil", "ghost"],
        "god": [],
        "illusion": ["illusion"],
        "mechanical": ["bug", "dragon", "fairy", "flying", "grass", "ice", "mechanical", "normal", "psychic", "rock"],
        "normal": [],
    }

    def _analyze_team_coverage(self, enemy_type: str) -> tuple:
        """
        分析阵容对敌方属性的覆盖情况
        Returns: (has_counter, counter_types, has_resist, resist_types)
        """
        if not self.team_list or not enemy_type:
            return False, [], False, []
        
        counter_types = []
        resist_types = []
        
        for pet in self.team_list:
            pet_type = pet.get("type", "")
            if not pet_type:
                continue
            # 检查是否克制敌方
            if pet_type in self.TYPE_CHART and enemy_type in self.TYPE_CHART.get(pet_type, []):
                counter_types.append(pet_type)
            # 检查是否抵抗敌方
            if pet_type in self.RESIST_CHART and enemy_type in self.RESIST_CHART.get(pet_type, []):
                resist_types.append(pet_type)
        
        return len(counter_types) > 0, counter_types, len(resist_types) > 0, resist_types
    
    def semanticize_state(self, my_pet: str, my_hp: str, enemy_pet: str, enemy_hp: str, skills: list) -> tuple:
        """
        状态提取与语义化 (Feature Engineering)
        将原始战斗状态转换为双路查询向量
        融入阵容感知：分析后备精灵对敌方的克制/抵抗关系
        
        Returns:
            (scenario_vector_text, action_vector_text): 用于双路并发查询的语义文本
        """
        # --- 路径 A: 场景语义化 (Scenario-centric) ---
        # 提取 HP 数值用于判断危急状态
        my_hp_ratio = 1.0
        enemy_hp_ratio = 1.0
        
        try:
            if "/" in my_hp:
                parts = my_hp.split("/")
                if len(parts) == 2:
                    current, total = float(parts[0]), float(parts[1])
                    if total > 0:
                        my_hp_ratio = current / total
        except:
            pass
            
        try:
            if "/" in enemy_hp:
                parts = enemy_hp.split("/")
                if len(parts) == 2:
                    current, total = float(parts[0]), float(parts[1])
                    if total > 0:
                        enemy_hp_ratio = current / total
        except:
            pass
        
        # 查询双方属性类型
        my_type = self._get_pet_type(my_pet)
        enemy_type = self._get_pet_type(enemy_pet)
        
        # 转换为中文属性名用于语义化 (与策略文本语言一致)
        my_type_cn = TYPE_EN_TO_CN.get(my_type, my_type) if my_type else ""
        enemy_type_cn = TYPE_EN_TO_CN.get(enemy_type, enemy_type) if enemy_type else ""
        
        # 分析阵容覆盖
        has_counter, counter_types, has_resist, resist_types = self._analyze_team_coverage(enemy_type)
        
        # 判断属性克制关系，注入关键词增强向量区分度
        type_advantage_keywords = []
        if my_type and enemy_type:
            if my_type in self.TYPE_CHART and enemy_type in self.TYPE_CHART.get(my_type, []):
                type_advantage_keywords.append(f"{my_type_cn}系克制{enemy_type_cn}系")
            if enemy_type in self.TYPE_CHART and my_type in self.TYPE_CHART.get(enemy_type, []):
                type_advantage_keywords.append(f"{enemy_type_cn}系克制{my_type_cn}系")
        
        # 构建场景描述 (用于场景匹配)
        scenario_parts = [f"我方{my_pet}对战敌方{enemy_pet}"]
        
        if my_type_cn and enemy_type_cn:
            scenario_parts.append(f"{my_type_cn}系宠物面对{enemy_type_cn}系对手")
        elif my_type_cn:
            scenario_parts.append(f"{my_type_cn}系宠物")
        elif enemy_type_cn:
            scenario_parts.append(f"面对{enemy_type_cn}系对手")
        
        # 注入属性克制关键词，增强Type-Advantage策略召回
        if type_advantage_keywords:
            scenario_parts.append(" | ".join(type_advantage_keywords))
        
        if my_hp_ratio < 0.3:
            scenario_parts.append("我方处于危急状态")
        elif my_hp_ratio < 0.6:
            scenario_parts.append("我方血量中等")
        else:
            scenario_parts.append("我方血量健康")
            
        if enemy_hp_ratio < 0.3:
            scenario_parts.append("敌方残血可收割")
        elif enemy_hp_ratio < 0.6:
            scenario_parts.append("敌方血量中等")
        else:
            scenario_parts.append("敌方血量健康")
        
        # 技能信息语义化 (中文属性名)
        skill_types = [s.get('type', '') for s in skills if s.get('name') != '未知']
        skill_types_cn = [TYPE_EN_TO_CN.get(t, t) for t in skill_types if t]
        if skill_types_cn:
            scenario_parts.append(f"可用技能类型: {', '.join(skill_types_cn)}系")
        
        # 阵容感知：后备队伍克制/抵抗信息
        if self.team_list:
            team_types = [p.get('type', '') for p in self.team_list if p.get('type')]
            team_types_cn = [TYPE_EN_TO_CN.get(t, t) for t in team_types]
            if team_types_cn:
                scenario_parts.append(f"后备精灵类型: {', '.join(team_types_cn)}系")
            
            if has_counter and counter_types:
                counter_cn = TYPE_EN_TO_CN.get(counter_types[0], counter_types[0])
                scenario_parts.append(f"后备有克制敌方的{counter_cn}系精灵")
            if has_resist and resist_types:
                resist_cn = TYPE_EN_TO_CN.get(resist_types[0], resist_types[0])
                scenario_parts.append(f"后备有抵抗敌方的{resist_cn}系精灵")
        
        scenario_text = " | ".join(scenario_parts)
        
        # --- 路径 B: 动作语义化 (Action-centric) ---
        # 构建动作意图描述 (用于动作匹配)
        action_parts = []
        
        # 基于状态推断最优动作类型
        if my_hp_ratio < 0.25 and self.team_list:
            if has_resist:
                action_parts.append("需要换宠保命，后备有抵抗属性")
            elif has_counter:
                action_parts.append("需要换宠反击，后备有克制属性")
            else:
                action_parts.append("需要换宠保命")
        elif enemy_hp_ratio < 0.3:
            action_parts.append("需要收割残血")
        else:
            action_parts.append("需要输出伤害")
        
        # 技能威力分析
        high_power_skills = [s for s in skills if s.get('power', 0) > 80 and s.get('name') != '未知']
        if high_power_skills:
            action_parts.append(f"高威力技能: {', '.join([s['name'] for s in high_power_skills])}")
        
        # 属性克制推断 (中文属性名)
        if my_type_cn and enemy_type_cn:
            action_parts.append(f"属性对抗: {my_type_cn}系对{enemy_type_cn}系")
        
        # 阵容协同
        if has_counter:
            action_parts.append(f"阵容优势: 后备可克制敌方")
        if has_resist:
            action_parts.append(f"阵容防御: 后备可抵抗敌方")
        
        action_text = " | ".join(action_parts)
        
        return scenario_text, action_text
    
    def query_battle_intel(self, scenario_text: str, action_text: str, top_k: int = 3) -> list:
        """
        LanceDB 双路并发召回 (Retrieval)
        路径A: 场景语义搜索 | 路径B: 动作语义搜索
        优先召回Type-Advantage策略（基于硬编码属性关系）
        合并去重后返回 top_k 条战术情报
        """
        if not self._lance_db_initialized or self.battle_intel_table is None:
            return []
        
        # 检查缓存
        cache_key = f"{scenario_text}::{action_text}"
        if self._cache_key == cache_key and (time.time() - self._cache_timestamp) < self._cache_ttl:
            return self._cached_intel
        
        try:
            import numpy as np
            
            # === 阶段1: 硬编码Type-Advantage优先召回 ===
            # 从scenario_text提取属性关系，直接匹配策略ID
            priority_results = []
            seen_ids = set()
            
            # 属性名到英文的反向映射
            cn_to_en = {v: k for k, v in TYPE_EN_TO_CN.items()}
            
            # 解析scenario_text中的属性对抗信息
            # 格式: "X系宠物面对Y系对手" 或 "X系克制Y系"
            import re
            type_match = re.search(r'([\u4e00-\u9fff]+)系宠物面对([\u4e00-\u9fff]+)系对手', scenario_text)
            if type_match:
                my_type_cn = type_match.group(1)
                enemy_type_cn = type_match.group(2)
                my_type_en = cn_to_en.get(my_type_cn, '')
                enemy_type_en = cn_to_en.get(enemy_type_cn, '')
                
                if my_type_en and enemy_type_en:
                    # 构建可能的策略ID列表 (兼容中英文ID)
                    # 中文ID格式: "{my}系克{enemy}系" 或 "{my}系克{enemy}"
                    # 旧英文ID格式: "type_{my}_{enemy}"
                    possible_ids = [
                        f"{my_type_cn}系克{enemy_type_cn}系",
                        f"{my_type_cn}系克{enemy_type_cn}",
                        f"type_{my_type_en}_{enemy_type_en}",
                    ]
                    
                    # 尝试从LanceDB精确匹配
                    try:
                        df = self.battle_intel_table.to_pandas()
                        for strategy_id in possible_ids:
                            exact_match = df[df['id'] == strategy_id]
                            if not exact_match.empty:
                                row = exact_match.iloc[0]
                                row_id = row.get('id', strategy_id)
                                if row_id not in seen_ids:
                                    seen_ids.add(row_id)
                                    priority_results.append({
                                        "id": row_id,
                                        "category": row.get('category', '属性优势'),
                                        "scenario": row.get('scenario', ''),
                                        "action": row.get('action', ''),
                                        "text": row.get('text', ''),
                                        "source": row.get('source', '官方属性表'),
                                        "score": 0.0  # 最高优先级
                                    })
                                break  # 找到即停止
                    except Exception:
                        pass
            
            # === 阶段2: 向量语义搜索补充 ===
            # 生成查询向量
            scenario_vector = simple_text_to_vector(scenario_text)
            action_vector = simple_text_to_vector(action_text)
            
            # 双路并发查询
            results_a = self.battle_intel_table.search(scenario_vector).metric("cosine").limit(top_k * 2).to_pandas()
            results_b = self.battle_intel_table.search(action_vector).metric("cosine").limit(top_k * 2).to_pandas()
            
            # 合并与去重
            for i in range(max(len(results_a), len(results_b))):
                if i < len(results_a):
                    row = results_a.iloc[i]
                    row_id = row.get('id', f"a_{i}")
                    if row_id not in seen_ids:
                        seen_ids.add(row_id)
                        priority_results.append({
                            "id": row_id,
                            "category": row.get('category', '未知'),
                            "scenario": row.get('scenario', ''),
                            "action": row.get('action', ''),
                            "text": row.get('text', ''),
                            "source": row.get('source', 'unknown'),
                            "score": float(row.get('_distance', 0)) if '_distance' in row else 0.0
                        })
                
                if i < len(results_b):
                    row = results_b.iloc[i]
                    row_id = row.get('id', f"b_{i}")
                    if row_id not in seen_ids:
                        seen_ids.add(row_id)
                        priority_results.append({
                            "id": row_id,
                            "category": row.get('category', '未知'),
                            "scenario": row.get('scenario', ''),
                            "action": row.get('action', ''),
                            "text": row.get('text', ''),
                            "source": row.get('source', 'unknown'),
                            "score": float(row.get('_distance', 0)) if '_distance' in row else 0.0
                        })
            
            # 按相似度排序并截断
            priority_results.sort(key=lambda x: x['score'])
            final_results = priority_results[:top_k]
            
            # 更新缓存
            self._cache_key = cache_key
            self._cached_intel = final_results
            self._cache_timestamp = time.time()
            
            return final_results
            
        except Exception as e:
            print(f"[战术情报] 查询失败: {e}")
            return []
    
    def format_intel_for_prompt(self, intel_list: list) -> str:
        """将检索到的战术情报格式化为提示词片段"""
        if not intel_list:
            return ""
        
        lines = ["\n【战术情报参考】(来自历史对战数据库)"]
        for i, intel in enumerate(intel_list, 1):
            lines.append(f"  [{i}] {intel['category']} | 场景: {intel['scenario']}")
            lines.append(f"      建议: {intel['action']}")
            if intel.get('source') and intel['source'] != 'unknown':
                lines.append(f"      来源: {intel['source']}")
        lines.append("  [注意] 以上情报仅供参考，请结合当前实际情况决策\n")
        
        return "\n".join(lines)

    def run_vlm_battle(self, context: Context, image: np.ndarray) -> bool:
        h, w = image.shape[:2]
        
        print("\n" + "="*60)
        print("[OCR 阶段] 正在识别战斗信息...")
        
        # 1. 动态感知：空间隔离提取
        my_pet_raw = enemy_pet_raw = "识别中"
        my_pet_rag = enemy_pet_rag = "未知"
        my_hp = enemy_hp = "未知"
        
        # 1. 顶部感知：宠物名与 HP (Y < 35%)
        # 使用 2.5x 缩放进行识别
        enlarged_top = cv2.resize(image[0:int(h*0.35), 0:w], None, fx=2.5, fy=2.5, interpolation=cv2.INTER_CUBIC)
        ocr_res_top = context.run_recognition('TempOCR1', enlarged_top, pipeline_override={'TempOCR1': {'recognition': 'OCR', 'roi': [0, 0, int(w*2.5), int(h*0.35*2.5)]}})
        
        if ocr_res_top and ocr_res_top.hit:
            for res_box in ocr_res_top.all_results:
                txt, raw_box = res_box.text, res_box.box
                box = [val / 2.5 for val in raw_box] # 还原坐标
                
                # 匹配血量格式: 123/456 或 92%
                hp_match = re.search(r'(?<![★P])(\d+)/(\d+)', txt)
                percent_match = re.search(r'(\d+)%', txt)
                if hp_match:
                    if box[0] < w/2: my_hp = txt
                    else: enemy_hp = txt
                elif percent_match:
                    # 百分比血量通常是敌方
                    if box[0] >= w/2:
                        enemy_hp = txt
                        print(f"      [DEBUG] 敌方百分比血量: {enemy_hp}")
                else:
                    hit = self.rag_db.search_pet_by_name(txt, limit=1)
                    if hit: # 分值过滤
                        if box[0] < w/2:
                            my_pet_raw, my_pet_rag = txt, hit[0]['name']
                        else:
                            enemy_pet_raw, enemy_pet_rag = txt, hit[0]['name']

        # 2. 能量识别 (左下角)
        energy_text = "未知"
        energy_roi = image[int(h*0.85):h, 0:int(w*0.15)]
        if energy_roi.size > 0:
            energy_enl = cv2.resize(energy_roi, None, fx=2.5, fy=2.5, interpolation=cv2.INTER_CUBIC)
            energy_res = context.run_recognition('TempOCR_Energy', energy_enl, pipeline_override={'TempOCR_Energy': {'recognition': 'OCR', 'roi': [0, 0, energy_enl.shape[1], energy_enl.shape[0]]}})
            if energy_res and energy_res.hit:
                for e_box in energy_res.all_results:
                    e_txt = e_box.text
                    # 匹配能量格式如 "2/10" 或 "10/10"
                    e_match = re.search(r'(\d+)/(\d+)', e_txt)
                    if e_match:
                        energy_text = e_txt
                        print(f"      [DEBUG] 能量识别: {energy_text}")
                        break

        # 3. 左侧技能栏感知：技能呈垂直排列
        # 根据截图确凿证据，技能(1-4)排布在屏幕左侧的中下区域，从上往下排列。之前 y=0.55 的切分把 1/2 技能物理腰斩了。
        roi_y = int(h * 0.25)
        roi_x0 = int(w * 0.0)
        roi_x1 = int(w * 0.40) # 技能主要集中在左边40%区间
        skill_crop = image[roi_y:h, roi_x0:roi_x1]
        
        # 放大 2.5 倍以确保清晰度（提高生僻字识别率）
        skill_enl = cv2.resize(skill_crop, None, fx=2.5, fy=2.5, interpolation=cv2.INTER_CUBIC)
        skill_res = context.run_recognition('TempOCR', skill_enl, pipeline_override={'TempOCR': {'recognition': 'OCR', 'roi': [0, 0, skill_enl.shape[1], skill_enl.shape[0]]}})
        
        found_skills_meta = []
        energy_candidates = []  # (y坐标, 数字字符串) 能耗徽章候选
        if skill_res and skill_res.hit:
            for b in skill_res.all_results:
                txt = b.text
                base_y = roi_y + (b.box[1] / 2.5)
                print(f"      [DEBUG OCR] 技能视窗捕获: '{txt}', Y: {base_y:.1f}")
                
                if txt:
                    # 纯数字（1-9）：可能是能耗徽章
                    if re.fullmatch(r'[1-9]', txt.strip()):
                        energy_candidates.append((base_y, int(txt.strip())))
                        continue

                    # 识别子串并全量榨取
                    s_hits = self.rag_db.search_skill_by_name(txt, limit=4)
                    for s_hit in s_hits:
                        if any(s['data']['name'] == s_hit['name'] for s in found_skills_meta):
                            continue
                        idx = txt.find(s_hit['name'])
                        micro_y = base_y + (idx * 15 if idx > 0 else 0)
                        found_skills_meta.append({"data": s_hit, "y": micro_y})
                        print(f"      [DEBUG] 隐式萃取 -> 命中技能: {s_hit['name']} (最终Y坐标: {micro_y:.1f})")

        # 关键修正：既然技能是垂直排列的 (1, 2, 3, 4)，我们必须根据 Y 坐标【从上到下】进行排序！
        found_skills_meta.sort(key=lambda item: item['y'])
        skills = []
        seen_names = set()
        for s in found_skills_meta:
            if s['data']['name'] not in seen_names and len(skills) < 4:
                skill_entry = dict(s['data'])  # 复制，避免修改原始数据库对象
                # 优先使用数据库中的能耗，OCR 徽章作为 fallback
                if skill_entry.get('energy_cost') is None:
                    skill_y = s['y']
                    best_energy = None
                    best_dist = 999
                    for (ey, ev) in energy_candidates:
                        dist = skill_y - ey
                        if 0 < dist < 80 and dist < best_dist:
                            best_dist = dist
                            best_energy = ev
                    skill_entry['energy_cost'] = best_energy
                skills.append(skill_entry)
                seen_names.add(s['data']['name'])
        
        # 如果识别到超过4个技能，只保留前4个（按Y坐标排序后的）
        skills = skills[:4]
        
        while len(skills) < 4:
            skills.append({"name": "未知", "type": "未知", "power": 0, "effect": "未知", "energy_cost": None})

        print(f"  [空间隔离感知结果]")
        print(f"    我方: {my_pet_rag} (HP:{my_hp}) | 敌方: {enemy_pet_rag} (HP:{enemy_hp}) | 能量:{energy_text}")
        print(f"    能耗徽章候选: {energy_candidates}")
        for i, s in enumerate(skills, 1):
            ec = f" ★{s['energy_cost']}" if s.get('energy_cost') is not None else ""
            print(f"    槽位{i}: {s['name']}{ec}")

        # ==========================================
        # 换宠界面检测：全部技能为未知 → 当前展示的是换宠面板
        # 识别各槽位血量 → 构建换宠提示词 → 调用 AI 决策
        # ==========================================
        all_skills_unknown = all(s["name"] == "未知" for s in skills)
        if all_skills_unknown:
            now = time.time()
            if now - self._last_decision_time < 3.0:  # 换宠冷却独立3秒
                print(f"  [换宠冷却] 冷却中，跳过...")
                return True

            print("  [换宠界面] 检测到换宠面板，正在识别各槽位血量...")

            # --- 像素采样：估算各槽位 HP 百分比 ---
            # 换宠面板宠物槽竖向排列在屏幕左侧 (x: 5%~20%, y: 15%~90%)
            # 每个宠物卡片高度约占总高度的 14%，HP 条在卡片下方约 60% 处
            slot_hp_list = []
            panel_x0 = int(w * 0.05)
            panel_x1 = int(w * 0.20)
            bar_width_ref = panel_x1 - panel_x0  # HP 条参考宽度

            for slot_idx in range(5):
                # 槽位 Y 中心位置（从顶部约 18% 开始，每格约 14%）
                slot_y_center = int(h * (0.18 + slot_idx * 0.145))
                # HP 条区域：宠物图标下方细长区域
                bar_y0 = slot_y_center + int(h * 0.04)
                bar_y1 = bar_y0 + max(4, int(h * 0.012))
                bar_crop = image[bar_y0:bar_y1, panel_x0:panel_x1]

                if bar_crop.size == 0:
                    slot_hp_list.append(100)
                    continue

                # 统计绿色像素（HP 条为绿色）：G > 100, R < 150, B < 100
                bar_bgr = bar_crop
                green_mask = (
                    (bar_bgr[:, :, 1].astype(int) > 100) &
                    (bar_bgr[:, :, 0].astype(int) < 150) &
                    (bar_bgr[:, :, 2].astype(int) < 150)
                )
                green_cols = int(np.any(green_mask, axis=0).sum())
                hp_pct = int(green_cols / max(bar_width_ref, 1) * 100)
                hp_pct = max(0, min(100, hp_pct))
                slot_hp_list.append(hp_pct)
                print(f"    槽位{slot_idx+1} HP 采样: {hp_pct}%")

            # --- 构建换宠决策提示词（直接遍历 team_list，索引即槽位号）---
            slot_lines = []
            available_slots = []

            if not self.team_list:
                # team_list 为空时退化：只用 HP 采样数据
                for i, hp_pct in enumerate(slot_hp_list, 1):
                    status = "【HP耗尽，不可选】" if hp_pct < 5 else ""
                    slot_lines.append(f"  [{i}] 精灵{i} HP:{hp_pct}% {status}".rstrip())
                    if hp_pct >= 5:
                        available_slots.append(i)
            else:
                for i, pet in enumerate(self.team_list, 1):
                    hp_pct = slot_hp_list[i - 1] if i <= len(slot_hp_list) else 0
                    pet_name = pet.get("name", f"精灵{i}")
                    is_current = "【当前上场】" if pet_name == my_pet_rag else ""

                    # 从数据库查完整属性
                    db_data = get_pet_full_data(pet_name)
                    type_cn = TYPE_EN_TO_CN.get(db_data.get("type", ""), db_data.get("type", ""))
                    sec_type = db_data.get("secondary_type")
                    sec_cn = TYPE_EN_TO_CN.get(sec_type, sec_type) if sec_type else None
                    type_str = f"{type_cn}" + (f"/{sec_cn}" if sec_cn else "")

                    stats = db_data.get("base_stats", {})
                    stats_str = ""
                    if stats:
                        stats_str = (f" | 攻:{int(stats.get('atk',0))} 防:{int(stats.get('def',0))}"
                                     f" 魔攻:{int(stats.get('spatk',0))} 魔防:{int(stats.get('spdef',0))}"
                                     f" 速:{int(stats.get('spd',0))}")

                    weaknesses = db_data.get("weaknesses", {})
                    weak_list = [TYPE_EN_TO_CN.get(t, t) for t in weaknesses.get("weak_to", [])]
                    resist_list = [TYPE_EN_TO_CN.get(t, t) for t in weaknesses.get("resist", [])]
                    immune_list = [TYPE_EN_TO_CN.get(t, t) for t in weaknesses.get("immune", [])]
                    weak_str = ""
                    if weak_list:   weak_str += f" | 弱点:{','.join(weak_list)}"
                    if resist_list: weak_str += f" | 抗性:{','.join(resist_list)}"
                    if immune_list: weak_str += f" | 免疫:{','.join(immune_list)}"

                    status = "【HP耗尽，不可选】" if hp_pct < 5 else is_current
                    line = f"  [{i}] {pet_name}（{type_str}）HP:{hp_pct}%{stats_str}{weak_str} {status}".rstrip()
                    slot_lines.append(line)

                    if hp_pct >= 5 and not is_current:
                        available_slots.append(i)

            # 如果没有可用槽位（全部耗尽或只剩当前精灵），直接退出
            if not available_slots:
                print("  [换宠] 无可用精灵，跳过换宠")
                self._last_decision_time = now
                time.sleep(2)
                return True

            switch_prompt = f"""你是洛克王国对战助手，当前需要选择替换上场的精灵。

【当前战场】
敌方精灵: {enemy_pet_rag} (HP: {enemy_hp})
当前上场: {my_pet_rag} (HP: {my_hp})

【可选择的精灵】（按槽位1-5）
{chr(10).join(slot_lines)}

【决策要求】
1. 只能选择 HP≥5% 且未标注【当前上场】或【HP耗尽】的精灵
2. 优先选择属性克制敌方的精灵
3. 第一行只输出槽位数字（{"/".join(str(s) for s in available_slots)} 中的一个）
4. 第二行输出换宠理由（一句话）

请输出你的决策："""

            print(f"\n[换宠决策提示词]:\n{switch_prompt}")

            if not self.ai_client:
                # 无 AI 客户端时退化：选第一个非当前且 HP > 0 的槽位
                for i, hp in enumerate(slot_hp_list, 1):
                    if hp > 0 and self.team_list and self.team_list[i-1].get("name") != my_pet_rag:
                        context.tasker.controller.post_press_key(48 + i).wait()
                        time.sleep(0.2)
                        context.tasker.controller.post_press_key(32).wait()  # 空格确认
                        self._last_decision_time = now
                        time.sleep(3)
                        return True
                return True

            switch_decision = self.ai_client.ask_vlm(switch_prompt, None)
            self._last_decision_time = now

            if switch_decision:
                # 提取槽位数字 1-5
                slot_match = re.search(r'\b([1-5])\b', switch_decision)
                if slot_match:
                    target_slot = int(slot_match.group(1))
                    print(f"  >>> [换宠决策] AI 选择槽位 {target_slot}", flush=True)
                    context.tasker.controller.post_press_key(48 + target_slot).wait()
                    time.sleep(0.2)
                    context.tasker.controller.post_press_key(32).wait()  # 空格确认
                else:
                    fallback = available_slots[0] if available_slots else 1
                    print(f"  [换宠] AI 输出无法解析，选择可用槽位 {fallback}")
                    context.tasker.controller.post_press_key(48 + fallback).wait()
                    time.sleep(0.2)
                    context.tasker.controller.post_press_key(32).wait()  # 空格确认
            else:
                fallback = available_slots[0] if available_slots else 1
                print(f"  [换宠] AI 无响应，选择可用槽位 {fallback}")
                context.tasker.controller.post_press_key(48 + fallback).wait()
                time.sleep(0.2)
                context.tasker.controller.post_press_key(32).wait()  # 空格确认

            time.sleep(3)
            return True

        # 提取状态 → 语义化 → 双路并发查询 → 拼接提示词
        # 目标: 整体耗时 < 1 秒
        # ==========================================
        pipeline_start = time.time()
        
        # Step 1 & 2: 状态提取与语义化
        semantic_start = time.time()
        scenario_text, action_text = self.semanticize_state(my_pet_rag, my_hp, enemy_pet_rag, enemy_hp, skills)
        semantic_cost = time.time() - semantic_start
        
        # Step 3: 双路并发查询 LanceDB
        retrieval_start = time.time()
        intel_list = self.query_battle_intel(scenario_text, action_text, top_k=1)
        retrieval_cost = time.time() - retrieval_start
        
        # Step 4: 格式化并拼接提示词
        intel_text = self.format_intel_for_prompt(intel_list)
        prompt = self.build_battle_prompt(my_pet_rag, my_hp, enemy_pet_rag, enemy_hp, skills, intel_text, energy_text)
        
        pipeline_cost = time.time() - pipeline_start
        
        # 性能报告
        print(f"\n[召回管线] 语义化: {semantic_cost*1000:.1f}ms | 检索: {retrieval_cost*1000:.1f}ms | 总耗时: {pipeline_cost*1000:.1f}ms")
        if intel_list:
            print(f"[召回管线] 命中 {len(intel_list)} 条战术情报:")
            for intel in intel_list:
                print(f"  - [{intel['category']}] {intel['scenario'][:40]}...")
        else:
            print(f"[召回管线] 未命中战术情报 (LanceDB: {'就绪' if self._lance_db_initialized else '未就绪'})")
        
        print("\n" + "="*60)
        print(f"[VLM 提示词]:\n{prompt}")
        print("="*60 + "\n")
        
        # 决策冷却检查
        now = time.time()
        if now - self._last_decision_time < self._decision_cooldown:
            remaining = self._decision_cooldown - (now - self._last_decision_time)
            print(f"  [决策冷却] 等待 {remaining:.1f} 秒后再次决策...")
            return True
        
        target_w = 768
        if w > target_w:
            scale = target_w / w
            image = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        image = cv2.copyMakeBorder(image, 10, 10, 10, 10, cv2.BORDER_CONSTANT, value=[255, 255, 255])
        _, buffer = cv2.imencode('.jpg', image, [int(cv2.IMWRITE_JPEG_QUALITY), 50])
        img_base64 = base64.b64encode(buffer).decode('utf-8')
        
        if not self.ai_client:
            print("  [决策失败] AI 客户端未初始化，请检查配置文件和模型服务...")
            return True
            
        decision = self.ai_client.ask_vlm(prompt, img_base64)
        if not decision:
            print("  [决策失败] AI 无响应，进入冷却...")
            self._last_decision_time = now
            return True
        
        self._last_decision_time = now
        
        # 从AI输出中提取指令
        decision_upper = decision.upper()
        
        # 策略1: 从第一行提取（最可能的位置）
        first_line = decision_upper.split('\n')[0].strip()
        match = re.search(r'^([1234XE][1-6]?)$', first_line)
        
        # 策略2: 搜索独立的指令模式（前后无其他字母数字）
        if not match:
            match = re.search(r'(?<![A-Z0-9])([1234XE][1-6]?)(?![A-Z0-9])', decision_upper)
        
        # 策略3: 如果策略2失败，尝试从文本中查找任何出现的指令
        if not match:
            match = re.search(r'([1234XE][1-6]?)', decision_upper)
        
        if not match:
            print(f"  [AI 无效输出] 无法从文本中提取指令: {decision[:100]}")
            return True
        
        final_cmd = match.group(1)
        action_map = {"1": 49, "2": 50, "3": 51, "4": 52, "X": 88, "E": 69}
        
        print(f"  >>> VLM 决策(提取): {final_cmd}", flush=True)
        if final_cmd.startswith('E') and len(final_cmd) == 2:
            key1 = 69 # E
            key2 = 48 + int(final_cmd[1]) # 1->49
            context.tasker.controller.post_press_key(key1).wait()
            time.sleep(1) # 等待队伍面板展开
            context.tasker.controller.post_press_key(key2).wait()
            print(f"  >>> [指令注入] 组合技注入成功 -> 换宠序列 E -> {final_cmd[1]}")
        else:
            key_code = action_map.get(final_cmd)
            if key_code:
                context.tasker.controller.post_press_key(key_code).wait()
                print(f"  >>> [指令注入] 确认单动作: {final_cmd}")
        
        time.sleep(5)
        return True
    
    def _get_type_advice(self, my_type: str, enemy_type: str) -> str:
        """根据属性类型生成克制建议文本"""
        if not my_type or not enemy_type:
            return ""
        
        advice_parts = []
        my_type_cn = TYPE_EN_TO_CN.get(my_type, my_type)
        enemy_type_cn = TYPE_EN_TO_CN.get(enemy_type, enemy_type)
        
        # 我方克制敌方
        if my_type in self.TYPE_CHART and enemy_type in self.TYPE_CHART.get(my_type, []):
            advice_parts.append(f"{my_type_cn}系克制{enemy_type_cn}系，造成2倍伤害")
        
        # 敌方克制我方
        if enemy_type in self.TYPE_CHART and my_type in self.TYPE_CHART.get(enemy_type, []):
            advice_parts.append(f"{enemy_type_cn}系克制{my_type_cn}系，敌方对我方造成2倍伤害")
        
        # 我方抵抗敌方
        if my_type in self.RESIST_CHART and enemy_type in self.RESIST_CHART.get(my_type, []):
            advice_parts.append(f"{my_type_cn}系抵抗{enemy_type_cn}系，受到0.5倍伤害")
        
        # 敌方抵抗我方
        if enemy_type in self.RESIST_CHART and my_type in self.RESIST_CHART.get(enemy_type, []):
            advice_parts.append(f"{enemy_type_cn}系抵抗{my_type_cn}系，我方对其仅造成0.5倍伤害")
        
        # 敌方被哪些属性克制
        enemy_weaknesses = []
        for atk_type, weak_types in self.TYPE_CHART.items():
            if enemy_type in weak_types:
                atk_type_cn = TYPE_EN_TO_CN.get(atk_type, atk_type)
                enemy_weaknesses.append(atk_type_cn)
        if enemy_weaknesses:
            advice_parts.append(f"{enemy_type_cn}系被以下属性克制: {', '.join(enemy_weaknesses)}系")
        
        return " | ".join(advice_parts) if advice_parts else ""

    def build_battle_prompt(self, my_pet: str, my_hp: str, enemy_pet: str, enemy_hp: str, skills: list, intel_text: str = "", energy: str = "未知") -> str:
        # 解析当前能量数值用于可用性判断
        current_energy = None
        energy_match = re.search(r'(\d+)\s*/\s*\d+', energy)
        if energy_match:
            current_energy = int(energy_match.group(1))

        skills_info = "可用技能:\n"
        for i, skill in enumerate(skills, 1):
            ec = skill.get('energy_cost')
            if ec is not None:
                castable = "✓可用" if (current_energy is None or current_energy >= ec) else "✗能量不足"
                energy_str = f" | 能耗:★{ec}({castable})"
            else:
                energy_str = ""
            skills_info += f"  [{i}] {skill['name']} - 威力:{skill['power']} | 类型:{skill['type']} | 效果:{skill['effect']}{energy_str}\n"

        # 查询双方属性并生成克制建议
        my_type = self._get_pet_type(my_pet)
        enemy_type = self._get_pet_type(enemy_pet)
        type_advice = self._get_type_advice(my_type, enemy_type)
        
        prompt = f"""你是顶级博弈专家，请做出最优决策。
【战场信息】
我方精灵: {my_pet} (HP: {my_hp})
敌方精灵: {enemy_pet} (HP: {enemy_hp})
当前能量: {energy}

{skills_info}"""
        
        if type_advice:
            prompt += f"\n【属性克制】{type_advice}\n"

        if self.team_list:
            team_str = "\n【后备队伍】 (按 1-6 顺序):\n"
            for i, p in enumerate(self.team_list, 1):
                team_str += f"  [{i}] {p['name']} (类型: {p.get('type', '')})\n"
            prompt += team_str
        
        # --- 动态注入检索到的战术情报 ---
        if intel_text:
            prompt += intel_text
            
        prompt += """\n【可用指令】
1-4: 释放对应的四个技能
X: 恢复5点能量
E: 战替换后备宠物"""

        if self.team_list:
            prompt += " (您可以直接输出 E1~E6 组合键，例如 E2 代表替换为队伍里的第 2 只宠物)"

        prompt += """\n\n【决策要求】
1. 考虑技能威力和效果
2. 参考战术情报
3. 第一行请仅输出一个指令
4. 必须在20秒内做出决策

第一行输出指令，第二行输出解释："""
        
        return prompt

def find_roco_window_hwnd():
    pids = [p.info['pid'] for p in psutil.process_iter(['name', 'pid']) if "NRC-Win64-Shipping" in p.info['name']]
    if not pids: return None
    user32 = ctypes.windll.user32
    chosen = [None]
    def cb(hwnd, _):
        if not user32.IsWindowVisible(hwnd): return True
        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value in pids:
            rect = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            if (rect.right - rect.left) > 100:
                cls = ctypes.create_string_buffer(256)
                user32.GetClassNameA(hwnd, cls, 256)
                if cls.value.decode() == "UnrealWindow":
                    chosen[0] = hwnd
                    return False
        return True
    user32.EnumWindows(ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)(cb), 0)
    return chosen[0]

def run_pvp_ai():
    is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
    admin_str = "管理员 (Elevated)" if is_admin else "普通用户 (LUA - 可能导致 Error 5)"
    
    script_dir = r"D:\Project\AutoPlayGame"
    Toolkit.init_option(script_dir)
    res_bundle = os.path.join(script_dir, "RocoAutomation", "assets", "resource").replace("\\", "/")
    
    config_path = os.path.join(os.path.dirname(__file__), "config", "ai_config.json")
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            conf = json.load(f)
        engine = conf.get("current_engine", "gemini")
        if engine == "doubao":
            model_id = conf.get("doubao_model_id", "doubao-seed-2-0-lite-260215")
            engine_name = f"{model_id} (Singleton)"
        elif engine == "gemini":
            model_id = conf.get("gemini_model_id", "gemini-2.5-flash")
            engine_name = f"{model_id} (Singleton)"
        elif engine == "ollama":
            model_id = conf.get("ollama_model_id", "qwen3.5:4b")
            no_think = conf.get("ollama_no_think", True)
            engine_name = f"Ollama {model_id} (no_think={no_think})"
        else:
            engine_name = "讯飞星火"
    except: engine_name = "未知"
    
    print("="*60)
    print(f"  [系统状态] 权限身份: {admin_str}")
    print(f"  [AI 核心状态] 引擎: {engine_name} | 抗泄露单例化: 已开启")
    print(f"  [RAG 数据库] LanceDB: {'已连接' if LANCEDB_AVAILABLE else '未安装'}")
    print("="*60 + "\n")

    last_hwnd = None
    tasker = None
    controller = None

    def cleanup():
        print("\n[系统] 正在释放资源...")
        global GLOBAL_AI_CLIENT
        if GLOBAL_AI_CLIENT and hasattr(GLOBAL_AI_CLIENT, 'disconnect'):
            try:
                GLOBAL_AI_CLIENT.disconnect()
                print("  [资源] AI 客户端已断开")
            except Exception as e:
                print(f"  [资源] AI 客户端断开异常: {e}")
        if tasker:
            try:
                # Tasker 并没有 stop 方法，直接置空即可
                tasker = None
                print("  [资源] Tasker 已释放")
            except Exception as e:
                print(f"  [资源] Tasker 释放异常: {e}")
        if controller:
            try:
                controller.post_connection().wait()
                print("  [资源] Controller 已释放")
            except Exception as e:
                print(f"  [资源] Controller 释放异常: {e}")
        print("[系统] 资源释放完毕，退出。")

    import atexit
    atexit.register(cleanup)

    try:
        while True:
            hwnd = find_roco_window_hwnd()
            if not hwnd:
                last_hwnd = None
                if tasker:
                    tasker = None
                if controller:
                    try:
                        controller.post_connection().wait()
                    except:
                        pass
                    controller = None
                time.sleep(5)
                continue
            if hwnd != last_hwnd:
                print(f"[系统] 发现目标窗口 (HWND: {hwnd})，初始化后台连接...")
                # 使用 18 (Background) 支持被遮挡截图，使用 2 (SendMessage) 阻止抢占用户物理鼠标，彻底实现静默挂机！
                controller = Win32Controller(hWnd=hwnd, screencap_method=18, mouse_method=2, keyboard_method=2)
                if not controller.post_connection().wait().succeeded:
                    time.sleep(5)
                    continue
                resource.post_bundle(res_bundle).wait()
                tasker = Tasker()
                tasker.bind(resource, controller)
                last_hwnd = hwnd
                print("[系统] 后台挂载完毕。")
            if tasker:
                tasker.post_task("PvPAction").wait()
            time.sleep(1)
    except KeyboardInterrupt:
        cleanup()

if __name__ == "__main__":
    run_pvp_ai()
