"""Módulo do COLABORADOR DE CAMPO: ordens de serviço da equipe.

O colaborador enxerga só as OS da própria equipe. Iniciar e concluir uma OS
muda o status da ocorrência e aparece na linha do tempo do cidadão.
"""
import base64
import binascii
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from psycopg import Connection

from ..db import conexao
from ..esquemas import ConclusaoEntrada, FotoEntrada, MotivoEntrada, PosicaoEntrada
from ..seguranca import exigir_perfil

_colaborador = exigir_perfil("COLABORADOR")
router = APIRouter(prefix="/api/campo", tags=["Campo"], dependencies=[Depends(_colaborador)])

MAX_FOTOS_POR_OS = 6
MAX_BYTES_FOTO = 2 * 1024 * 1024
# Assinatura (primeiros bytes) de cada formato aceito: não confiamos só no nome/tipo informado
_ASSINATURAS = {"image/jpeg": (b"\xff\xd8\xff",), "image/png": (b"\x89PNG\r\n\x1a\n",), "image/webp": (b"RIFF",)}

_SELECT = """
SELECT os.id, os.status, os.instrucoes, os.prazo_em, os.criado_em, os.iniciada_em, os.encerrada_em,
       os.relatorio, os.motivo_encerramento, os.responsavel_id, r.nome AS responsavel_nome,
       os.equipe_id, e.nome AS equipe_nome, (now() > os.prazo_em AND os.encerrada_em IS NULL) AS atrasada,
       o.id AS ocorrencia_id, o.titulo, o.descricao, o.urgencia, o.endereco_referencia,
       c.nome AS categoria_nome, o.apoios_validos,
       ST_Y(o.localizacao) AS latitude, ST_X(o.localizacao) AS longitude,
       (SELECT count(*) FROM os_fotos f WHERE f.os_id = os.id) AS fotos,
       {distancia} AS distancia_m
  FROM ordens_servico os
  JOIN ocorrencias o ON o.id = os.ocorrencia_id
  JOIN categorias  c ON c.id = o.categoria_id
  JOIN equipes     e ON e.id = os.equipe_id
  LEFT JOIN usuarios r ON r.id = os.responsavel_id
"""
_SEM_DISTANCIA = "NULL::float8"
_DISTANCIA = "ST_Distance(o.localizacao::geography, ST_SetSRID(ST_MakePoint(%(lng)s, %(lat)s), 4326)::geography)"


def _equipe(conn: Connection, usuario_id: int) -> dict | None:
    return conn.execute(
        "SELECT e.id, e.nome FROM equipe_membros m JOIN equipes e ON e.id = m.equipe_id WHERE m.usuario_id = %s",
        (usuario_id,)).fetchone()


def _minha_os(conn: Connection, os_id: int, usuario_id: int, travar: bool = False) -> dict:
    """Confere se a OS existe e é da equipe do colaborador. Com travar=True,
    trava primeiro a ocorrência e depois a OS (mesma ordem usada pelo gestor)."""
    os_ = conn.execute(
        """SELECT os.id, os.status, os.ocorrencia_id, os.equipe_id
             FROM ordens_servico os JOIN equipe_membros m ON m.equipe_id = os.equipe_id AND m.usuario_id = %s
            WHERE os.id = %s""", (usuario_id, os_id)).fetchone()
    if not os_:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ordem de serviço não encontrada na sua equipe.")
    if travar:
        conn.execute("SELECT 1 FROM ocorrencias WHERE id = %s FOR UPDATE", (os_["ocorrencia_id"],))
        os_ = conn.execute("SELECT id, status, ocorrencia_id, equipe_id FROM ordens_servico WHERE id = %s FOR UPDATE",
                           (os_id,)).fetchone()
    return os_


def _saida(conn: Connection, os_id: int) -> dict:
    return conn.execute(_SELECT.format(distancia=_SEM_DISTANCIA) + " WHERE os.id = %s", (os_id,)).fetchone()


def _evento(conn: Connection, ocorrencia_id: int, anterior: str, novo: str, observacao: str, autor_id: int) -> None:
    if novo != anterior:
        conn.execute("UPDATE ocorrencias SET status = %s, atualizado_em = now() WHERE id = %s", (novo, ocorrencia_id))
    conn.execute(
        "INSERT INTO historico_status (ocorrencia_id, status_anterior, status_novo, observacao, autor_id) "
        "VALUES (%s, %s, %s, %s, %s)", (ocorrencia_id, anterior, novo, observacao, autor_id))


@router.get("/ordens", summary="Ordens de serviço da minha equipe")
def listar(
    situacao: Literal["ativas", "encerradas"] = "ativas",
    latitude: float | None = Query(None, ge=-90, le=90),
    longitude: float | None = Query(None, ge=-180, le=180),
    u: dict = Depends(_colaborador), conn: Connection = Depends(conexao),
):
    equipe = _equipe(conn, u["id"])
    if not equipe:
        return {"equipe": None, "itens": []}
    tem_posicao = latitude is not None and longitude is not None
    p = {"eq": equipe["id"], "lat": latitude, "lng": longitude}
    if situacao == "ativas":
        # Em execução primeiro; depois a mesma lógica da fila do gestor: urgência, apoios válidos, prazo
        where = "os.status IN ('ATRIBUIDA', 'EM_EXECUCAO')"
        ordem = ("(os.status = 'EM_EXECUCAO') DESC, "
                 "CASE o.urgencia WHEN 'ALTA' THEN 3 WHEN 'MEDIA' THEN 2 ELSE 1 END DESC, "
                 "o.apoios_validos DESC, os.prazo_em ASC")
    else:
        where = "os.status IN ('CONCLUIDA', 'DEVOLVIDA', 'CANCELADA')"
        ordem = "os.encerrada_em DESC"
    itens = conn.execute(
        _SELECT.format(distancia=_DISTANCIA if tem_posicao else _SEM_DISTANCIA)
        + f" WHERE os.equipe_id = %(eq)s AND {where} ORDER BY {ordem} LIMIT 100", p).fetchall()
    return {"equipe": equipe, "itens": itens}


@router.get("/ordens/{os_id}", summary="Detalhe de uma ordem de serviço")
def detalhe(os_id: int, u: dict = Depends(_colaborador), conn: Connection = Depends(conexao)):
    _minha_os(conn, os_id, u["id"])
    os_ = _saida(conn, os_id)
    os_["lista_fotos"] = conn.execute(
        "SELECT id, tipo, criado_em FROM os_fotos WHERE os_id = %s ORDER BY id", (os_id,)).fetchall()
    return os_


@router.post("/ordens/{os_id}/iniciar", summary="Iniciar a execução (ocorrência passa a EM_ANDAMENTO)")
def iniciar(os_id: int, u: dict = Depends(_colaborador), conn: Connection = Depends(conexao)):
    os_ = _minha_os(conn, os_id, u["id"], travar=True)
    if os_["status"] != "ATRIBUIDA":
        raise HTTPException(status.HTTP_409_CONFLICT, "Esta ordem de serviço já foi iniciada ou encerrada.")
    conn.execute("UPDATE ordens_servico SET status = 'EM_EXECUCAO', responsavel_id = %s WHERE id = %s", (u["id"], os_id))
    atual = conn.execute("SELECT status FROM ocorrencias WHERE id = %s", (os_["ocorrencia_id"],)).fetchone()["status"]
    novo = "EM_ANDAMENTO" if atual in ("ABERTA", "EM_ANALISE") else atual
    _evento(conn, os_["ocorrencia_id"], atual, novo, f"Equipe em campo (ordem de serviço nº {os_id}).", u["id"])
    return _saida(conn, os_id)


@router.post("/ordens/{os_id}/concluir", summary="Concluir o serviço (ocorrência passa a RESOLVIDA)")
def concluir(os_id: int, dados: ConclusaoEntrada, u: dict = Depends(_colaborador), conn: Connection = Depends(conexao)):
    os_ = _minha_os(conn, os_id, u["id"], travar=True)
    if os_["status"] != "EM_EXECUCAO":
        raise HTTPException(status.HTTP_409_CONFLICT, "Inicie a ordem de serviço antes de concluir.")
    # Prova de presença: distância entre o aparelho e o local da ocorrência.
    # Fora do raio (ou sem GPS) não bloqueia o trabalho, mas vira alerta para o gestor.
    if dados.latitude is not None and dados.longitude is not None:
        conn.execute(
            """UPDATE ordens_servico os
                  SET status = 'CONCLUIDA', relatorio = %(rel)s,
                      local_conclusao = ST_SetSRID(ST_MakePoint(%(lng)s, %(lat)s), 4326),
                      distancia_conclusao_m = d.m,
                      fora_do_local = d.m > parametro('conclusao_raio_m')
                 FROM (SELECT ST_Distance(o.localizacao::geography,
                                          ST_SetSRID(ST_MakePoint(%(lng)s, %(lat)s), 4326)::geography) AS m
                         FROM ocorrencias o WHERE o.id = %(oc)s) d
                WHERE os.id = %(os)s""",
            {"rel": dados.relatorio, "lat": dados.latitude, "lng": dados.longitude,
             "oc": os_["ocorrencia_id"], "os": os_id})
    else:
        conn.execute("UPDATE ordens_servico SET status = 'CONCLUIDA', relatorio = %s WHERE id = %s",
                     (dados.relatorio, os_id))
    atual = conn.execute("SELECT status FROM ocorrencias WHERE id = %s", (os_["ocorrencia_id"],)).fetchone()["status"]
    _evento(conn, os_["ocorrencia_id"], atual, "RESOLVIDA", f"Serviço concluído: {dados.relatorio}", u["id"])
    return _saida(conn, os_id)


@router.post("/ordens/{os_id}/devolver", summary="Devolver a OS ao gestor (impedimento em campo)")
def devolver(os_id: int, dados: MotivoEntrada, u: dict = Depends(_colaborador), conn: Connection = Depends(conexao)):
    os_ = _minha_os(conn, os_id, u["id"], travar=True)
    if os_["status"] not in ("ATRIBUIDA", "EM_EXECUCAO"):
        raise HTTPException(status.HTTP_409_CONFLICT, "Esta ordem de serviço já foi encerrada.")
    conn.execute("UPDATE ordens_servico SET status = 'DEVOLVIDA', motivo_encerramento = %s WHERE id = %s",
                 (dados.motivo, os_id))
    atual = conn.execute("SELECT status FROM ocorrencias WHERE id = %s", (os_["ocorrencia_id"],)).fetchone()["status"]
    _evento(conn, os_["ocorrencia_id"], atual, atual,
            f"A equipe não conseguiu executar e devolveu a ordem de serviço nº {os_id}: {dados.motivo}", u["id"])
    return _saida(conn, os_id)


@router.post("/ordens/{os_id}/fotos", status_code=status.HTTP_201_CREATED, summary="Anexar foto (antes/depois)")
def anexar_foto(os_id: int, dados: FotoEntrada, u: dict = Depends(_colaborador), conn: Connection = Depends(conexao)):
    os_ = _minha_os(conn, os_id, u["id"], travar=True)
    if os_["status"] not in ("ATRIBUIDA", "EM_EXECUCAO"):
        raise HTTPException(status.HTTP_409_CONFLICT, "Só é possível anexar fotos a uma ordem de serviço ativa.")
    cabecalho, _, b64 = dados.imagem.partition(",")
    mime = cabecalho.removeprefix("data:").removesuffix(";base64")
    try:
        conteudo = base64.b64decode(b64, validate=True)
    except (binascii.Error, ValueError):
        conteudo = b""
    if mime not in _ASSINATURAS or not conteudo.startswith(_ASSINATURAS[mime]):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Envie uma imagem JPEG, PNG ou WebP.")
    if len(conteudo) > MAX_BYTES_FOTO:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "A foto passa de 2 MB.")
    if conn.execute("SELECT count(*) AS n FROM os_fotos WHERE os_id = %s", (os_id,)).fetchone()["n"] >= MAX_FOTOS_POR_OS:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Limite de {MAX_FOTOS_POR_OS} fotos por ordem de serviço.")
    return conn.execute(
        "INSERT INTO os_fotos (os_id, tipo, mime, conteudo, autor_id) VALUES (%s, %s, %s, %s, %s) "
        "RETURNING id, tipo, criado_em", (os_id, dados.tipo, mime, conteudo, u["id"])).fetchone()
