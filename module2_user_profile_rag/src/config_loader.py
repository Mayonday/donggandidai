# -*- coding: utf-8 -*-
"""统一配置加载器（成员2模块）。

设计目标：
    1) 只读团队公共 config.yaml，绝不修改；
    2) 本模块可用自己的 config.yaml 覆盖公共配置中的本模块相关项；
    3) 未提供任何文件时使用内置默认值（与 config.example.yaml 一致），
       保证离线可自测、可复现。

查找顺序（先找到的生效，逐层合并，后者覆盖前者）：
    a. 模块目录/config.yaml            —— 本模块本地覆盖（若有）
    b. 模块目录/../config.yaml          —— 团队公共配置（只读）
    c. 模块目录/config.example.yaml     —— 内置示例/默认值
"""
from __future__ import annotations

import os

from . import yaml_light

# 内置默认值：与 config.example.yaml 保持一致
DEFAULTS = {
    "model": {
        "backend": "mock",               # mock | openai_compatible
        "base_url": "http://127.0.0.1:8000/v1",
        "api_key_env": "OPENAI_API_KEY",
        # 团队已确定使用 Qwen 系列；此处为默认值，实际以团队 config.yaml 为准。
        # model_name 必须与推理服务暴露的名字完全一致（vLLM 用 HF 仓库名，Ollama 用 qwen2.5:7b）。
        "model_name": "Qwen/Qwen2.5-7B-Instruct",
        "temperature": 0.7,
        "max_tokens": 512,
        "timeout": 60,
    },
    "embedding": {
        # 团队选定：优先 sentence_transformers（中文检索质量更高）；
        # 目标环境缺依赖时自动降级到 fallback_backend，保证程序可运行。
        "backend": "sentence_transformers",   # sentence_transformers | hashing | api
        "fallback_backend": "hashing",
        "model_name": "BAAI/bge-small-zh-v1.5",
        "dim": 512,
        "ngram_min": 1,
        # n-gram 上界与虚词降权：见 logs Iter 11 的实测（校准集 Recall 0.667→0.800）。
        "ngram_max": 2,
        "function_word_weight": 0.15,
    },
    "emotion": {
        # 成员1 情感识别模块的标签集（待成员1 同步确认后更新此处即可全链路生效）
        "labels": ["开心", "平静", "焦虑", "悲伤", "愤怒", "孤独", "疲惫", "未知"],
        "unknown_label": "未知",
    },
    "memory": {
        "top_k": 5,
        # 绝对下限：只做"完全无关"的兜底筛除。
        "similarity_threshold": 0.10,
        # 相对下限：只保留与最佳命中同一量级的记忆，自适应提问措辞造成的分数漂移。
        # 实测（30 条标注查询，见 logs Iter 11）：
        #   绝对模式最优 F1 0.760 (Recall 0.633)
        #   相对模式最优 F1 0.828 (Recall 0.800) <- 采用
        "relative_ratio": 0.8,
        # 按实际生效的嵌入后端分别标定绝对下限（避免 ST→hashing 静默降级后失配）。
        "similarity_threshold_by_backend": {"hashing": 0.10},
        "persist_path": "data/memory_store.json",
        "max_dialogue_turns": 200,
        "summarize_every": 20,
        "max_facts": 60,
    },
    "profile": {
        "dimensions_path": "profiles/profile_dimensions.yaml",
        "backend": "heuristic",          # heuristic | llm
        "min_confidence": 0.5,
    },
    "persona": {
        "default_persona": "温暖倾听者",
        "language": "zh",
        "max_history_turns": 8,
        "anti_hallucination": True,      # 提示词层面的护栏（软约束）
        # 程序层面的防瞎编校验（硬约束），见 src/anti_hallucination.py
        "hallucination_check": {
            "mode": "enforce",           # off | warn | enforce
            "enforce_entities": True,    # 仅对高精度"实体级"信号做拦截
            "report_sentences": True,    # 低精度"句级"信号仅记录不拦截
            "min_overlap": 0.30,
            "min_claim_len": 5,
        },
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    """递归合并两个字典，override 的值覆盖 base。"""
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _load_yaml_file(path: str):
    """读取 YAML 文件；优先 PyYAML，缺失时退回内置极简解析器。"""
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    try:
        import yaml  # type: ignore
        return yaml.safe_load(text) or {}
    except ImportError:
        return yaml_light.loads(text)


def load_config(module_dir: str | None = None) -> dict:
    """加载并合并配置，返回顶层 dict（含 model/embedding/memory/profile/persona）。"""
    if module_dir is None:
        # 默认以本文件所在目录的上一级作为模块根目录（src/ 的上一级）
        module_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    cfg = _deep_merge({}, DEFAULTS)

    # c. 默认值已内置；再尝试读 example 文件兜底（保持一致）
    example = os.path.join(module_dir, "config.example.yaml")
    if os.path.isfile(example):
        cfg = _deep_merge(cfg, _load_yaml_file(example))

    # b. 团队公共配置（只读，不写）
    public = os.path.join(module_dir, "..", "config.yaml")
    public = os.path.abspath(public)
    if os.path.isfile(public):
        cfg = _deep_merge(cfg, _load_yaml_file(public))

    # a. 本模块本地覆盖
    local = os.path.join(module_dir, "config.yaml")
    if os.path.isfile(local):
        cfg = _deep_merge(cfg, _load_yaml_file(local))

    return cfg


class Config:
    """配置访问封装，提供点号/分节访问与路径解析。"""

    def __init__(self, data: dict, module_dir: str | None = None):
        self.data = data
        self.module_dir = module_dir or os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))
        )

    def __getitem__(self, key):
        return self.data[key]

    def get(self, path: str, default=None):
        """按点分路径取值，如 get('model.temperature')。"""
        node = self.data
        for part in path.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def section(self, name: str) -> dict:
        return self.data.get(name, {})

    def resolve(self, path: str) -> str:
        """把相对路径解析为基于模块根目录的绝对路径。"""
        if os.path.isabs(path):
            return path
        return os.path.join(self.module_dir, path)

    def copy_to_module_config(self):
        """（工具函数）把当前生效配置导出为本模块 config.yaml。

        仅用于开发时固化一份本地配置，不触碰公共配置。
        """
        # 依赖 PyYAML；缺失时用极简方式写出（本函数仅供开发，非运行必需）
        return self.data
