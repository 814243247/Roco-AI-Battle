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

class EmbeddingClient:
    """使用 llama.cpp 生成语义向量 (支持 A卡/N卡 GPU 加速)"""
    def __init__(self, model_path: str):
        self.model_path = model_path
        self._cache = {}
        self.llm = None
        try:
            from llama_cpp import Llama
            print(f"  [系统] 正在加载本地 Llama.cpp 向量模型 (尝试调用 GPU): {os.path.basename(model_path)} ...", flush=True)
            self.llm = Llama(
                model_path=model_path,
                embedding=True,
                n_gpu_layers=-1, # -1 意味着将尽可能多的层卸载到 GPU 上 (CUDA / Vulkan / ROCm)
                verbose=False
            )
            print(f"  [系统] Llama.cpp 向量模型加载成功！", flush=True)
        except ImportError:
            print(f"  [警告] 未安装 llama-cpp-python，请根据您的显卡安装对应版本 (CUDA / Vulkan)。", flush=True)
        except Exception as e:
            print(f"  [警告] 加载模型失败，请检查路径是否正确: {e}", flush=True)
        
    def get_embedding(self, text: str) -> list:
        """获取文本的embedding向量，带缓存"""
        if text in self._cache:
            return self._cache[text]
        
        if self.llm:
            try:
                result = self.llm.create_embedding(text)
                embedding = result["data"][0]["embedding"]
                if embedding:
                    self._cache[text] = embedding
                    return embedding
            except Exception as e:
                print(f"  [Embedding错误] {e}")
        
        # 失败时回退到简单哈希
        return self._fallback_vector(text)
    
    def _fallback_vector(self, text: str) -> list:
        """简单的哈希回退方案"""
        vector = np.zeros(768, dtype=np.float32)
        for i, char in enumerate(text):
            vector[i % 768] += ord(char) / 1000.0
        norm = np.linalg.norm(vector)
        if norm > 0:
            vector = vector / norm
        return vector.tolist()

# 全局Embedding客户端实例
GLOBAL_EMBEDDING_CLIENT = None

def get_embedding_client() -> EmbeddingClient:
    """获取或创建Embedding客户端单例"""
    global GLOBAL_EMBEDDING_CLIENT
    if GLOBAL_EMBEDDING_CLIENT is None:
        # 尝试从配置读取
        config_path = os.path.join(os.path.dirname(__file__), "config", "ai_config.json")
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                c = json.load(f)
            model_path = c.get("llama_cpp_embedding_model_path", "models/nomic-embed-text-v1.5.Q4_K_M.gguf")
        except:
            model_path = "models/nomic-embed-text-v1.5.Q4_K_M.gguf"
        
        if not os.path.isabs(model_path):
            model_path = os.path.abspath(os.path.join(os.path.dirname(__file__), model_path))
            
        GLOBAL_EMBEDDING_CLIENT = EmbeddingClient(model_path)
    return GLOBAL_EMBEDDING_CLIENT

def simple_text_to_vector(text: str) -> list:
    """使用llama.cpp Embedding模型生成语义向量"""
    client = get_embedding_client()
    return client.get_embedding(text)

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
    
    def get_pet_detail(self, name: str) -> dict:
        if not name or not self.pets:
            return {}
        for p in self.pets:
            if p.get("name") == name:
                return p
        return {}
    
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
                        "type_cn": skill.get("type_cn", ""),  # 直接从数据库取中文名
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

class ConnectionAdapter:
    def __init__(self):
        self.is_connected = True
        self.model_id = ""

    def connect(self): pass

    def disconnect(self):
        self.is_connected = False

    def send(self, history_messages, current_prompt, image_base64,
             use_text_only, response_format, max_tokens, temperature, proxy):
        raise NotImplementedError


class OllamaAdapter(ConnectionAdapter):
    def __init__(self, base_url, model_id, no_think=True):
        super().__init__()
        self.base_url = base_url.rstrip("/")
        self.model_id = model_id
        self.no_think = no_think
        self.chat_url = f"{self.base_url}/api/chat"

    def connect(self):
        print(f"  [Ollama] 正在预热模型 {self.model_id}，首次加载可能需要 30-60 秒...", flush=True)
        try:
            payload = {
                "model": self.model_id,
                "messages": [{"role": "user", "content": "hi"}],
                "stream": False, "keep_alive": -1,
                "options": {"num_predict": 1}
            }
            start = time.time()
            resp = requests.post(self.chat_url, json=payload, timeout=120)
            elapsed = time.time() - start
            if resp.status_code == 200:
                print(f"  [Ollama] 模型预热完成，已常驻内存 | 耗时: {elapsed:.1f}s", flush=True)
                self.is_connected = True
            else:
                print(f"  [Ollama] 预热返回 HTTP {resp.status_code}，将在首次对战时重试。", flush=True)
        except Exception as e:
            print(f"  [Ollama] 预热失败（{e}），将在首次对战时重试。", flush=True)

    def send(self, history_messages, current_prompt, image_base64,
             use_text_only, response_format, max_tokens, temperature, proxy):
        try:
            content = current_prompt
            if self.no_think:
                content = "/no_think\n" + current_prompt

            messages = list(history_messages)

            if not use_text_only and image_base64:
                payload_size_kb = len(image_base64) / 1024
                print(f"  [监测] 图像 Payload 体积: {payload_size_kb:.1f} KB", flush=True)
                messages.append({"role": "user", "content": content, "images": [image_base64]})
            else:
                print(f"  [LLM] 纯文本模式 | 提示词长度: {len(current_prompt)} 字符", flush=True)
                messages.append({"role": "user", "content": content})

            payload = {
                "model": self.model_id,
                "messages": messages,
                "stream": False,
                "keep_alive": -1,
                "options": {"temperature": temperature, "top_p": 0.85, "num_predict": max_tokens}
            }

            if response_format == "json":
                payload["format"] = "json"

            start_t = time.time()
            print(f"  [LLM] 正在通过 Ollama {self.model_id} 进行决策请求...", flush=True)
            response = requests.post(self.chat_url, json=payload, timeout=60, proxies=None)
            latency = time.time() - start_t

            if response.status_code != 200:
                print(f"  [Ollama 错误] HTTP {response.status_code} | 耗时 {latency:.2f}s")
                try: print(f"  [错误详情]: {response.json()}")
                except: print(f"  [响应内容]: {response.text[:500]}")
                return None

            result = response.json()
            msg = result.get("message", {})
            raw_text = msg.get("content", "")
            thinking_text = msg.get("thinking", "")

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


class GeminiAdapter(ConnectionAdapter):
    def __init__(self, api_key, model_id):
        super().__init__()
        self.api_key = api_key
        self.model_id = model_id
        self.url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent?key={api_key}"

    def send(self, history_messages, current_prompt, image_base64,
             use_text_only, response_format, max_tokens, temperature, proxy):
        try:
            contents = []
            for msg in history_messages:
                role = "user" if msg["role"] == "user" else "model"
                contents.append({"role": role, "parts": [{"text": msg["content"]}]})

            parts = [{"text": current_prompt}]
            if not use_text_only and image_base64:
                payload_size_kb = len(image_base64) / 1024
                print(f"  [监测] 图像 Payload 体积: {payload_size_kb:.1f} KB", flush=True)
                parts.append({"inline_data": {"mime_type": "image/jpeg", "data": image_base64}})
            else:
                print(f"  [LLM] 纯文本模式 | 提示词长度: {len(current_prompt)} 字符", flush=True)

            contents.append({"role": "user", "parts": parts})
            payload = {"contents": contents}
            gen_config = {"maxOutputTokens": max_tokens, "temperature": temperature}
            if response_format == "json":
                json_supported = ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash"]
                if any(m in self.model_id for m in json_supported):
                    gen_config["responseMimeType"] = "application/json"
                else:
                    print(f"  [Gemini] 模型 {self.model_id} 不支持JSON mode，使用文本模式", flush=True)
            payload["generationConfig"] = gen_config

            headers = {"Content-Type": "application/json"}
            proxies = {"http": proxy, "https": proxy} if proxy else None
            start_t = time.time()
            print(f"  [LLM] 正在通过 {self.model_id} 进行决策请求...", flush=True)
            response = requests.post(self.url, headers=headers, json=payload, timeout=60, proxies=proxies)
            latency = time.time() - start_t

            if response.status_code != 200:
                print(f"  [Gemini 错误] HTTP {response.status_code} | 耗时 {latency:.2f}s")
                try: print(f"  [错误详情]: {response.json()}")
                except: print(f"  [响应内容]: {response.text[:300]}")
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


class OpenAIAdapter(ConnectionAdapter):
    def __init__(self, api_key, model_id, base_url, rate_limit_retry=False):
        super().__init__()
        self.api_key = api_key
        self.model_id = model_id
        self.base_url = base_url.rstrip("/")
        self.url = f"{self.base_url}/chat/completions"
        self.rate_limit_retry = rate_limit_retry

    def send(self, history_messages, current_prompt, image_base64,
             use_text_only, response_format, max_tokens, temperature, proxy):
        try:
            headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
            messages = list(history_messages)

            if not use_text_only and image_base64:
                payload_size_kb = len(image_base64) / 1024
                print(f"  [监测] 图像 Payload 体积：{payload_size_kb:.1f} KB", flush=True)
                image_data_uri = f"data:image/jpeg;base64,{image_base64}"
                content = [
                    {"type": "image_url", "image_url": {"url": image_data_uri}},
                    {"type": "text", "text": current_prompt}
                ]
            else:
                content = current_prompt
                print(f"  [LLM] 纯文本模式 | 提示词长度: {len(current_prompt)} 字符", flush=True)

            messages.append({"role": "user", "content": content})
            payload = {
                "model": self.model_id,
                "messages": messages,
                "stream": False,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }

            if response_format == "json":
                payload["response_format"] = {"type": "json_object"}

            proxies = {"http": proxy, "https": proxy} if proxy else None
            start_t = time.time()
            print(f"  [LLM] 正在通过 {self.model_id} 进行决策请求...", flush=True)
            response = requests.post(self.url, headers=headers, json=payload, timeout=60, proxies=proxies)
            latency = time.time() - start_t

            if self.rate_limit_retry and response.status_code == 429:
                print(f"  [限流] 请求过于频繁，等待 60 秒后重试...")
                time.sleep(60)
                return self.send(history_messages, current_prompt, image_base64,
                               use_text_only, response_format, max_tokens, temperature, proxy)

            if response.status_code != 200:
                print(f"  [HTTP错误] {response.status_code} | 耗时 {latency:.2f}s")
                try: print(f"  [错误详情]: {response.json()}")
                except: print(f"  [响应内容]: {response.text[:200]}")
                return None

            result = response.json()
            choices = result.get("choices", [])
            if choices:
                raw_text = choices[0].get("message", {}).get("content", "")
                print(f"  [AI 原始回执]: \"{raw_text.strip()}\" (耗时: {latency:.2f}s)", flush=True)
                return raw_text
            return None
        except Exception as e:
            print(f"  [通讯异常] {str(e)}")
            return None


class SparkWSAdapter(ConnectionAdapter):
    def __init__(self, app_id, api_key, api_secret, spark_url, domain="spark-x"):
        super().__init__()
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
        self.current_max_tokens = 4096
        self.current_temperature = 0.5
        self.ws = None
        self.is_connected = False
        self._is_connecting = False
        self._threads = []

    def connect(self):
        if self.is_connected or self._is_connecting: return
        self._is_connecting = True
        ws_url = self._create_url()
        self.ws = websocket.WebSocketApp(ws_url, on_message=self._on_message,
                                          on_error=self._on_error,
                                          on_close=self._on_close,
                                          on_open=self._on_open)
        t = threading.Thread(target=self.ws.run_forever,
                            kwargs={"sslopt": {"cert_reqs": ssl.CERT_NONE}, "ping_interval": 5},
                            daemon=True)
        self._threads.append(t)
        t.start()

    def disconnect(self):
        self.is_connected = False
        if self.ws:
            try: self.ws.close()
            except: pass
            self.ws = None
        self.response_done.set()
        self.prompt_ready.set()

    def _create_url(self):
        now = datetime.now()
        date = format_date_time(mktime(now.timetuple()))
        signature_origin = f"host: {self.host}\ndate: {date}\nGET {self.path} HTTP/1.1"
        signature_sha = hmac.new(self.api_secret.encode('utf-8'), signature_origin.encode('utf-8'), digestmod=hashlib.sha256).digest()
        signature_sha_base64 = base64.b64encode(signature_sha).decode(encoding='utf-8')
        authorization_origin = f'api_key="{self.api_key}", algorithm="hmac-sha256", headers="host date request-line", signature="{signature_sha_base64}"'
        authorization = base64.b64encode(authorization_origin.encode('utf-8')).decode(encoding='utf-8')
        v = {"authorization": authorization, "date": date, "host": self.host}
        return self.spark_url + '?' + urllib.parse.urlencode(v)

    def _on_message(self, ws, message):
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

    def _on_error(self, ws, error):
        self.is_connected = False
        self.response_done.set()

    def _on_close(self, ws, status, msg):
        self.is_connected = False

    def _on_open(self, ws):
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
                        "parameter": {"chat": {"domain": self.domain, "max_tokens": self.current_max_tokens, "temperature": self.current_temperature}},
                        "payload": {"message": {"text": content_list}}
                    }
                    ws.send(json.dumps(data))
                    self.prompt_ready.clear()
        t = threading.Thread(target=run_thread, daemon=True)
        self._threads.append(t)
        t.start()

    def send(self, history_messages, current_prompt, image_base64,
             use_text_only, response_format, max_tokens, temperature, proxy):
        if not self.is_connected:
            self.connect()
            wait_st = time.time()
            while not self.is_connected and time.time() - wait_st < 5: time.sleep(0.1)
        if not self.is_connected: return None
        self.answer = ""
        self.current_prompt = current_prompt
        self.current_image_base64 = image_base64 if not use_text_only else None
        self.current_max_tokens = max_tokens
        self.current_temperature = temperature
        self.response_done.clear()
        self.prompt_ready.set()
        return self.answer if self.response_done.wait(timeout=30) else None


class AIClient:
    def __init__(self, adapter, proxy=None, use_text_only=True,
                 response_format=None, context_limit=4096, max_tokens=4096, temperature=0.5):
        self.adapter = adapter
        self.model_id = adapter.model_id
        self.proxy = proxy
        self.use_text_only = use_text_only
        self.response_format = response_format
        self.context_limit = context_limit
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.battle_records = []

    @property
    def is_connected(self):
        return self.adapter.is_connected

    def connect(self):
        self.adapter.connect()

    def disconnect(self):
        self.adapter.disconnect()

    def add_battle_record(self, state_summary, action, reason):
        self.battle_records.append({
            "state": state_summary,
            "action": action,
            "reason": reason,
            "timestamp": time.time()
        })

    def _estimate_tokens(self, text):
        return max(1, len(text) // 2)

    def _build_history_messages(self):
        if not self.battle_records:
            return []
        messages = []
        remaining = self.context_limit
        for record in reversed(self.battle_records):
            user_text = f"【历史对战】{record['state']}"
            asst_text = f"{record['action']} | {record['reason']}"
            tokens = self._estimate_tokens(user_text) + self._estimate_tokens(asst_text)
            if tokens > remaining:
                break
            messages.insert(0, {"role": "assistant", "content": asst_text})
            messages.insert(0, {"role": "user", "content": user_text})
            remaining -= tokens
        return messages

    def ask_vlm(self, prompt, image_base64=None):
        history = self._build_history_messages()
        return self.adapter.send(
            history_messages=history,
            current_prompt=prompt,
            image_base64=image_base64,
            use_text_only=self.use_text_only,
            response_format=self.response_format,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            proxy=self.proxy
        )


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
        
        # 是否使用AI决策（false则使用纯规则决策）
        # 注意：此值由 init_ai_client() 从配置文件中读取并设置，不要在这里硬编码覆盖
        # self.use_ai = True
        # 战斗状态追踪（用于检测战斗结束）
        self._in_battle = False
        
        # 状态记忆与冷却追踪
        self.state_tracker = {
            "enemy_skills_used": [],  # 敌方使用过的技能 [{"name": "...", "turn": 1}]
            "enemy_hp_history": [],   # 敌方血量历史 [(hp_value, timestamp)]
            "my_hp_history": [],      # 我方血量历史
            "turn_count": 0,          # 回合计数
            "last_enemy_pet": None,   # 上回合敌方宠物
            "last_enemy_hp_str": "未知", # 上回合敌方血量字符串
            "skill_cooldowns": {}     # 技能冷却追踪 {"skill_name": available_turn}
        }

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
            use_text_only = c.get("use_text_only", True)
            response_format = c.get("response_format", None)
            context_limit = c.get("context_limit", 4096)
            max_tokens = c.get("max_tokens", 4096)
            temperature = c.get("temperature", 0.5)
            use_ai = c.get("use_ai", True)
            self.use_ai = use_ai
            
            adapter = None
            if engine == "ollama":
                base_url = c.get("ollama_base_url", "http://127.0.0.1:11434")
                model_id = c.get("ollama_model_id", "qwen3.5:4b")
                no_think = c.get("ollama_no_think", True)
                adapter = OllamaAdapter(base_url, model_id, no_think)
            elif engine == "gemini":
                api_key = c.get("gemini_apikey")
                model_id = c.get("gemini_model_id", "gemini-2.5-flash")
                if api_key:
                    adapter = GeminiAdapter(api_key, model_id)
            elif engine == "doubao":
                api_key = c.get("doubao_api_key")
                model_id = c.get("doubao_model_id")
                base_url = c.get("doubao_base_url", "https://ark.cn-beijing.volces.com/api/v3")
                if api_key and model_id:
                    adapter = OpenAIAdapter(api_key, model_id, base_url)
            elif engine == "spark_maas":
                api_key = c.get("spark_maas_apikey")
                model_id = c.get("spark_maas_model_id")
                base_url = c.get("spark_maas_base_url", "https://maas-api.cn-huabei-1.xf-yun.com/v2")
                if api_key and model_id:
                    adapter = OpenAIAdapter(api_key, model_id, base_url, rate_limit_retry=True)
            elif engine == "spark_ws":
                app_id = c.get("spark_appid")
                api_key = c.get("spark_apikey")
                api_secret = c.get("spark_apisecret")
                spark_url = c.get("spark_url", "wss://spark-api.xf-yun.com/x2")
                if app_id and api_key and api_secret:
                    adapter = SparkWSAdapter(app_id, api_key, api_secret, spark_url)
            else:
                app_id = c.get("spark_appid")
                api_key = c.get("spark_apikey")
                api_secret = c.get("spark_apisecret")
                spark_url = c.get("spark_url", "wss://spark-api.xf-yun.com/x2")
                if app_id and api_key and api_secret:
                    adapter = SparkWSAdapter(app_id, api_key, api_secret, spark_url)
            
            if not adapter:
                print(f"  [系统] AI 适配器创建失败：缺少配置参数", flush=True)
                return None
            
            client = AIClient(
                adapter=adapter,
                proxy=proxy,
                use_text_only=use_text_only,
                response_format=response_format,
                context_limit=context_limit,
                max_tokens=max_tokens,
                temperature=temperature
            )
            adapter.connect()
            print(f"  [系统] AI 核心单例化成功：{adapter.model_id} (引擎={engine}, 纯文本={use_text_only}, 格式={response_format}, 上下文={context_limit})", flush=True)
            return client
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
                    elif "逃跑" in txt or "倒计时" in txt or "技能" in txt or "更换" in txt or "捕捉" in txt: found_battle = True
                    elif "大世界小队" in txt or "大世界" in txt or "小队" in txt: found_team_ui = True

            if found_battle:
                self._in_battle = True
                return self.run_vlm_battle(context, image)
            
            # 检测战斗结束：之前战斗中，现在检测到大世界UI特征
            if self._in_battle:
                # 检查大世界特征：左下角Enter/I/K按钮、右上角地图、左上角精灵头像
                ocr_boxes = res.all_results if (res and res.hit) else []
                is_world = self._detect_world_ui(image, h, w, ocr_boxes)
                if is_world:
                    print("  [战斗结束] 检测到大世界界面，重置对战历史...")
                    self._in_battle = False
                    if self.ai_client:
                        self.ai_client.battle_records.clear()
                        print(f"  [历史重置] 已清空 {len(self.ai_client.battle_records)} 条对战记录")
                    self.state_tracker = {
                        "enemy_skills_used": [],
                        "enemy_hp_history": [],
                        "my_hp_history": [],
                        "turn_count": 0,
                        "last_enemy_pet": None,
                        "last_enemy_hp_str": "未知",
                        "skill_cooldowns": {}
                    }
                    return True
            
            # 队伍状态检测
            if not self.team_list:
                if found_team_ui:
                    print("  [系统] 捕获到团队排布界面，正在建立大世界小队名册...")
                    self.parse_team_ui(context, image)
                    print(f"  [队伍] 解析完毕 (共{len(self.team_list)}只): {[p['name'] for p in self.team_list]}")
                    context.tasker.controller.post_press_key(27).wait()
                    time.sleep(2)
                    return True
                else:
                    now = time.time()
                    if now - self.last_team_req > 8:
                        print("  [系统] 当前小队名册为空 (非战态)，按下 `~` 键请求侦察...")
                        context.tasker.controller.post_press_key(192).wait()
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
        "normal": [],
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
        def parse_power(p):
            try:
                return int(p) if p is not None else 0
            except (ValueError, TypeError):
                return 0
        high_power_skills = [s for s in skills if parse_power(s.get('power', 0)) > 80 and s.get('name') != '未知']
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
        # 分区进行 OCR，避免宽幅图像导致漏识别，并处理名字和血量粘连的情况
        
        # 左侧处理 (我方)
        left_crop = image[0:int(h*0.35), 0:int(w*0.5)]
        left_enl = cv2.resize(left_crop, None, fx=2.5, fy=2.5, interpolation=cv2.INTER_CUBIC)
        ocr_res_left = context.run_recognition('TempOCR_L', left_enl, pipeline_override={'TempOCR_L': {'recognition': 'OCR', 'roi': [0, 0, left_enl.shape[1], left_enl.shape[0]]}})
        
        if ocr_res_left and ocr_res_left.hit:
            for res_box in ocr_res_left.all_results:
                txt = res_box.text
                
                hp_match = re.search(r'(?<![★P])(\d+)/(\d+)', txt)
                if hp_match:
                    my_hp = hp_match.group(0)
                
                hit = self.rag_db.search_pet_by_name(txt, limit=1)
                if hit:
                    my_pet_raw, my_pet_rag = txt, hit[0]['name']

        # 右侧处理 (敌方)
        right_crop = image[0:int(h*0.35), int(w*0.5):w]
        right_enl = cv2.resize(right_crop, None, fx=2.5, fy=2.5, interpolation=cv2.INTER_CUBIC)
        ocr_res_right = context.run_recognition('TempOCR_R', right_enl, pipeline_override={'TempOCR_R': {'recognition': 'OCR', 'roi': [0, 0, right_enl.shape[1], right_enl.shape[0]]}})

        if ocr_res_right and ocr_res_right.hit:
            for res_box in ocr_res_right.all_results:
                txt = res_box.text
                
                hp_match = re.search(r'(?<![★P])(\d+)/(\d+)', txt)
                percent_match = re.search(r'(\d+)%', txt)
                if hp_match:
                    enemy_hp = hp_match.group(0)
                elif percent_match:
                    enemy_hp = percent_match.group(0)
                    print(f"      [DEBUG] 敌方百分比血量: {enemy_hp}")
                
                hit = self.rag_db.search_pet_by_name(txt, limit=1)
                if hit:
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

        # 3. 物理槽位锚定感知 (Slot-based Anchoring)
        # 将左侧区域划分为 4 个垂直区间，确保位置与指令 (1, 2, 3, 4) 绝对锁定
        roi_y_start = int(h * 0.22) # 略微上移以包含槽位1的顶部
        roi_x0 = 0
        roi_x1 = int(w * 0.35)
        skill_crop = image[roi_y_start:h, roi_x0:roi_x1]
        
        # 提升清晰度
        skill_enl = cv2.resize(skill_crop, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
        skill_res = context.run_recognition('TempOCR', skill_enl, pipeline_override={'TempOCR': {'recognition': 'OCR', 'roi': [0, 0, skill_enl.shape[1], skill_enl.shape[0]]}})
        
        # 定义 4 个物理槽位的 Y 坐标区间 (基于 1080p 的相对比例映射)
        # 槽位高度约 95px
        slots_data = [
            {"y_range": (0, 335), "skill": None, "energy": None, "cd": None},   # Slot 1
            {"y_range": (335, 435), "skill": None, "energy": None, "cd": None}, # Slot 2
            {"y_range": (435, 530), "skill": None, "energy": None, "cd": None}, # Slot 3
            {"y_range": (530, 999), "skill": None, "energy": None, "cd": None}, # Slot 4
        ]

        if skill_res and skill_res.hit:
            for b in skill_res.all_results:
                txt = b.text.strip()
                if not txt: continue
                
                # 坐标映射回主区域 (除以缩放系数 2.0)
                abs_y = roi_y_start + (b.box[1] + b.box[3]/2) / 2.0
                
                # 判定所属槽位
                target_slot = None
                for i, slot in enumerate(slots_data):
                    if slot["y_range"][0] <= abs_y < slot["y_range"][1]:
                        target_slot = slot
                        break
                
                if not target_slot: continue

                # 识别逻辑
                if re.fullmatch(r'[1-9]', txt):
                    # 采样背景判定冷却
                    bx, by, bw, bh = b.box
                    cx, cy = int((bx + bw/2)/2.0), int((by + bh/2)/2.0)
                    is_cd = False
                    if 0 <= cy < skill_crop.shape[0] and 0 <= cx < skill_crop.shape[1]:
                        pixel = skill_crop[cy, cx] # BGR
                        if pixel[2] > 140 and pixel[1] < 100 and pixel[0] < 100:
                            is_cd = True
                    
                    if is_cd:
                        target_slot["cd"] = int(txt)
                    else:
                        target_slot["energy"] = int(txt)
                else:
                    # 匹配技能名
                    s_hits = self.rag_db.search_skill_by_name(txt, limit=1)
                    if s_hits:
                        target_slot["skill"] = s_hits[0]

        # 构建最终技能列表 (严格保持 4 个位置)
        skills = []
        for i, data in enumerate(slots_data):
            if data["skill"]:
                skill_entry = dict(data["skill"])
                # 属性注入
                skill_entry['energy_cost'] = data["energy"] if data["energy"] else skill_entry.get('energy_cost')
                skill_entry['cooldown'] = data["cd"]
                skills.append(skill_entry)
                print(f"      [DEBUG] 槽位{i+1}: {skill_entry['name']} (Energy:{skill_entry['energy_cost']} CD:{skill_entry['cooldown']})")
            else:
                # 占位符，防止后续技能顶替位置
                skills.append({
                    "name": "未知技能", 
                    "power": "0", 
                    "type": "未知", 
                    "effect": "未识别到该槽位技能名",
                    "energy_cost": data["energy"],
                    "cooldown": data["cd"]
                })
                print(f"      [DEBUG] 槽位{i+1}: 未知")
        
        # 如果识别到超过4个技能，只保留前4个（按Y坐标排序后的）
        skills = skills[:4]
        
        while len(skills) < 4:
            skills.append({"name": "未知", "type": "未知", "power": 0, "effect": "未知", "energy_cost": None})

        print(f"  [空间隔离感知结果]")
        print(f"    我方: {my_pet_rag} (HP:{my_hp}) | 敌方: {enemy_pet_rag} (HP:{enemy_hp}) | 能量:{energy_text}")
        for i, s in enumerate(skills, 1):
            ec = f" ★{s['energy_cost']}" if s.get('energy_cost') is not None else ""
            print(f"    槽位{i}: {s['name']}{ec}")

        # ==========================================
        # 换宠界面检测：全部技能为未知 → 当前展示的是换宠面板
        # 识别各槽位血量 → 构建换宠提示词 → 调用 AI 决策
        # ==========================================
        all_skills_unknown = all(s["name"] in ("未知", "未知技能") for s in skills)
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

                # 统计 HP 条像素（支持绿色、黄色、红色）：
                # BGR 格式：绿色 (G>100, R<150, B<150), 黄色 (G>150, R>150, B<100), 红色 (R>150, G<100, B<100)
                bar_bgr = bar_crop
                hp_mask = (
                    # 绿色
                    ((bar_bgr[:, :, 1].astype(int) > 100) & (bar_bgr[:, :, 2].astype(int) < 150) & (bar_bgr[:, :, 0].astype(int) < 150)) |
                    # 黄色
                    ((bar_bgr[:, :, 1].astype(int) > 150) & (bar_bgr[:, :, 2].astype(int) > 150) & (bar_bgr[:, :, 0].astype(int) < 100)) |
                    # 红色
                    ((bar_bgr[:, :, 2].astype(int) > 150) & (bar_bgr[:, :, 1].astype(int) < 100) & (bar_bgr[:, :, 0].astype(int) < 100))
                )
                hp_cols = int(np.any(hp_mask, axis=0).sum())
                hp_pct = int(hp_cols / max(bar_width_ref, 1) * 100)
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
                    db_data = self.rag_db.get_pet_detail(pet_name)
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

            # --- 提取敌方情报用于换宠决策 ---
            enemy_db_data = self.rag_db.get_pet_detail(enemy_pet_rag)
            enemy_type_str = "未知"
            enemy_weak_str = ""
            if enemy_db_data:
                enemy_type_cn = TYPE_EN_TO_CN.get(enemy_db_data.get("type", ""), enemy_db_data.get("type", ""))
                enemy_sec_type = enemy_db_data.get("secondary_type")
                enemy_sec_cn = TYPE_EN_TO_CN.get(enemy_sec_type, enemy_sec_type) if enemy_sec_type else None
                enemy_type_str = f"{enemy_type_cn}" + (f"/{enemy_sec_cn}" if enemy_sec_cn else "")
                enemy_weaknesses = enemy_db_data.get("weaknesses", {})
                enemy_weak_list = [TYPE_EN_TO_CN.get(t, t) for t in enemy_weaknesses.get("weak_to", [])]
                if enemy_weak_list:
                    enemy_weak_str = f" | 弱点:{','.join(enemy_weak_list)}"

            switch_prompt = f"""你是洛克王国对战助手，当前需要选择替换上场的精灵。

【当前战场】
敌方精灵: {enemy_pet_rag} (属性: {enemy_type_str}{enemy_weak_str}) (HP: {enemy_hp})
当前上场: {my_pet_rag} (HP: {my_hp})

【可选择的精灵】（按槽位1-5）
{chr(10).join(slot_lines)}

【决策要求】
1. 只能选择 HP≥5% 且未标注【当前上场】或【HP耗尽】的精灵
2. 请仔细比对敌方的属性弱点与我方队伍的属性，优先选择能够克制敌方的精灵上场
3. 第一行只输出槽位数字（{"/".join(str(s) for s in available_slots)} 中的一个）
4. 第二行输出换宠理由（请简要说明属性克制关系，一句话）

请输出你的决策："""

            print(f"\n[换宠决策提示词]:\n{switch_prompt}")

            if not self.ai_client or not self.use_ai:
                print("  [规则模式] 使用属性克制策略进行换宠决策...")
                enemy_type = self._get_pet_type(enemy_pet_rag)
                best_slot = self._find_best_switch(enemy_type, my_pet_rag)
                
                if best_slot and best_slot in available_slots:
                    target_slot = best_slot
                    print(f"  >>> [换宠决策] 规则选择槽位 {target_slot} (属性优势)")
                else:
                    target_slot = available_slots[0] if available_slots else 1
                    print(f"  >>> [换宠决策] 规则选择槽位 {target_slot} (首个可用)")
                
                context.tasker.controller.post_press_key(48 + target_slot).wait()
                time.sleep(0.2)
                context.tasker.controller.post_press_key(32).wait()
                self._last_decision_time = now
                time.sleep(3)
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
                    context.tasker.controller.post_press_key(32).wait()
                else:
                    fallback = available_slots[0] if available_slots else 1
                    print(f"  [换宠] AI 输出无法解析，选择可用槽位 {fallback}")
                    context.tasker.controller.post_press_key(48 + fallback).wait()
                    time.sleep(0.2)
                    context.tasker.controller.post_press_key(32).wait()
            else:
                fallback = available_slots[0] if available_slots else 1
                print(f"  [换宠] AI 无响应，选择可用槽位 {fallback}")
                context.tasker.controller.post_press_key(48 + fallback).wait()
                time.sleep(0.2)
                context.tasker.controller.post_press_key(32).wait()

            time.sleep(3)
            return True

        # 更新状态追踪器
        self._update_state_tracker(my_pet_rag, my_hp, enemy_pet_rag, enemy_hp, skills)
        
        # 提取属性类型和能量（供后续决策和兜底使用）
        my_type = self._get_pet_type(my_pet_rag)
        enemy_type = self._get_pet_type(enemy_pet_rag)
        current_energy = None
        energy_match = re.search(r'(\d+)\s*/\s*\d+', energy_text)
        if energy_match:
            current_energy = int(energy_match.group(1))
        
        # 决策冷却检查
        now = time.time()
        if now - self._last_decision_time < self._decision_cooldown:
            remaining = self._decision_cooldown - (now - self._last_decision_time)
            print(f"  [决策冷却] 等待 {remaining:.1f} 秒后再次决策...")
            return True
        
        # 解析血量百分比供规则决策使用
        my_hp_pct = None
        enemy_hp_pct = None
        try:
            if my_hp and '/' in my_hp:
                parts = my_hp.split('/')
                my_hp_pct = int(parts[0]) / int(parts[1]) * 100
            if enemy_hp and '/' in enemy_hp:
                parts = enemy_hp.split('/')
                enemy_hp_pct = int(parts[0]) / int(parts[1]) * 100
            elif enemy_hp and '%' in enemy_hp:
                enemy_hp_pct = float(enemy_hp.replace('%', ''))
        except:
            pass
        
        final_cmd = None
        reason = ""
        
        # === 纯规则决策模式 ===
        if not self.use_ai:
            print("  [规则模式] 使用属性克制+能量管理策略决策...")
            final_cmd, reason = self._rule_based_decision(
                skills, my_type, enemy_type, current_energy,
                my_hp_pct, enemy_hp_pct, my_pet_rag, enemy_pet_rag
            )
            if final_cmd:
                print(f"  [规则决策] {final_cmd} | 理由: {reason}")
            else:
                print("  [规则决策] 无可用决策，回退到启发式兜底")
                final_cmd = self._heuristic_fallback(skills, my_type, enemy_type, current_energy)
                reason = "启发式兜底"
        
        # === AI决策模式 ===
        else:
            # RAG 管线：语义化 -> Embedding -> LanceDB 检索 -> 拼接提示词
            pipeline_start = time.time()
            semantic_start = time.time()
            scenario_text, action_text = self.semanticize_state(my_pet_rag, my_hp, enemy_pet_rag, enemy_hp, skills)
            semantic_cost = time.time() - semantic_start
            
            retrieval_start = time.time()
            intel_query = f"{my_pet_rag}的专属作战策略"
            raw_intel = self.query_battle_intel(intel_query, "", top_k=3)
            intel_list = []
            for item in raw_intel:
                if my_pet_rag in item['scenario'] or item.get('category') == "宠物策略":
                    intel_list.append(item)
            retrieval_cost = time.time() - retrieval_start
            
            intel_text = self.format_intel_for_prompt(intel_list)
            prompt = self.build_battle_prompt(my_pet_rag, my_hp, enemy_pet_rag, enemy_hp, skills, intel_text, energy_text)
            pipeline_cost = time.time() - pipeline_start
            
            print(f"\n[召回管线] 语义化: {semantic_cost*1000:.1f}ms | 检索: {retrieval_cost*1000:.1f}ms | 总耗时: {pipeline_cost*1000:.1f}ms")
            if intel_list:
                print(f"[召回管线] 命中 {len(intel_list)} 条战术情报:")
                for intel in intel_list:
                    print(f"  - [{intel['category']}] {intel['scenario'][:40]}...")
            else:
                lancedb_status = '就绪' if self._lance_db_initialized else '未就绪'
                print(f"[召回管线] 未命中战术情报 (LanceDB: {lancedb_status})")
            
            print("\n" + "="*60)
            print(f"[VLM 提示词]:\n{prompt}")
            print("="*60 + "\n")
            
            target_w = 768
            if w > target_w:
                scale = target_w / w
                image = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
            image = cv2.copyMakeBorder(image, 10, 10, 10, 10, cv2.BORDER_CONSTANT, value=[255, 255, 255])
            _, buffer = cv2.imencode('.jpg', image, [int(cv2.IMWRITE_JPEG_QUALITY), 50])
            img_base64 = base64.b64encode(buffer).decode('utf-8')
            
            if not self.ai_client:
                print("  [决策失败] AI 客户端未初始化，回退到规则决策...")
                final_cmd, reason = self._rule_based_decision(
                    skills, my_type, enemy_type, current_energy,
                    my_hp_pct, enemy_hp_pct, my_pet_rag, enemy_pet_rag
                )
                if not final_cmd:
                    final_cmd = self._heuristic_fallback(skills, my_type, enemy_type, current_energy)
                    reason = "启发式兜底"
            else:
                decision = self.ai_client.ask_vlm(prompt, img_base64)
                if not decision:
                    print("  [决策失败] AI 无响应，启用规则决策...")
                    final_cmd, reason = self._rule_based_decision(
                        skills, my_type, enemy_type, current_energy,
                        my_hp_pct, enemy_hp_pct, my_pet_rag, enemy_pet_rag
                    )
                    if not final_cmd:
                        final_cmd = self._heuristic_fallback(skills, my_type, enemy_type, current_energy)
                        reason = "启发式兜底"
                else:
                    # 解析AI输出
                    reason = "未提供理由"
                    is_json_format = hasattr(self.ai_client, 'response_format') and self.ai_client.response_format == "json"
                    
                    if is_json_format:
                        try:
                            json_match = re.search(r'\{[^}]*\}', decision)
                            if json_match:
                                json_str = json_match.group(0)
                                parsed = json.loads(json_str)
                                final_cmd = parsed.get("action", "").strip().upper()
                                reason = parsed.get("reason", "未提供理由")
                                print(f"  [JSON解析] action={final_cmd}, reason={reason}")
                        except Exception as e:
                            print(f"  [JSON解析失败] {e}，回退到文本解析")
                    
                    if not final_cmd:
                        lines = decision.strip().split('\n')
                        if len(lines) >= 2:
                            reason = lines[1].strip()
                        decision_upper = decision.upper()
                        first_line = decision_upper.split('\n')[0].strip()
                        match = re.search(r'^([1234XE][1-6]?)$', first_line)
                        if not match:
                            match = re.search(r'(?<![A-Z0-9])([1234XE][1-6]?)(?![A-Z0-9])', decision_upper)
                        if not match:
                            match = re.search(r'([1234XE][1-6]?)', decision_upper)
                        if match:
                            final_cmd = match.group(1)
        
        self._last_decision_time = now
        
        if final_cmd and self.ai_client and self.use_ai:
            state_summary = f"我方:{my_pet_rag}(HP:{my_hp}) 敌方:{enemy_pet_rag}(HP:{enemy_hp})"
            self.ai_client.add_battle_record(state_summary, final_cmd, reason)
        
        if not final_cmd:
            print("  [决策失败] 无法提取有效指令")
            return True
        
        action_map = {"1": 49, "2": 50, "3": 51, "4": 52, "X": 88, "E": 69}
        
        print(f"  >>> 决策(提取): {final_cmd}", flush=True)
        if final_cmd.startswith('E') and len(final_cmd) == 2:
            key1 = 69
            key2 = 48 + int(final_cmd[1])
            context.tasker.controller.post_press_key(key1).wait()
            time.sleep(1)
            context.tasker.controller.post_press_key(key2).wait()
            print(f"  >>> [指令注入] 组合技注入成功 -> 换宠序列 E -> {final_cmd[1]}")
        else:
            key_code = action_map.get(final_cmd)
            if key_code:
                context.tasker.controller.post_press_key(key_code).wait()
                print(f"  >>> [指令注入] 确认单动作: {final_cmd}")
            else:
                try:
                    vk = int(final_cmd)
                    context.tasker.controller.post_press_key(vk).wait()
                    print(f"  >>> [指令注入] 直接VK注入: {vk}")
                except:
                    print(f"  >>> [指令注入] 无法映射指令: {final_cmd}")
        
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
            cd = skill.get('cooldown')
            
            # 可用性判定：必须能量足够 且 不在冷却中
            if cd and cd > 0:
                castable = f"✗冷却中({cd}回合)"
            elif ec is not None:
                castable = "✓可用" if (current_energy is None or current_energy >= ec) else "✗能量不足"
            else:
                castable = "✓可用"
                
            energy_str = f" | 状态:{castable}"
            if ec is not None:
                energy_str = f" | 能耗:★{ec}{energy_str}"
            
            # 属性转换：优先用数据库中的 type_cn，否则查表
            s_type_cn = skill.get('type_cn')
            raw_type = str(skill.get('type', '未知')).strip().lower()
            if not s_type_cn or s_type_cn == "":
                s_type_cn = TYPE_EN_TO_CN.get(raw_type, raw_type)
            
            skills_info += f"  [{i}] {skill['name']} - 威力:{skill['power']} | 类型:{s_type_cn} | 效果:{skill['effect']}{energy_str}\n"

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
                # 兼容性转换
                p_type_raw = str(p.get('type', '')).strip().lower()
                p_type_cn = TYPE_EN_TO_CN.get(p_type_raw, p_type_raw)
                team_str += f"  [{i}] {p['name']} (类型: {p_type_cn})\n"
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

        # 检查是否使用JSON输出格式
        is_json_format = hasattr(self.ai_client, 'response_format') and self.ai_client.response_format == "json"
        
        if is_json_format:
            prompt += """\n\n【决策要求】
1. 考虑技能威力和效果
2. 参考战术情报
3. 必须在20秒内做出决策
4. 输出格式必须是JSON: {"action": "指令", "reason": "解释"}

示例输出：
{"action": "2", "reason": "敌方血量低，使用高威力技能收割"}

请输出JSON："""
        else:
            prompt += """\n\n【决策要求】
1. 考虑技能威力和效果
2. 参考战术情报
3. 第一行请仅输出一个指令
4. 必须在20秒内做出决策

第一行输出指令，第二行输出解释："""
        
        return prompt

    def _update_state_tracker(self, my_pet, my_hp, enemy_pet, enemy_hp, skills):
        """更新战斗状态追踪器"""
        tracker = self.state_tracker
        tracker["turn_count"] += 1
        current_turn = tracker["turn_count"]
        
        # 解析血量数值
        def parse_hp(hp_str):
            if isinstance(hp_str, str):
                match = re.search(r'(\d+)', hp_str)
                if match:
                    return int(match.group(1))
            return 0
        
        my_hp_val = parse_hp(my_hp)
        enemy_hp_val = parse_hp(enemy_hp)
        
        # 记录血量历史
        tracker["my_hp_history"].append((my_hp_val, time.time()))
        tracker["enemy_hp_history"].append((enemy_hp_val, time.time()))
        
        # 保持历史记录在合理长度
        if len(tracker["my_hp_history"]) > 10:
            tracker["my_hp_history"].pop(0)
        if len(tracker["enemy_hp_history"]) > 10:
            tracker["enemy_hp_history"].pop(0)
        
        # 检测敌方换宠
        if tracker["last_enemy_pet"] and tracker["last_enemy_pet"] != enemy_pet:
            print(f"  [状态追踪] 敌方换宠: {tracker['last_enemy_pet']} -> {enemy_pet}")
            tracker["enemy_skills_used"] = []  # 重置技能记录
        
        tracker["last_enemy_pet"] = enemy_pet
        if enemy_hp != "未知":
            tracker["last_enemy_hp_str"] = enemy_hp
        
        # 更新技能冷却
        for skill in skills:
            skill_name = skill.get("name", "")
            cd = skill.get("cooldown", 0)
            if cd is not None and cd > 0:
                tracker["skill_cooldowns"][skill_name] = current_turn + cd
            elif skill_name in tracker["skill_cooldowns"]:
                if tracker["skill_cooldowns"][skill_name] <= current_turn:
                    del tracker["skill_cooldowns"][skill_name]
    
    def _get_state_memory_text(self) -> str:
        """生成状态记忆文本，用于注入提示词"""
        tracker = self.state_tracker
        if tracker["turn_count"] == 0:
            return ""
        
        memory_parts = []
        
        # 血量变化趋势
        if len(tracker["enemy_hp_history"]) >= 2:
            recent = tracker["enemy_hp_history"][-3:]
            if len(recent) >= 2:
                trend = recent[-1][0] - recent[0][0]
                if trend < -20:
                    memory_parts.append(f"敌方血量大幅下降({trend})，我方攻势有效")
                elif trend > 10:
                    memory_parts.append(f"敌方血量回升({trend})，注意对方可能使用了治疗")
        
        # 技能冷却状态
        current_turn = tracker["turn_count"]
        available_skills = []
        cooling_skills = []
        for skill_name, available_at in tracker["skill_cooldowns"].items():
            if available_at <= current_turn:
                available_skills.append(skill_name)
            else:
                cooling_skills.append(f"{skill_name}({available_at - current_turn}回合)")
        
        if cooling_skills:
            memory_parts.append(f"技能冷却中: {', '.join(cooling_skills)}")
        
        # 敌方技能使用历史
        if tracker["enemy_skills_used"]:
            recent_skills = tracker["enemy_skills_used"][-3:]
            memory_parts.append(f"敌方近期使用技能: {', '.join([s['name'] for s in recent_skills])}")
        
        if memory_parts:
            return "\n【状态记忆】\n" + "\n".join([f"  - {part}" for part in memory_parts])
        return ""

    def _heuristic_fallback(self, skills: list, my_type: str, enemy_type: str, current_energy: int = None) -> str:
        """
        启发式兜底策略：当AI无响应时，基于规则选择最优技能
        优先级：
        1. 先手技能（带有"先手"关键词）
        2. 属性克制且高威力技能
        3. 高威力技能
        4. 能量恢复（X）
        """
        if not skills or len(skills) == 0:
            return "1"  # 最基础的兜底
        
        best_skill_idx = -1
        best_score = -1
        
        for i, skill in enumerate(skills):
            if not skill or skill.get("name") == "未知":
                continue
            
            # 基础分数 = 威力
            power = 0
            try:
                power = int(skill.get("power", 0))
            except:
                power = 0
            
            score = power
            
            # 检查是否先手技能
            effect = skill.get("effect", "")
            if "先手" in effect or "先制" in effect:
                score += 50  # 先手技能加分
            
            # 检查属性克制
            skill_type = skill.get("type", "").lower()
            if my_type and enemy_type:
                # 我方技能类型克制敌方
                if skill_type in self.TYPE_CHART and enemy_type in self.TYPE_CHART.get(skill_type, []):
                    score *= 2  # 克制翻倍
                # 敌方抵抗我方技能
                if enemy_type in self.RESIST_CHART and skill_type in self.RESIST_CHART.get(enemy_type, []):
                    score *= 0.5  # 抵抗减半
            
            # 检查能量是否足够
            energy_cost = skill.get("energy_cost")
            if current_energy is not None and energy_cost is not None:
                if current_energy < energy_cost:
                    score = -1  # 能量不足，排除
            
            # 检查冷却
            cd = skill.get("cooldown", 0)
            if cd and cd > 0:
                score = -1  # 冷却中，排除
            
            if score > best_score:
                best_score = score
                best_skill_idx = i
        
        # 如果找到可用技能，返回对应指令（1-4）
        if best_skill_idx >= 0 and best_score > 0:
            return str(best_skill_idx + 1)
        
        # 如果所有技能都不可用，尝试恢复能量
        if current_energy is not None and current_energy < 5:
            return "X"
        
        # 最终兜底：返回第一个可用技能或1
        for i, skill in enumerate(skills):
            if skill and skill.get("name") != "未知":
                cd = skill.get("cooldown", 0)
                energy_cost = skill.get("energy_cost")
                if (not cd or cd <= 0) and (energy_cost is None or current_energy is None or current_energy >= energy_cost):
                    return str(i + 1)
        
        return "1"

    def _detect_world_ui(self, image: np.ndarray, h: int, w: int, ocr_results: list = None) -> bool:
        """检测大世界界面特征（战斗结束标志）"""
        try:
            # 特征1：左下角 Enter/I/K 按钮区域 OCR 检测（极高置信度）
            has_bottom_left_keys = False
            if ocr_results:
                for box in ocr_results:
                    txt = box.text.strip().upper()
                    # 还原 2.0 缩放
                    cx = int((box.box[0] + box.box[2] // 2) / 2.0)
                    cy = int((box.box[1] + box.box[3] // 2) / 2.0)
                    if txt in ["ENTER", "I", "K", "聊天"] and cx < w * 0.25 and cy > h * 0.8:
                        has_bottom_left_keys = True
                        break

            # 特征2：右上角地图区域（约 x:82-100%, y:0-15%）
            has_minimap = False
            top_right = image[0:int(h*0.15), int(w*0.82):w]
            if top_right.size > 0:
                green_mask = (
                    (top_right[:,:,1].astype(int) > 80) &
                    (top_right[:,:,1].astype(int) < 180) &
                    (top_right[:,:,0].astype(int) < 100) &
                    (top_right[:,:,2].astype(int) < 100)
                )
                green_ratio = np.count_nonzero(green_mask) / green_mask.size
                if green_ratio > 0.1:
                    has_minimap = True
            
            # 特征3：左上角精灵头像区域（约 x:0-12%, y:0-12%）
            has_avatar = False
            top_left = image[0:int(h*0.12), 0:int(w*0.12)]
            if top_left.size > 0:
                tl_gray = cv2.cvtColor(top_left, cv2.COLOR_BGR2GRAY)
                # 排除纯透明/纯黑色的部分，计算非均匀区域比例
                non_white = np.count_nonzero((tl_gray < 240) & (tl_gray > 20)) / tl_gray.size
                if non_white > 0.3:
                    has_avatar = True
            
            # 严格模式：至少需要满足 "左下角按键" 或 "同时满足地图和头像"
            return has_bottom_left_keys or (has_minimap and has_avatar)
        except:
            return False

    def _rule_based_decision(self, skills: list, my_type: str, enemy_type: str,
                             current_energy: int, my_hp_pct: float,
                             enemy_hp_pct: float, my_pet: str, enemy_pet: str) -> tuple:
        """纯规则决策：基于属性克制、能量管理、血量判断"""
        if not skills or len(skills) == 0:
            return None, "无技能数据"
        
        best_cmd = None
        best_reason = ""
        best_score = -999
        
        # 1. 检查是否需要换宠（我方被严重克制且血量低）
        if my_hp_pct is not None and my_hp_pct < 30 and enemy_type:
            my_weak = False
            if enemy_type in self.TYPE_CHART and my_type in self.TYPE_CHART.get(enemy_type, []):
                my_weak = True
            if my_weak and self.team_list:
                best_switch = self._find_best_switch(enemy_type, my_pet)
                if best_switch:
                    return f"E{best_switch}", f"我方被克制且血量低，换上克制{enemy_pet}的宠物"
        
        # 2. 评估每个技能
        for i, skill in enumerate(skills):
            if not skill or skill.get("name") == "未知":
                continue
            
            idx = i + 1
            score = 0
            reasons = []
            
            power = 0
            try:
                power = int(skill.get("power", 0))
            except:
                power = 0
            score += power * 0.5
            
            skill_type = skill.get("type", "").lower()
            effect = skill.get("effect", "")
            energy_cost = skill.get("energy_cost")
            cd = skill.get("cooldown", 0)
            
            if cd and cd > 0:
                continue
            if current_energy is not None and energy_cost is not None and current_energy < energy_cost:
                continue
            
            if skill_type and enemy_type:
                if skill_type in self.TYPE_CHART and enemy_type in self.TYPE_CHART.get(skill_type, []):
                    score += 200
                    reasons.append(f"属性克制敌方")
                elif enemy_type in self.RESIST_CHART and skill_type in self.RESIST_CHART.get(enemy_type, []):
                    score -= 100
                    reasons.append(f"被敌方抵抗")
            
            if "先手" in effect or "先制" in effect:
                score += 80
                reasons.append("先手技能")
            
            if power >= 100:
                score += 50
                reasons.append("高威力")
            
            if current_energy is not None and energy_cost is not None:
                if current_energy <= 3 and energy_cost <= 2:
                    score += 60
                    reasons.append("低能耗")
                elif current_energy >= 8 and energy_cost >= 4:
                    score += 30
                    reasons.append("能量充足可释放")
            
            if enemy_hp_pct is not None and enemy_hp_pct < 30 and power > 50:
                score += 40
                reasons.append("敌方残血，高威力收割")
            
            if score > best_score:
                best_score = score
                best_cmd = str(idx)
                best_reason = "、".join(reasons) if reasons else "综合最优"
        
        # 3. 如果没有可用技能，考虑恢复能量
        if not best_cmd:
            if current_energy is not None and current_energy < 3:
                return "X", "能量不足，恢复能量"
            for i, skill in enumerate(skills):
                if skill and skill.get("name") != "未知":
                    cd = skill.get("cooldown", 0)
                    ec = skill.get("energy_cost")
                    if (not cd or cd <= 0) and (ec is None or current_energy is None or current_energy >= ec):
                        return str(i+1), "默认选择可用技能"
        
        return best_cmd, best_reason
    
    def _find_best_switch(self, enemy_type: str, current_pet_name: str) -> int:
        """寻找最优换宠目标：克制敌方且血量健康的宠物"""
        if not self.team_list or not enemy_type:
            return None
        
        best_slot = None
        best_score = -999
        
        for i, pet in enumerate(self.team_list, 1):
            pet_name = pet.get("name", "")
            if pet_name == current_pet_name:
                continue
            
            pet_type = self._get_pet_type(pet_name)
            if not pet_type:
                continue
            
            score = 0
            if pet_type in self.TYPE_CHART and enemy_type in self.TYPE_CHART.get(pet_type, []):
                score += 300
            if enemy_type in self.TYPE_CHART and pet_type in self.TYPE_CHART.get(enemy_type, []):
                score -= 200
            if enemy_type in self.RESIST_CHART and pet_type in self.RESIST_CHART.get(enemy_type, []):
                score += 100
            
            if score > best_score:
                best_score = score
                best_slot = i
        
        return best_slot

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
                controller = Win32Controller(hWnd=hwnd, screencap_method=18, mouse_method=2, keyboard_method=4)
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
