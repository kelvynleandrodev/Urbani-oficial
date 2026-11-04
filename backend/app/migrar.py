"""Aplica as migrações SQL de backend/db/migrations em ordem.

Uso (dentro da pasta backend):
    python -m app.migrar            aplica só as que ainda não rodaram
    python -m app.migrar --sem-demo pula os dados de demonstração (002_dados_demo.sql)

Cada arquivo roda numa transação e fica registrado em schema_migrations,
então rodar o comando de novo não duplica nada.
"""
import sys
from pathlib import Path

import psycopg

from . import config

PASTA = Path(__file__).resolve().parent.parent / "db" / "migrations"


def migrar(url: str = config.DATABASE_URL, com_demo: bool = True) -> list[str]:
    aplicadas = []
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations ("
                     "arquivo TEXT PRIMARY KEY, aplicada_em TIMESTAMPTZ NOT NULL DEFAULT now())")
        feitas = {r[0] for r in conn.execute("SELECT arquivo FROM schema_migrations")}
        for arq in sorted(PASTA.glob("*.sql")):
            if arq.name in feitas or (not com_demo and "demo" in arq.name):
                continue
            with conn.transaction():
                conn.execute(arq.read_text(encoding="utf-8"))
                conn.execute("INSERT INTO schema_migrations (arquivo) VALUES (%s)", (arq.name,))
            aplicadas.append(arq.name)
    return aplicadas


if __name__ == "__main__":
    feitas = migrar(com_demo="--sem-demo" not in sys.argv)
    print("Aplicadas:", ", ".join(feitas) if feitas else "nenhuma (banco já atualizado)")
