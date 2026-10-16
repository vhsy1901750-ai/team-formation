# 2026-10-16 22:06 KST
"""비밀 값 읽기. 내 컴퓨터는 .env, 배포한 앱은 Streamlit Secrets에서 읽는다.

값은 절대 출력하지 않는다. 있는지 확인할 때는 '있음, 없음'만 쓴다.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent


def load_local_env() -> None:
    env_file = ROOT / ".env"
    if env_file.exists():
        load_dotenv(env_file, override=False)


def get_secret(name: str) -> str | None:
    value = os.environ.get(name)
    if value is None:
        try:
            import streamlit as st

            value = st.secrets.get(name)
        except Exception:  # secrets 파일이 없으면 Streamlit이 예외를 낸다
            value = None
    if value is None:
        return None
    value = str(value).strip()
    return value or None
