"""Conexão com o PostgreSQL usando um pool (reaproveita conexões entre requisições).

Todas as consultas usam parâmetros (%s), nunca concatenação de texto:
isso impede injeção de SQL.
"""
from collections.abc import Iterator

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from . import config

pool = ConnectionPool(
    config.DATABASE_URL,
    min_size=1,
    max_size=10,
    kwargs={"row_factory": dict_row},   # cada linha vem como dicionário
    open=False,
)


def conexao() -> Iterator[Connection]:
    """Dependência do FastAPI: uma transação por requisição.

    Se a rota terminar sem erro, a transação é confirmada (commit);
    se der erro, tudo é desfeito (rollback).
    """
    with pool.connection() as conn:
        yield conn
