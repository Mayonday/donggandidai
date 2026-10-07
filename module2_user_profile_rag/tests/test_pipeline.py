# -*- coding: utf-8 -*-
"""自测：统一对外接口（供成员1集成、成员3评测调用）。"""
from tests import context


def run():
    from src.pipeline import CompanionPipeline

    ctx = context.build()
    pipe = CompanionPipeline.from_config(module_dir=ctx["module_root"])
    pipe.reset()

    results = []

    # 1. 一行式对话
    out = pipe.chat("今天被领导骂了，好难受", user_id="p1", emotion_label="悲伤")
    ok = isinstance(out, dict) and bool(out.get("response"))
    results.append({"name": "pipeline.chat 返回回复", "ok": ok,
                    "info": out.get("response", "")[:36]})

    # 2. 画像抽取接口
    prof = pipe.extract_profile("我是女生，在上海读大学，喜欢听歌")
    ok = isinstance(prof, dict) and prof.get("gender") == "女" and prof.get("location") == "一线城市"
    results.append({"name": "pipeline.extract_profile 可用", "ok": ok,
                    "info": f"gender={prof.get('gender')}, location={prof.get('location')}"})

    # 3. 记忆检索接口（跨轮）
    pipe.chat("我养了一只叫豆豆的橘猫", user_id="p2")
    hits = pipe.retrieve("猫")
    ok = any("橘猫" in h["text"] for h in hits)
    results.append({"name": "pipeline.retrieve 跨轮检索", "ok": ok,
                    "info": f"命中 {len(hits)} 条"})

    # 4. 画像查询与重置
    prof2 = pipe.get_profile("p1")
    pipe.reset("p1")
    after = pipe.get_profile("p1")
    ok = bool(prof2) and not after
    results.append({"name": "pipeline.reset 清空指定用户", "ok": ok,
                    "info": f"重置前 {len(prof2)} 项, 重置后 {len(after)} 项"})

    return {"suite": "统一对外接口", "results": results}
