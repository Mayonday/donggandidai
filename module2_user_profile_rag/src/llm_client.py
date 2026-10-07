# -*- coding: utf-8 -*-
"""团队统一大模型调用封装（成员2视角）。

仅使用标准库 urllib，避免强依赖 requests；接口对齐 OpenAI 兼容协议
（绝大多数开源大模型 vLLM / Ollama / LMDeploy 均提供该协议）。

后端：
    mock               —— 离线自测用，返回确定性的共情式回复，不联网。
    openai_compatible  —— 调用真实模型（base_url + api_key + model_name）。
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request

# 常见 OpenAI 兼容模型的默认模型名（成员1确认后以 config.yaml 为准）
FALLBACK_MODEL_NAME = "qwen2.5-7b-instruct"


class LLMClient:
    def __init__(self, model_cfg: dict):
        self.backend = model_cfg.get("backend", "mock")
        self.base_url = (model_cfg.get("base_url") or "").rstrip("/")
        self.model_name = model_cfg.get("model_name") or FALLBACK_MODEL_NAME
        self.api_key = os.environ.get(model_cfg.get("api_key_env", "OPENAI_API_KEY"), "")
        self.temperature = float(model_cfg.get("temperature", 0.7))
        self.max_tokens = int(model_cfg.get("max_tokens", 512))
        self.timeout = int(model_cfg.get("timeout", 60))

    # ------------------------------------------------------------------
    # 对外主入口
    # ------------------------------------------------------------------
    def chat(self, messages: list[dict], temperature=None, max_tokens=None) -> str:
        """给定标准 messages，返回模型的文本回复。"""
        if self.backend == "mock":
            return self._mock_reply(messages)
        return self._chat_openai_compatible(messages, temperature, max_tokens)

    # ------------------------------------------------------------------
    # 真实模型调用（OpenAI 兼容 /chat/completions）
    # ------------------------------------------------------------------
    def _chat_openai_compatible(self, messages, temperature, max_tokens) -> str:
        url = self.base_url + "/chat/completions"
        payload = {
            "model": self.model_name,
            "messages": messages,
            "temperature": self.temperature if temperature is None else temperature,
            "max_tokens": self.max_tokens if max_tokens is None else max_tokens,
            "stream": False,
        }
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = "Bearer " + self.api_key

        req = urllib.request.Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            raise RuntimeError(
                f"大模型接口返回 HTTP {e.code}: {e.read().decode('utf-8', 'ignore')}"
            ) from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"无法连接大模型接口 {url}: {e.reason}") from e

        data = json.loads(body)
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise RuntimeError(f"大模型返回结构异常: {body[:500]}") from e

    # ------------------------------------------------------------------
    # 离线 mock：确定性回复，便于自测/演示
    # ------------------------------------------------------------------
    def _mock_reply(self, messages: list[dict]) -> str:
        system = "\n".join(m.get("content", "") for m in messages if m["role"] == "system")
        last_user = next(
            (m.get("content", "") for m in reversed(messages) if m["role"] == "user"),
            "",
        )

        persona = "陪伴者"
        m = re.search(r"「(.{1,8})」", system)
        if m:
            persona = m.group(1)
        else:
            m = re.search(r"你是(.{1,12})", system)
            if m:
                persona = m.group(1).strip("，。；、\"'")

        # 从系统提示里取当前情绪与相关记忆片段，用于验证"上下文注入"是否生效
        emotion = ""
        me = re.search(r"当前情绪[:：]\s*([^\n]+)", system)
        if me:
            emotion = me.group(1).strip()

        memory_hint = ""
        mm = re.search(r"相关记忆[:：]\s*\n?(.{0,40})", system)
        if mm:
            memory_hint = mm.group(1).strip()

        user_brief = last_user.strip().replace("\n", " ")
        if len(user_brief) > 24:
            user_brief = user_brief[:24] + "…"

        parts = [f"{persona}：我在听，先陪着你。"]
        if emotion:
            parts.append(f"我感觉到你现在有些{emotion}。")
        if memory_hint and memory_hint not in ("（暂无）", "（无相关记忆）", ""):
            parts.append(f"还记得你之前提到过「{memory_hint}」，我们可以接着聊。")
        if user_brief:
            parts.append(f"你说到「{user_brief}」，可以多和我讲讲吗？")
        parts.append("我不着急，你慢慢说。")
        return "".join(parts)
