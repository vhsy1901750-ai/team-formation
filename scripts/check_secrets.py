# 2026-10-16 22:06 KST
"""비밀 값이 있는지와 DB, 오픈라우터 접속만 확인한다. 값은 출력하지 않는다."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psycopg
import requests

from tf.config import get_secret, load_local_env

NAMES = ["OPENROUTER_API_KEY", "DATABASE_URL", "ADMIN_PASSWORD"]


def main() -> None:
    load_local_env()
    for name in NAMES:
        print(name, "있음" if get_secret(name) else "없음")

    url = get_secret("DATABASE_URL")
    if url:
        try:
            with psycopg.connect(url, connect_timeout=15) as conn:
                conn.execute("select 1")
            print("DB 접속: 성공")
        except Exception as e:
            print("DB 접속: 실패", type(e).__name__)

    key = get_secret("OPENROUTER_API_KEY")
    if key:
        r = requests.get(
            "https://openrouter.ai/api/v1/key",
            headers={"Authorization": f"Bearer {key}"},
            timeout=20,
        )
        print("오픈라우터 키:", r.status_code)


if __name__ == "__main__":
    main()
