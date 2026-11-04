"""Categorias de ocorrência (lista pública, usada no formulário e nos filtros)."""
from fastapi import APIRouter, Depends
from psycopg import Connection

from ..db import conexao
from ..esquemas import CategoriaSaida

router = APIRouter(prefix="/api", tags=["Categorias"])


@router.get("/categorias", response_model=list[CategoriaSaida], summary="Listar categorias ativas")
def listar(conn: Connection = Depends(conexao)):
    return conn.execute("SELECT id, nome, descricao FROM categorias WHERE ativa ORDER BY nome").fetchall()
