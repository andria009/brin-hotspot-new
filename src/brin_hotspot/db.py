from __future__ import annotations

import psycopg

from brin_hotspot.config import DatabaseSettings


def check_database_connection(settings: DatabaseSettings) -> None:
    with psycopg.connect(settings.dsn, connect_timeout=5) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()

