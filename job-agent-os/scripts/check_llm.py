# 新建文件: /Users/zhaozhizhun/pycharm_project/mult-agent/job-agent-os/scripts/check_llm.py
"""Standalone LLM connectivity check.

Does NOT import job_agent_os (no DB / Redis / JWT validation needed).
Only reads OPENAI_* variables from .env and makes one real LLM call.

Usage:
    uv run python scripts/check_llm.py
"""

import os
import sys
import time

from dotenv import load_dotenv

load_dotenv()  # 读取项目根目录的 .env

from langchain_openai import ChatOpenAI


def build_llm(model: str) -> ChatOpenAI:
    return ChatOpenAI(
        model=model,
        api_key=os.getenv("OPENAI_API_KEY", ""),
        base_url=os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com"),
        temperature=float(os.getenv("OPENAI_TEMPERATURE", "0.1")),
        max_tokens=int(os.getenv("OPENAI_MAX_TOKENS", "4096")),
        timeout=int(os.getenv("OPENAI_TIMEOUT", "60")),
    )


def check_model(model: str) -> bool:
    print(f"\n[CHECK] model = {model}")
    print("-" * 50)
    try:
        llm = build_llm(model)
        start = time.time()
        response = llm.invoke("请只回复四个字：连接成功")
        elapsed = time.time() - start

        print(f"[OK]    回复内容: {response.content}")
        usage = getattr(response, "usage_metadata", None)
        if usage:
            print(
                f"[OK]    Token 用量: 输入 {usage.get('input_tokens')} / "
                f"输出 {usage.get('output_tokens')} / "
                f"总计 {usage.get('total_tokens')}"
            )
        print(f"[OK]    耗时: {elapsed:.2f}s")
        return True
    except Exception as e:
        print(f"[FAIL]  调用失败: {type(e).__name__}: {e}")
        return False


def main() -> int:
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key or "your" in api_key.lower():
        print("[FAIL] OPENAI_API_KEY 未配置或为占位符，请检查 .env")
        return 1

    print(f"[INFO] base_url = {os.getenv('OPENAI_BASE_URL')}")
    print(f"[INFO] api_key  = {api_key[:8]}****")

    models = [os.getenv("OPENAI_MODEL", "deepseek-chat")]
    fallback = os.getenv("OPENAI_MODEL_FALLBACK", "")
    if fallback and fallback != models[0]:
        models.append(fallback)

    results = {model: check_model(model) for model in models}

    print("\n" + "=" * 50)
    for model, ok in results.items():
        print(f"  {model}: {'✅ 成功' if ok else '❌ 失败'}")
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
