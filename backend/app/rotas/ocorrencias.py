"""Ocorrências: listagem, detalhe, criação, mudança de status, proximidade e apoios."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from psycopg import Connection
from psycopg.errors import CheckViolation, UniqueViolation

from ..db import conexao
from ..esquemas import (ApoiosSaida, HistoricoSaida, OcorrenciaEntrada, OcorrenciaSaida,
                        Status, StatusEntrada)
from ..seguranca import exigir_perfil, usuario_atual

router = APIRouter(prefix="/api/ocorrencias", tags=["Ocorrências"])

# Consulta base. Latitude = Y e longitude = X do ponto PostGIS.
# Só o nome do autor é exposto; CPF e e-mail nunca saem nesta rota (LGPD).
_SELECT = """
SELECT o.id, o.titulo, o.descricao, o.urgencia, o.status,
       o.categoria_id, c.nome AS categoria_nome,
       o.usuario_id, u.nome AS autor_nome,
       o.endereco_referencia,
       ST_Y(o.localizacao) AS latitude, ST_X(o.localizacao) AS longitude,
       o.apoios_total,
       EXISTS (SELECT 1 FROM apoios a
               WHERE a.ocorrencia_id = o.id AND a.usuario_id = %(me)s) AS apoiado_por_mim,
       o.criado_em, o.atualizado_em
  FROM ocorrencias o
  JOIN categorias c ON c.id = o.categoria_id
  JOIN usuarios   u ON u.id = o.usuario_id
"""

_ORDENS = {
    "recentes": "o.criado_em DESC",
    "apoiadas": "o.apoios_total DESC, o.criado_em DESC",
    # Prioridade dinâmica: ocorrências em aberto primeiro; depois maior
    # urgência; depois mais apoios (validação social); depois as mais antigas
    # esperando (quem espera há mais tempo vem antes no empate).
    "prioridade": "(o.status IN ('RESOLVIDA','REJEITADA')), "
                  "CASE o.urgencia WHEN 'ALTA' THEN 3 WHEN 'MEDIA' THEN 2 ELSE 1 END DESC, "
                  "o.apoios_total DESC, o.criado_em ASC",
}

# Mudanças de status permitidas (as demais são recusadas)
TRANSICOES = {
    "ABERTA": {"EM_ANALISE", "EM_ANDAMENTO", "REJEITADA"},
    "EM_ANALISE": {"EM_ANDAMENTO", "REJEITADA"},
    "EM_ANDAMENTO": {"RESOLVIDA"},
    "RESOLVIDA": set(),
    "REJEITADA": set(),
}

# Antifraude simples: mesma pessoa, mesma categoria, até 50 m, nas últimas 24 h
DUPLICADA_RAIO_M = 50


def _buscar(conn: Connection, ocorrencia_id: int, me: int) -> dict:
    o = conn.execute(_SELECT + " WHERE o.id = %(id)s", {"me": me, "id": ocorrencia_id}).fetchone()
    if not o:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ocorrência não encontrada.")
    return o


@router.get("", summary="Listar ocorrências com filtros, ordenação e paginação")
def listar(
    categoria_id: int | None = None,
    status_: Status | None = Query(None, alias="status"),
    minhas: bool = Query(False, description="Só as ocorrências do usuário logado"),
    ordem: Literal["recentes", "apoiadas", "prioridade"] = "recentes",
    limite: int = Query(100, ge=1, le=200),
    deslocamento: int = Query(0, ge=0),
    u: dict = Depends(usuario_atual),
    conn: Connection = Depends(conexao),
):
    filtros, p = [], {"me": u["id"], "lim": limite, "off": deslocamento}
    if categoria_id is not None:
        filtros.append("o.categoria_id = %(cat)s"); p["cat"] = categoria_id
    if status_:
        filtros.append("o.status = %(st)s"); p["st"] = status_
    if minhas:
        filtros.append("o.usuario_id = %(me)s")
    where = (" WHERE " + " AND ".join(filtros)) if filtros else ""
    total = conn.execute(f"SELECT count(*) AS n FROM ocorrencias o{where}", p).fetchone()["n"]
    itens = conn.execute(
        f"{_SELECT}{where} ORDER BY {_ORDENS[ordem]} LIMIT %(lim)s OFFSET %(off)s", p).fetchall()
    return {"total": total, "itens": [OcorrenciaSaida(**i) for i in itens]}


@router.get("/proximas", response_model=list[OcorrenciaSaida],
            summary="Ocorrências num raio (em metros) a partir de um ponto")
def proximas(
    latitude: float = Query(ge=-90, le=90),
    longitude: float = Query(ge=-180, le=180),
    raio_m: int = Query(1000, ge=10, le=20000),
    limite: int = Query(50, ge=1, le=200),
    u: dict = Depends(usuario_atual),
    conn: Connection = Depends(conexao),
):
    # ST_DWithin em geography mede em metros e usa o índice espacial.
    p = {"me": u["id"], "lat": latitude, "lng": longitude, "raio": raio_m, "lim": limite}
    ponto = "ST_SetSRID(ST_MakePoint(%(lng)s, %(lat)s), 4326)::geography"
    linhas = conn.execute(
        _SELECT.replace("o.criado_em, o.atualizado_em",
                        f"o.criado_em, o.atualizado_em, ST_Distance(o.localizacao::geography, {ponto}) AS distancia_m")
        + f" WHERE ST_DWithin(o.localizacao::geography, {ponto}, %(raio)s)"
          " ORDER BY distancia_m LIMIT %(lim)s", p).fetchall()
    return [OcorrenciaSaida(**linha) for linha in linhas]


@router.get("/{ocorrencia_id}", response_model=OcorrenciaSaida, summary="Detalhe de uma ocorrência")
def detalhe(ocorrencia_id: int, u: dict = Depends(usuario_atual), conn: Connection = Depends(conexao)):
    return _buscar(conn, ocorrencia_id, u["id"])


@router.post("", response_model=OcorrenciaSaida, status_code=status.HTTP_201_CREATED,
             summary="Registrar ocorrência (sempre começa como ABERTA)")
def criar(dados: OcorrenciaEntrada, u: dict = Depends(usuario_atual), conn: Connection = Depends(conexao)):
    if not conn.execute("SELECT 1 FROM categorias WHERE id = %s AND ativa", (dados.categoria_id,)).fetchone():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Categoria inválida.")
    p = {**dados.model_dump(), "me": u["id"], "raio": DUPLICADA_RAIO_M}
    ponto = "ST_SetSRID(ST_MakePoint(%(longitude)s, %(latitude)s), 4326)"
    repetida = conn.execute(
        f"""SELECT id FROM ocorrencias
             WHERE usuario_id = %(me)s AND categoria_id = %(categoria_id)s
               AND status NOT IN ('RESOLVIDA','REJEITADA')
               AND criado_em > now() - interval '24 hours'
               AND ST_DWithin(localizacao::geography, {ponto}::geography, %(raio)s)
             LIMIT 1""", p).fetchone()
    if repetida:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Você já registrou uma ocorrência dessa categoria neste local nas últimas 24 horas "
                            f"(nº {repetida['id']}).")
    novo = conn.execute(
        f"""INSERT INTO ocorrencias (usuario_id, categoria_id, titulo, descricao, urgencia,
                                     localizacao, endereco_referencia)
            VALUES (%(me)s, %(categoria_id)s, %(titulo)s, %(descricao)s, %(urgencia)s,
                    {ponto}, %(endereco_referencia)s)
            RETURNING id""", p).fetchone()
    conn.execute(
        "INSERT INTO historico_status (ocorrencia_id, status_anterior, status_novo, observacao, autor_id) "
        "VALUES (%s, NULL, 'ABERTA', 'Ocorrência registrada pelo cidadão.', %s)", (novo["id"], u["id"]))
    return _buscar(conn, novo["id"], u["id"])


@router.patch("/{ocorrencia_id}", response_model=OcorrenciaSaida,
              summary="Alterar status (somente GESTOR ou ADMIN)")
def alterar_status(ocorrencia_id: int, dados: StatusEntrada,
                   u: dict = Depends(exigir_perfil("GESTOR", "ADMIN")),
                   conn: Connection = Depends(conexao)):
    # FOR UPDATE trava a linha: dois gestores não mudam o status ao mesmo tempo.
    atual = conn.execute("SELECT status FROM ocorrencias WHERE id = %s FOR UPDATE", (ocorrencia_id,)).fetchone()
    if not atual:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ocorrência não encontrada.")
    if dados.status not in TRANSICOES[atual["status"]]:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Não é possível mudar de {atual['status']} para {dados.status}.")
    conn.execute("UPDATE ocorrencias SET status = %s, atualizado_em = now() WHERE id = %s",
                 (dados.status, ocorrencia_id))
    conn.execute(
        "INSERT INTO historico_status (ocorrencia_id, status_anterior, status_novo, observacao, autor_id) "
        "VALUES (%s, %s, %s, %s, %s)",
        (ocorrencia_id, atual["status"], dados.status, dados.observacao, u["id"]))
    return _buscar(conn, ocorrencia_id, u["id"])


@router.get("/{ocorrencia_id}/historico", response_model=list[HistoricoSaida],
            summary="Linha do tempo de status")
def historico(ocorrencia_id: int, u: dict = Depends(usuario_atual), conn: Connection = Depends(conexao)):
    _buscar(conn, ocorrencia_id, u["id"])
    return conn.execute(
        """SELECT h.status_anterior, h.status_novo, h.observacao, a.nome AS autor_nome, h.alterado_em
             FROM historico_status h JOIN usuarios a ON a.id = h.autor_id
            WHERE h.ocorrencia_id = %s ORDER BY h.alterado_em, h.id""", (ocorrencia_id,)).fetchall()


# ------------------------------ Apoios ------------------------------
def _apoios(conn: Connection, ocorrencia_id: int, me: int) -> ApoiosSaida:
    o = _buscar(conn, ocorrencia_id, me)
    return ApoiosSaida(ocorrencia_id=o["id"], apoios_total=o["apoios_total"], apoiado_por_mim=o["apoiado_por_mim"])


@router.get("/{ocorrencia_id}/apoios", response_model=ApoiosSaida, summary="Total de apoios")
def ver_apoios(ocorrencia_id: int, u: dict = Depends(usuario_atual), conn: Connection = Depends(conexao)):
    return _apoios(conn, ocorrencia_id, u["id"])


@router.post("/{ocorrencia_id}/apoios", response_model=ApoiosSaida, status_code=status.HTTP_201_CREATED,
             summary="Apoiar ocorrência (uma vez por conta)")
def apoiar(ocorrencia_id: int, u: dict = Depends(usuario_atual), conn: Connection = Depends(conexao)):
    _buscar(conn, ocorrencia_id, u["id"])
    try:
        conn.execute("INSERT INTO apoios (usuario_id, ocorrencia_id) VALUES (%s, %s)", (u["id"], ocorrencia_id))
    except UniqueViolation:
        raise HTTPException(status.HTTP_409_CONFLICT, "Você já apoiou esta ocorrência.")
    except CheckViolation as e:   # regras do trigger validar_apoio()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, e.diag.message_primary + ".")
    return _apoios(conn, ocorrencia_id, u["id"])


@router.delete("/{ocorrencia_id}/apoios", status_code=status.HTTP_204_NO_CONTENT,
               summary="Retirar o próprio apoio")
def retirar_apoio(ocorrencia_id: int, u: dict = Depends(usuario_atual), conn: Connection = Depends(conexao)):
    apagou = conn.execute("DELETE FROM apoios WHERE usuario_id = %s AND ocorrencia_id = %s",
                          (u["id"], ocorrencia_id)).rowcount
    if not apagou:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Você ainda não apoiou esta ocorrência.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
