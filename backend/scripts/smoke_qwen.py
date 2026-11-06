"""Qwen3（阿里云百炼）连通性冒烟测试。

用法（在 backend/ 目录下）：
    python scripts/smoke_qwen.py
    python scripts/smoke_qwen.py --api-key sk-xxx --model qwen3-max

API Key 优先取 --api-key，其次取环境变量 DASHSCOPE_API_KEY。
"""
import argparse
import json
import os
import sys
from pathlib import Path

import httpx

DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_MODEL = "qwen3.8-max"

BASE_DIR = Path(__file__).resolve().parent.parent  # backend/


def load_env_file(path: Path) -> None:
    """读取 backend/.env（KEY=VALUE 格式，跳过注释），不覆盖已存在的环境变量。"""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def main() -> int:
    load_env_file(BASE_DIR / ".env")
    parser = argparse.ArgumentParser(description="Qwen3 连通性冒烟测试")
    parser.add_argument("--api-key", default=os.environ.get("DASHSCOPE_API_KEY", ""))
    parser.add_argument("--model", default=os.environ.get("LLM_MODEL", DEFAULT_MODEL))
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    args = parser.parse_args()

    if not args.api_key:
        print("[失败] 未找到 API Key：请设置环境变量 DASHSCOPE_API_KEY 或用 --api-key 传入")
        return 1

    print(f"[信息] 调用模型: {args.model}")
    try:
        resp = httpx.post(
            f"{args.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {args.api_key}"},
            json={
                "model": args.model,
                "messages": [{"role": "user", "content": "只回复两个字：OK"}],
                "max_tokens": 10,
            },
            timeout=30,
        )
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        print(f"[失败] HTTP {e.response.status_code}: {e.response.text[:300]}")
        return 1
    except httpx.HTTPError as e:
        print(f"[失败] 网络错误: {e}")
        return 1

    data = resp.json()
    content = data["choices"][0]["message"]["content"].strip()
    print(f"[成功] 模型回复: {content}")
    print(
        f"[信息] 实际模型: {data.get('model')} | "
        f"token 用量: {json.dumps(data.get('usage', {}), ensure_ascii=False)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
