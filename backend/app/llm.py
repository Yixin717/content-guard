"""DeepSeek 客户端：结构化输出 + 坏 JSON 重试 + 兜底解析。

设计要点（D1 的核心学习点）：
1. 用 response_format={"type": "json_object"} 让模型输出 JSON，而不是靠正则抠；
2. 依然可能拿到坏 JSON（截断、包了 ```json、多一段解释），所以做三层处理：
   - 第一次：直接 json.loads
   - 失败：_extract_json 从文本里截取最外层 {...} 再试
   - 仍失败：把错误回喂给模型重试一次（temperature 降为 0）
3. 全部失败时抛 LLMError，并保留原始文本供后续失败样本分析。
"""

from __future__ import annotations

import json
import re
import time
from typing import Any, Dict, Optional, Tuple, Type

import httpx
from pydantic import BaseModel, ValidationError

from .config import settings


class LLMError(RuntimeError):
    """调用失败或 JSON 始终无法解析。"""

    def __init__(self, message: str, raw: str = ""):
        super().__init__(message)
        self.raw = raw


def _extract_json(text: str) -> Optional[str]:
    """从可能带 markdown 围栏/前后缀说明的文本里，截出最外层 JSON 对象。"""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.+?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    return text[start : end + 1]


class LLM:
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None, timeout: float = 90.0):
        self.api_key = api_key or settings.require_key()
        self.model = model or settings.model
        self.base_url = settings.base_url
        self.timeout = timeout

    # ---- 低层调用 ----
    def _post(self, messages, temperature: float, json_mode: bool) -> Tuple[str, Dict[str, Any]]:
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": 2000,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        started = time.time()
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        latency_ms = int((time.time() - started) * 1000)

        if resp.status_code != 200:
            raise LLMError(f"HTTP {resp.status_code}: {resp.text[:300]}")

        data = resp.json()
        content = data["choices"][0]["message"]["content"] or ""
        usage = data.get("usage", {}) or {}
        meta = {
            "model": self.model,
            "tokens_in": usage.get("prompt_tokens", 0),
            "tokens_out": usage.get("completion_tokens", 0),
            "latency_ms": latency_ms,
        }
        return content, meta

    # ---- 结构化输出 ----
    def chat_json(
        self,
        system: str,
        user: str,
        schema: Type[BaseModel],
        max_retries: int = 2,
    ) -> Tuple[BaseModel, Dict[str, Any]]:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        last_raw = ""
        last_err: Optional[str] = None
        total = {"tokens_in": 0, "tokens_out": 0, "latency_ms": 0, "attempts": 0}

        for attempt in range(max_retries + 1):
            content, meta = self._post(messages, temperature=0.3 if attempt == 0 else 0.0, json_mode=True)
            total["attempts"] += 1
            for k in ("tokens_in", "tokens_out", "latency_ms"):
                total[k] += meta[k]
            last_raw = content

            candidate = content
            try:
                data = json.loads(candidate)
            except json.JSONDecodeError:
                extracted = _extract_json(candidate)
                try:
                    data = json.loads(extracted) if extracted else None
                except json.JSONDecodeError:
                    data = None

            if data is not None:
                try:
                    return schema.model_validate(data), total
                except ValidationError as exc:
                    last_err = f"字段校验失败：{exc.errors()[:3]}"
            else:
                last_err = "返回的不是合法 JSON"

            # 回喂错误，要求重出
            messages = messages[:2] + [
                {"role": "assistant", "content": content[:1500]},
                {
                    "role": "user",
                    "content": (
                        f"上面的输出无法解析为符合要求的 JSON（{last_err}）。"
                        "请只输出一个 JSON 对象，不要 markdown 代码块、不要任何解释文字。"
                    ),
                },
            ]

        raise LLMError(f"重试 {total['attempts']} 次后仍失败：{last_err}", raw=last_raw)

    def chat_text(self, system: str, user: str, temperature: float = 0.7) -> Tuple[str, Dict[str, Any]]:
        """非结构化调用，暂时保留给改写环节探索用。"""
        return self._post(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=temperature,
            json_mode=False,
        )
