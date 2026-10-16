# 2026-10-16 22:32 KST
"""Supabase 무료 프로젝트가 일시정지되지 않도록 DB에 질의한다. 깃허브 액션이 매일 실행한다."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tf import db
from tf.config import get_secret, load_local_env


def main() -> None:
    load_local_env()
    pool = db.make_pool(get_secret("DATABASE_URL"))
    try:
        db.touch_keepalive(pool)
        with pool.connection() as conn:
            count = conn.execute("select count(*) from tf_students").fetchone()[0]
            last = conn.execute("select value from tf_settings where key = 'last_keepalive'").fetchone()[0]
    finally:
        pool.close()
    print(f"DB 질의 성공: tf_students {count}행, last_keepalive {last}")


if __name__ == "__main__":
    main()
