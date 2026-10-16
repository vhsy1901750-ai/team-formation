# 2026-10-16 22:09 KST
"""schema.sql을 Supabase DB에 실행하고 만들어진 tf_ 테이블 이름을 출력한다."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import psycopg

from tf.config import get_secret, load_local_env


def main() -> None:
    load_local_env()
    sql = (ROOT / "schema.sql").read_text(encoding="utf-8")
    with psycopg.connect(get_secret("DATABASE_URL"), connect_timeout=15) as conn:
        conn.execute(sql)
        names = conn.execute(
            "select table_name from information_schema.tables"
            " where table_schema = 'public' and table_name like 'tf\\_%' order by 1"
        ).fetchall()
    print(len(names), "개:", ", ".join(n for (n,) in names))


if __name__ == "__main__":
    main()
