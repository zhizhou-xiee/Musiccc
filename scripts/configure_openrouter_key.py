#!/usr/bin/env python3
"""Save an OpenRouter API key locally without echoing it or committing it."""

from __future__ import annotations

import getpass
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SECRET_DIR = ROOT / ".secrets"
SECRET_PATH = SECRET_DIR / "openrouter_api_key"


def main() -> None:
    print("请输入 OpenRouter API key。粘贴时屏幕不会显示字符，这是正常的。")
    key = getpass.getpass("OpenRouter API key: ").strip()
    if not key:
        raise SystemExit("没有收到密钥，未写入任何文件。")
    if not key.startswith("sk-or-"):
        raise SystemExit("这不像 OpenRouter 密钥（通常以 sk-or- 开头），未写入。")

    SECRET_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(SECRET_DIR, 0o700)
    descriptor = os.open(SECRET_PATH, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(descriptor, (key + "\n").encode("utf-8"))
    finally:
        os.close(descriptor)
    os.chmod(SECRET_PATH, 0o600)
    print("已安全保存到本机 .secrets/openrouter_api_key；密钥内容没有显示。")


if __name__ == "__main__":
    main()
