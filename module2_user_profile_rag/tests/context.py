# -*- coding: utf-8 -*-
"""自测公共上下文：构建模块各组件，供各 test_*.py 与 run_self_test.py 复用。"""
import json
import os
import sys

# 保证可 import src 包（模块根目录加入 sys.path）
_MODULE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _MODULE_ROOT not in sys.path:
    sys.path.insert(0, _MODULE_ROOT)


def module_root() -> str:
    return _MODULE_ROOT


def load_dimensions():
    from src.config_loader import load_config, Config
    from src import yaml_light
    cfg = load_config(_MODULE_ROOT)
    dims_path = Config(cfg, _MODULE_ROOT).resolve(cfg["profile"]["dimensions_path"])
    with open(dims_path, "r", encoding="utf-8") as f:
        data = yaml_light.loads(f.read())
    return data["dimensions"]


def build():
    """构建并返回自测所需组件 dict。"""
    from src.config_loader import load_config, Config
    from src.llm_client import LLMClient
    from src.embedding import build_embedder
    from src.memory_store import VectorMemoryStore
    from src.profile_extractor import ProfileExtractor

    cfg = Config(load_config(_MODULE_ROOT), _MODULE_ROOT)

    llm = LLMClient(cfg.section("model"))
    embedder = build_embedder(cfg.section("embedding"), cfg.section("model"))

    memory_cfg = dict(cfg.section("memory"))
    memory_cfg["persist_path"] = os.path.join(_MODULE_ROOT, "data", "test_memory_store.json")
    memory = VectorMemoryStore(embedder, memory_cfg)

    dimensions = load_dimensions()
    extractor = ProfileExtractor(dimensions, cfg.section("profile"), llm_client=llm)

    dim_names = {d["id"]: d["name"] for d in dimensions}

    from src.dialogue_generator import DialogueGenerator
    generator = DialogueGenerator(cfg, llm, memory, extractor, dimension_names=dim_names)

    return {
        "cfg": cfg,
        "llm": llm,
        "embedder": embedder,
        "memory": memory,
        "extractor": extractor,
        "generator": generator,
        "dimensions": dimensions,
        "module_root": _MODULE_ROOT,
    }


def load_profile_samples():
    path = os.path.join(_MODULE_ROOT, "data", "profile_samples.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
