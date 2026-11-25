"""Módulo do GESTOR: fila de prioridade, despacho de ordens de serviço,
painel de indicadores, mapa, equipes e antifraude.

Todas as rotas exigem perfil GESTOR ou ADMIN.
"""
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from psycopg import Connection
from psycopg.errors import CheckViolation, UniqueViolation

from ..db import conexao
from ..esquemas import (ContaSituacaoEntrada, DenunciasAnaliseEntrada, DuplicataEntrada, EquipeEntrada,
                        MembroEntrada, MotivoEntrada, OrdemEntrada, ServidorEntrada, Status, Urgencia,
                        UrgenciaEntrada)
from ..seguranca import exigir_perfil, gerar_hash

_gestor = exigir_perfil("GESTOR", "ADMIN")
router = APIRouter(prefix="/api/gestao", tags=["Gestão"], dependencies=[Depends(_gestor)])

ATIVOS = "('ABERTA', 'EM_ANALISE', 'EM_ANDAMENTO')"
ENCERRADOS = "('RESOLVIDA', 'REJEITADA')"
_PESO = "CASE o.urgencia WHEN 'ALTA' THEN 3 WHEN 'MEDIA' THEN 2 ELSE 1 END"

# Prioridade dinâmica: 1º urgência, 2º apoios VÁLIDOS (validação social sem
# os apoios suspeitos), 3º quem espera há mais tempo. A mesma ordem do índice
# parcial ocorrencias_fila_ix, então a fila sai pronta do índice.
ORDEM_FILA = f"{_PESO} DESC, o.apoios_validos DESC, o.criado_em ASC"

# Situação do prazo (SLA) calculada no banco, a partir de sla_urgencia
_SLA = f"""
CASE WHEN o.status IN {ENCERRADOS} THEN
          CASE WHEN o.encerrado_em <= o.criado_em + make_interval(hours => s.prazo_solucao_h)
               THEN 'CUMPRIDO' ELSE 'DESCUMPRIDO' END
     WHEN now() > o.criado_em + make_interval(hours => s.prazo_solucao_h) THEN 'ATRASADA'
     WHEN o.status = 'ABERTA' AND now() > o.criado_em + make_interval(hours => s.prazo_resposta_h) THEN 'SEM_RESPOSTA'
     WHEN now() > o.criado_em + make_interval(hours => s.prazo_solucao_h) * 0.75 THEN 'VENCENDO'
     ELSE 'NO_PRAZO' END"""

_SELECT = f"""
SELECT o.id, o.titulo, o.descricao, o.urgencia, o.urgencia_revisada, o.status,
       o.categoria_id, c.nome AS categoria_nome, o.usuario_id, u.nome AS autor_nome,
       o.endereco_referencia, ST_Y(o.localizacao) AS latitude, ST_X(o.localizacao) AS longitude,
       o.apoios_total, o.apoios_validos, o.denuncias_pendentes, o.duplicada_de,
       o.criado_em, o.atualizado_em, o.primeira_resposta_em, o.encerrado_em,
       o.criado_em + make_interval(hours => s.prazo_resposta_h) AS prazo_resposta_em,
       o.criado_em + make_interval(hours => s.prazo_solucao_h)  AS prazo_solucao_em,
       {_SLA} AS sla,
       os.id AS os_id, os.status AS os_status, os.prazo_em AS os_prazo_em,
       os.equipe_id, e.nome AS equipe_nome
  FROM ocorrencias o
  JOIN categorias   c ON c.id = o.categoria_id
  JOIN usuarios     u ON u.id = o.usuario_id
  JOIN sla_urgencia s ON s.urgencia = o.urgencia
  LEFT JOIN ordens_servico os ON os.ocorrencia_id = o.id AND os.status IN ('ATRIBUIDA', 'EM_EXECUCAO')
  LEFT JOIN equipes e ON e.id = os.equipe_id
"""


def auditar(conn: Connection, autor_id: int, acao: str, *, ocorrencia_id: int | None = None,
            usuario_alvo_id: int | None = None, anterior=None, novo=None, motivo: str | None = None) -> None:
    conn.execute(
        "INSERT INTO auditoria (ocorrencia_id, usuario_alvo_id, acao, valor_anterior, valor_novo, motivo, autor_id) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s)",
        (ocorrencia_id, usuario_alvo_id, acao, anterior, novo, motivo, autor_id))


def _travar(conn: Connection, ocorrencia_id: int) -> dict:
    """Trava a ocorrência (FOR UPDATE): duas decisões simultâneas não se atropelam."""
    o = conn.execute(
        "SELECT id, usuario_id, categoria_id, status, urgencia, criado_em FROM ocorrencias WHERE id = %s FOR UPDATE",
        (ocorrencia_id,)).fetchone()
    if not o:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ocorrência não encontrada.")
    return o


def _evento(conn: Connection, ocorrencia_id: int, anterior: str, novo: str, observacao: str, autor_id: int) -> None:
    """Linha do tempo que o cidadão acompanha (historico_status)."""
    conn.execute(
        "INSERT INTO historico_status (ocorrencia_id, status_anterior, status_novo, observacao, autor_id) "
        "VALUES (%s, %s, %s, %s, %s)", (ocorrencia_id, anterior, novo, observacao, autor_id))


# ============================== Fila de prioridade ==============================
@router.get("/fila", summary="Fila de prioridade (urgência, apoios válidos, tempo de espera)")
def fila(
    situacao: Literal["ativas", "todas"] = "ativas",
    status_: Status | None = Query(None, alias="status"),
    categoria_id: int | None = None,
    urgencia: Urgencia | None = None,
    atrasadas: bool = Query(False, description="Só as que estouraram o prazo de solução"),
    sem_os: bool = Query(False, description="Só as que ainda não têm ordem de serviço ativa"),
    limite: int = Query(50, ge=1, le=200),
    deslocamento: int = Query(0, ge=0),
    conn: Connection = Depends(conexao),
):
    conn.execute("SELECT revalidar_apoios()")      # libera apoios de contas que cumpriram a carência
    filtros, p = [], {"lim": limite, "off": deslocamento}
    if situacao == "ativas":
        filtros.append(f"o.status IN {ATIVOS}")
    if status_:
        filtros.append("o.status = %(st)s"); p["st"] = status_
    if categoria_id is not None:
        filtros.append("o.categoria_id = %(cat)s"); p["cat"] = categoria_id
    if urgencia:
        filtros.append("o.urgencia = %(urg)s"); p["urg"] = urgencia
    if atrasadas:
        filtros.append(f"o.status IN {ATIVOS} AND now() > o.criado_em + make_interval(hours => s.prazo_solucao_h)")
    if sem_os:
        filtros.append("os.id IS NULL")
    where = (" WHERE " + " AND ".join(filtros)) if filtros else ""
    ordem = f"(o.status IN {ENCERRADOS}), {ORDEM_FILA}" if situacao == "todas" else ORDEM_FILA
    total = conn.execute(
        "SELECT count(*) AS n FROM ocorrencias o JOIN sla_urgencia s ON s.urgencia = o.urgencia "
        "LEFT JOIN ordens_servico os ON os.ocorrencia_id = o.id AND os.status IN ('ATRIBUIDA', 'EM_EXECUCAO')"
        + where, p).fetchone()["n"]
    itens = conn.execute(f"{_SELECT}{where} ORDER BY {ordem} LIMIT %(lim)s OFFSET %(off)s", p).fetchall()
    for i, item in enumerate(itens):
        item["posicao"] = deslocamento + i + 1
    return {"total": total, "itens": itens}


@router.get("/ocorrencias/{ocorrencia_id}", summary="Ficha completa da ocorrência para decisão")
def ficha(ocorrencia_id: int, conn: Connection = Depends(conexao)):
    o = conn.execute(_SELECT + " WHERE o.id = %s", (ocorrencia_id,)).fetchone()
    if not o:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ocorrência não encontrada.")
    o["historico"] = conn.execute(
        """SELECT h.status_anterior, h.status_novo, h.observacao, a.nome AS autor_nome, h.alterado_em
             FROM historico_status h JOIN usuarios a ON a.id = h.autor_id
            WHERE h.ocorrencia_id = %s ORDER BY h.alterado_em, h.id""", (ocorrencia_id,)).fetchall()
    o["auditoria"] = conn.execute(
        """SELECT x.acao, x.valor_anterior, x.valor_novo, x.motivo, a.nome AS autor_nome, x.criado_em
             FROM auditoria x JOIN usuarios a ON a.id = x.autor_id
            WHERE x.ocorrencia_id = %s ORDER BY x.criado_em, x.id""", (ocorrencia_id,)).fetchall()
    o["ordens"] = conn.execute(
        """SELECT os.id, os.status, os.instrucoes, os.prazo_em, os.criado_em, os.iniciada_em, os.encerrada_em,
                  os.relatorio, os.motivo_encerramento, os.distancia_conclusao_m, os.fora_do_local,
                  (os.status = 'CONCLUIDA' AND os.local_conclusao IS NULL) AS sem_gps,
                  e.nome AS equipe_nome, r.nome AS responsavel_nome,
                  COALESCE((SELECT json_agg(json_build_object('id', f.id, 'tipo', f.tipo) ORDER BY f.id)
                              FROM os_fotos f WHERE f.os_id = os.id), '[]'::json) AS fotos
             FROM ordens_servico os JOIN equipes e ON e.id = os.equipe_id
             LEFT JOIN usuarios r ON r.id = os.responsavel_id
            WHERE os.ocorrencia_id = %s ORDER BY os.id DESC""", (ocorrencia_id,)).fetchall()
    o["denuncias"] = conn.execute(
        """SELECT d.id, d.motivo, d.detalhe, d.situacao, d.criado_em, a.nome AS autor_nome
             FROM denuncias d JOIN usuarios a ON a.id = d.usuario_id
            WHERE d.ocorrencia_id = %s ORDER BY d.criado_em""", (ocorrencia_id,)).fetchall()
    o["apoios"] = conn.execute(
        """SELECT count(*) AS total,
                  count(*) FILTER (WHERE a.valido) AS validos,
                  count(*) FILTER (WHERE a.motivo_invalidez = 'CONTA_NOVA') AS em_carencia,
                  count(*) FILTER (WHERE a.motivo_invalidez = 'CONTA_SUSPENSA') AS de_contas_suspensas,
                  count(*) FILTER (WHERE a.motivo_invalidez = 'INVALIDADO_GESTOR') AS invalidados,
                  count(*) FILTER (WHERE a.motivo_invalidez IS DISTINCT FROM 'INVALIDADO_GESTOR'
                                     AND a.criado_em - u.criado_em
                                         < make_interval(hours => parametro('apoio_carencia_conta_h')::int)) AS suspeitos
             FROM apoios a JOIN usuarios u ON u.id = a.usuario_id
            WHERE a.ocorrencia_id = %s""", (ocorrencia_id,)).fetchone()
    # Mesma categoria, bem perto e ainda em aberto: provável pedido repetido
    o["possiveis_duplicatas"] = conn.execute(
        f"""SELECT b.id, b.titulo, b.status, b.apoios_validos, b.criado_em, ub.nome AS autor_nome,
                   round(ST_Distance(b.localizacao::geography, a.localizacao::geography)::numeric) AS distancia_m
              FROM ocorrencias a
              JOIN ocorrencias b ON b.id <> a.id AND b.categoria_id = a.categoria_id AND b.status IN {ATIVOS}
                                AND ST_DWithin(b.localizacao::geography, a.localizacao::geography,
                                               parametro('duplicata_raio_m')::float8)
              JOIN usuarios ub ON ub.id = b.usuario_id
             WHERE a.id = %s ORDER BY distancia_m LIMIT 5""", (ocorrencia_id,)).fetchall()
    o["autor"] = conn.execute(
        """SELECT u.id, u.nome, u.ativo, u.criado_em,
                  count(o.id) AS ocorrencias,
                  count(o.id) FILTER (WHERE o.status = 'REJEITADA') AS rejeitadas
             FROM usuarios u LEFT JOIN ocorrencias o ON o.usuario_id = u.id
            WHERE u.id = %s GROUP BY u.id""", (o["usuario_id"],)).fetchone()
    return o


# ============================== Decisões do gestor ==============================
@router.patch("/ocorrencias/{ocorrencia_id}/urgencia", summary="Reclassificar a urgência (com motivo e auditoria)")
def reclassificar(ocorrencia_id: int, dados: UrgenciaEntrada,
                  g: dict = Depends(_gestor), conn: Connection = Depends(conexao)):
    """A urgência informada pelo cidadão é só uma sugestão: quem decide a
    posição na fila é a prefeitura. Toda mudança fica na auditoria."""
    o = _travar(conn, ocorrencia_id)
    if o["status"] in ("RESOLVIDA", "REJEITADA"):
        raise HTTPException(status.HTTP_409_CONFLICT, "Ocorrência encerrada não pode ser reclassificada.")
    conn.execute("UPDATE ocorrencias SET urgencia = %s, urgencia_revisada = TRUE, atualizado_em = now() WHERE id = %s",
                 (dados.urgencia, ocorrencia_id))
    auditar(conn, g["id"], "URGENCIA", ocorrencia_id=ocorrencia_id,
            anterior=o["urgencia"], novo=dados.urgencia, motivo=dados.motivo)
    return ficha(ocorrencia_id, conn)


@router.post("/ocorrencias/{ocorrencia_id}/duplicata", summary="Unificar com outra ocorrência do mesmo problema")
def unificar(ocorrencia_id: int, dados: DuplicataEntrada,
             g: dict = Depends(_gestor), conn: Connection = Depends(conexao)):
    """Encerra esta ocorrência como duplicata e leva os apoios dela (e o autor)
    para a principal: a demanda real do bairro não se perde nem conta em dobro."""
    if dados.principal_id == ocorrencia_id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Escolha outra ocorrência como principal.")
    # Trava sempre na mesma ordem (menor id primeiro) para não haver deadlock
    travadas = {i: _travar(conn, i) for i in sorted((ocorrencia_id, dados.principal_id))}
    dup, principal = travadas[ocorrencia_id], travadas[dados.principal_id]
    if dup["status"] in ("RESOLVIDA", "REJEITADA") or principal["status"] in ("RESOLVIDA", "REJEITADA"):
        raise HTTPException(status.HTTP_409_CONFLICT, "As duas ocorrências precisam estar em aberto.")
    conn.execute("UPDATE ocorrencias SET status = 'REJEITADA', duplicada_de = %s, atualizado_em = now() WHERE id = %s",
                 (principal["id"], ocorrencia_id))
    _evento(conn, ocorrencia_id, dup["status"], "REJEITADA",
            f"Unificada com a ocorrência nº {principal['id']}, que trata do mesmo problema. "
            "Seu apoio foi transferido para ela.", g["id"])
    try:
        with conn.transaction():          # savepoint: se a transferência falhar, a unificação continua valendo
            conn.execute(
                """INSERT INTO apoios (usuario_id, ocorrencia_id, criado_em)
                   SELECT x.usuario_id, %(principal)s, x.criado_em
                     FROM (SELECT usuario_id, criado_em FROM apoios
                            WHERE ocorrencia_id = %(dup)s AND motivo_invalidez IS DISTINCT FROM 'INVALIDADO_GESTOR'
                           UNION ALL
                           SELECT usuario_id, criado_em FROM ocorrencias WHERE id = %(dup)s) x
                    WHERE x.usuario_id <> %(dono)s
                   ON CONFLICT DO NOTHING""",
                {"principal": principal["id"], "dup": ocorrencia_id, "dono": principal["usuario_id"]})
    except CheckViolation:
        pass
    auditar(conn, g["id"], "DUPLICATA", ocorrencia_id=ocorrencia_id, novo=str(principal["id"]))
    conn.execute("UPDATE denuncias SET situacao = 'PROCEDENTE', analisada_por = %s, analisada_em = now() "
                 "WHERE ocorrencia_id = %s AND situacao = 'PENDENTE' AND motivo = 'DUPLICADA'", (g["id"], ocorrencia_id))
    return ficha(principal["id"], conn)


@router.post("/ocorrencias/{ocorrencia_id}/apoios/invalidar-suspeitos",
             summary="Tirar do ranking os apoios dados por contas recém-criadas")
def invalidar_suspeitos(ocorrencia_id: int, dados: MotivoEntrada,
                        g: dict = Depends(_gestor), conn: Connection = Depends(conexao)):
    _travar(conn, ocorrencia_id)
    n = conn.execute(
        """UPDATE apoios a SET valido = FALSE, motivo_invalidez = 'INVALIDADO_GESTOR'
             FROM usuarios u
            WHERE u.id = a.usuario_id AND a.ocorrencia_id = %s
              AND a.motivo_invalidez IS DISTINCT FROM 'INVALIDADO_GESTOR'
              AND a.criado_em - u.criado_em < make_interval(hours => parametro('apoio_carencia_conta_h')::int)""",
        (ocorrencia_id,)).rowcount
    if n:
        auditar(conn, g["id"], "APOIOS_INVALIDADOS", ocorrencia_id=ocorrencia_id, novo=str(n), motivo=dados.motivo)
    return {"invalidados": n, "ocorrencia": ficha(ocorrencia_id, conn)}


@router.post("/ocorrencias/{ocorrencia_id}/denuncias/analisar", summary="Dar parecer às denúncias pendentes")
def analisar_denuncias(ocorrencia_id: int, dados: DenunciasAnaliseEntrada,
                       g: dict = Depends(_gestor), conn: Connection = Depends(conexao)):
    _travar(conn, ocorrencia_id)
    n = conn.execute(
        "UPDATE denuncias SET situacao = %s, analisada_por = %s, analisada_em = now() "
        "WHERE ocorrencia_id = %s AND situacao = 'PENDENTE'",
        ("PROCEDENTE" if dados.procedente else "IMPROCEDENTE", g["id"], ocorrencia_id)).rowcount
    if n:
        auditar(conn, g["id"], "DENUNCIAS", ocorrencia_id=ocorrencia_id,
                novo=f"{n} {'procedente(s)' if dados.procedente else 'improcedente(s)'}")
    return {"analisadas": n, "ocorrencia": ficha(ocorrencia_id, conn)}


# ============================== Ordens de serviço ==============================
@router.post("/ocorrencias/{ocorrencia_id}/ordens", status_code=status.HTTP_201_CREATED,
             summary="Despachar: criar ordem de serviço para uma equipe")
def despachar(ocorrencia_id: int, dados: OrdemEntrada,
              g: dict = Depends(_gestor), conn: Connection = Depends(conexao)):
    o = _travar(conn, ocorrencia_id)
    if o["status"] in ("RESOLVIDA", "REJEITADA"):
        raise HTTPException(status.HTTP_409_CONFLICT, "Ocorrência encerrada não recebe ordem de serviço.")
    equipe = conn.execute("SELECT id, nome FROM equipes WHERE id = %s AND ativa", (dados.equipe_id,)).fetchone()
    if not equipe:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Equipe inválida ou inativa.")
    if dados.responsavel_id is not None and not conn.execute(
            "SELECT 1 FROM equipe_membros WHERE usuario_id = %s AND equipe_id = %s",
            (dados.responsavel_id, equipe["id"])).fetchone():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "O responsável precisa ser membro da equipe.")
    agora = datetime.now(timezone.utc)
    prazo = dados.prazo_em
    if prazo is None:
        horas = conn.execute("SELECT prazo_solucao_h FROM sla_urgencia WHERE urgencia = %s",
                             (o["urgencia"],)).fetchone()["prazo_solucao_h"]
        prazo = o["criado_em"] + timedelta(hours=horas)
        if prazo <= agora:                       # SLA já estourado: 24 h para a equipe executar
            prazo = agora + timedelta(hours=24)
    elif prazo.tzinfo is None or prazo <= agora:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "O prazo precisa ser uma data futura (com fuso).")
    try:
        with conn.transaction():
            os_ = conn.execute(
                "INSERT INTO ordens_servico (ocorrencia_id, equipe_id, responsavel_id, instrucoes, prazo_em, criado_por) "
                "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
                (ocorrencia_id, equipe["id"], dados.responsavel_id, (dados.instrucoes or "").strip() or None,
                 prazo, g["id"])).fetchone()
    except UniqueViolation:                      # índice único parcial os_ativa_uk
        raise HTTPException(status.HTTP_409_CONFLICT, "Esta ocorrência já tem uma ordem de serviço ativa.")
    # ABERTA vira EM_ANALISE; nos outros casos o status fica e o cidadão vê o evento na linha do tempo
    novo = "EM_ANALISE" if o["status"] == "ABERTA" else o["status"]
    if novo != o["status"]:
        conn.execute("UPDATE ocorrencias SET status = %s, atualizado_em = now() WHERE id = %s", (novo, ocorrencia_id))
    _evento(conn, ocorrencia_id, o["status"], novo,
            f"Ordem de serviço nº {os_['id']} atribuída à equipe {equipe['nome']}.", g["id"])
    return ficha(ocorrencia_id, conn)


@router.post("/ordens/{os_id}/cancelar", summary="Cancelar uma ordem de serviço ativa")
def cancelar_os(os_id: int, dados: MotivoEntrada, g: dict = Depends(_gestor), conn: Connection = Depends(conexao)):
    alvo = conn.execute("SELECT ocorrencia_id FROM ordens_servico WHERE id = %s", (os_id,)).fetchone()
    if not alvo:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ordem de serviço não encontrada.")
    o = _travar(conn, alvo["ocorrencia_id"])
    os_ = conn.execute("SELECT status FROM ordens_servico WHERE id = %s FOR UPDATE", (os_id,)).fetchone()
    if os_["status"] not in ("ATRIBUIDA", "EM_EXECUCAO"):
        raise HTTPException(status.HTTP_409_CONFLICT, "Esta ordem de serviço já foi encerrada.")
    conn.execute("UPDATE ordens_servico SET status = 'CANCELADA', motivo_encerramento = %s WHERE id = %s",
                 (dados.motivo, os_id))
    _evento(conn, o["id"], o["status"], o["status"], f"Ordem de serviço nº {os_id} cancelada: {dados.motivo}", g["id"])
    return ficha(o["id"], conn)


# ============================== Painel (KPIs) ==============================
@router.get("/painel", summary="Indicadores: tempo de resposta, SLA, validação e produtividade")
def painel(dias: int = Query(30, ge=1, le=365), conn: Connection = Depends(conexao)):
    p = {"dias": dias}
    ini = "now() - make_interval(days => %(dias)s)"
    horas = "extract(epoch FROM {})/3600.0"
    resumo = conn.execute(
        f"""SELECT count(*) FILTER (WHERE o.status = 'ABERTA')       AS abertas,
                   count(*) FILTER (WHERE o.status = 'EM_ANALISE')   AS em_analise,
                   count(*) FILTER (WHERE o.status = 'EM_ANDAMENTO') AS em_andamento,
                   count(*) FILTER (WHERE o.status IN {ATIVOS}
                                      AND now() > o.criado_em + make_interval(hours => s.prazo_solucao_h)) AS atrasadas,
                   count(*) FILTER (WHERE o.status = 'ABERTA'
                                      AND now() > o.criado_em + make_interval(hours => s.prazo_resposta_h)) AS sem_resposta,
                   count(*) FILTER (WHERE o.criado_em >= {ini}) AS novas,
                   count(*) FILTER (WHERE o.status = 'RESOLVIDA' AND o.encerrado_em >= {ini}) AS resolvidas,
                   count(*) FILTER (WHERE o.status = 'REJEITADA' AND o.encerrado_em >= {ini}) AS rejeitadas,
                   round((avg({horas.format('o.primeira_resposta_em - o.criado_em')})
                          FILTER (WHERE o.primeira_resposta_em >= {ini}))::numeric, 1) AS resposta_media_h,
                   round((percentile_cont(0.5) WITHIN GROUP (ORDER BY {horas.format('o.primeira_resposta_em - o.criado_em')})
                          FILTER (WHERE o.primeira_resposta_em >= {ini}))::numeric, 1) AS resposta_mediana_h,
                   round((avg({horas.format('o.encerrado_em - o.criado_em')})
                          FILTER (WHERE o.status = 'RESOLVIDA' AND o.encerrado_em >= {ini}))::numeric, 1) AS solucao_media_h,
                   round((percentile_cont(0.5) WITHIN GROUP (ORDER BY {horas.format('o.encerrado_em - o.criado_em')})
                          FILTER (WHERE o.status = 'RESOLVIDA' AND o.encerrado_em >= {ini}))::numeric, 1) AS solucao_mediana_h,
                   count(*) FILTER (WHERE o.status = 'RESOLVIDA' AND o.encerrado_em >= {ini}
                                      AND o.encerrado_em <= o.criado_em + make_interval(hours => s.prazo_solucao_h)) AS no_prazo
              FROM ocorrencias o JOIN sla_urgencia s ON s.urgencia = o.urgencia
             WHERE o.status IN {ATIVOS} OR o.criado_em >= {ini} OR o.encerrado_em >= {ini}""", p).fetchone()
    resumo["sla_pct"] = round(100 * resumo["no_prazo"] / resumo["resolvidas"]) if resumo["resolvidas"] else None
    decididas = resumo["resolvidas"] + resumo["rejeitadas"]
    resumo["validacao_pct"] = round(100 * resumo["resolvidas"] / decididas) if decididas else None

    # Entradas x resolvidas por dia (dias sem movimento aparecem com zero)
    serie = conn.execute(
        f"""WITH d AS (SELECT generate_series((({ini}) AT TIME ZONE 'America/Sao_Paulo')::date,
                                              (now() AT TIME ZONE 'America/Sao_Paulo')::date, interval '1 day')::date AS dia),
                 n AS (SELECT (criado_em AT TIME ZONE 'America/Sao_Paulo')::date AS dia, count(*) AS q
                         FROM ocorrencias WHERE criado_em >= {ini} - interval '1 day' GROUP BY 1),
                 r AS (SELECT (encerrado_em AT TIME ZONE 'America/Sao_Paulo')::date AS dia, count(*) AS q
                         FROM ocorrencias WHERE status = 'RESOLVIDA' AND encerrado_em >= {ini} - interval '1 day' GROUP BY 1)
            SELECT d.dia, COALESCE(n.q, 0) AS novas, COALESCE(r.q, 0) AS resolvidas
              FROM d LEFT JOIN n USING (dia) LEFT JOIN r USING (dia) ORDER BY d.dia""", p).fetchall()

    categorias = conn.execute(
        f"""SELECT c.id, c.nome,
                   count(o.id) FILTER (WHERE o.status IN {ATIVOS}) AS ativas,
                   count(o.id) FILTER (WHERE o.criado_em >= {ini}) AS novas,
                   round((avg({horas.format('o.encerrado_em - o.criado_em')})
                          FILTER (WHERE o.status = 'RESOLVIDA' AND o.encerrado_em >= {ini}))::numeric, 1) AS solucao_media_h
              FROM categorias c
              LEFT JOIN ocorrencias o ON o.categoria_id = c.id
                                     AND (o.status IN {ATIVOS} OR o.criado_em >= {ini} OR o.encerrado_em >= {ini})
             WHERE c.ativa GROUP BY c.id ORDER BY ativas DESC, c.nome""", p).fetchall()

    equipes = conn.execute(
        f"""SELECT e.id, e.nome,
                   (SELECT count(*) FROM equipe_membros m WHERE m.equipe_id = e.id) AS membros,
                   count(os.id) FILTER (WHERE os.status IN ('ATRIBUIDA', 'EM_EXECUCAO')) AS ativas,
                   count(os.id) FILTER (WHERE os.status IN ('ATRIBUIDA', 'EM_EXECUCAO') AND now() > os.prazo_em) AS atrasadas,
                   count(os.id) FILTER (WHERE os.status = 'CONCLUIDA' AND os.encerrada_em >= {ini}) AS concluidas,
                   count(os.id) FILTER (WHERE os.status = 'DEVOLVIDA' AND os.encerrada_em >= {ini}) AS devolvidas,
                   round((avg({horas.format('os.encerrada_em - os.criado_em')})
                          FILTER (WHERE os.status = 'CONCLUIDA' AND os.encerrada_em >= {ini}))::numeric, 1) AS execucao_media_h
              FROM equipes e LEFT JOIN ordens_servico os ON os.equipe_id = e.id
             WHERE e.ativa GROUP BY e.id ORDER BY e.nome""", p).fetchall()

    # Densidade por região: grade de ~550 m (0,005 grau) sobre as ocorrências em aberto
    regioes = conn.execute(
        f"""SELECT count(*) AS ativas,
                   count(*) FILTER (WHERE o.urgencia = 'ALTA') AS urgentes,
                   round(avg(ST_Y(o.localizacao))::numeric, 5) AS latitude,
                   round(avg(ST_X(o.localizacao))::numeric, 5) AS longitude,
                   (array_agg(o.endereco_referencia ORDER BY o.apoios_validos DESC, o.criado_em))[1] AS referencia
              FROM ocorrencias o WHERE o.status IN {ATIVOS}
             GROUP BY ST_SnapToGrid(o.localizacao, 0.005)
             ORDER BY ativas DESC, urgentes DESC LIMIT 6""").fetchall()

    # Taxa de validação por usuário: das ocorrências já decididas, quantas a prefeitura confirmou
    usuarios = conn.execute(
        f"""SELECT u.id, u.nome, u.ativo,
                   count(*) AS registradas,
                   count(*) FILTER (WHERE o.status = 'RESOLVIDA') AS confirmadas,
                   count(*) FILTER (WHERE o.status = 'REJEITADA') AS rejeitadas,
                   count(*) FILTER (WHERE o.status IN {ATIVOS})   AS em_aberto,
                   COALESCE(sum(o.apoios_validos), 0) AS apoios_recebidos
              FROM ocorrencias o JOIN usuarios u ON u.id = o.usuario_id
             WHERE o.criado_em >= {ini}
             GROUP BY u.id ORDER BY registradas DESC, u.nome LIMIT 10""", p).fetchall()
    for x in usuarios:
        dec = x["confirmadas"] + x["rejeitadas"]
        x["validacao_pct"] = round(100 * x["confirmadas"] / dec) if dec else None

    return {"dias": dias, "gerado_em": datetime.now(timezone.utc), "resumo": resumo, "serie": serie,
            "categorias": categorias, "equipes": equipes, "regioes": regioes, "usuarios": usuarios}


# ============================== Mapa ==============================
@router.get("/mapa", summary="Pontos e densidade para as camadas do mapa")
def mapa(dias_encerradas: int = Query(30, ge=0, le=365), conn: Connection = Depends(conexao)):
    pontos = conn.execute(
        f"""SELECT o.id, o.titulo, o.status, o.urgencia, c.nome AS categoria_nome, o.endereco_referencia,
                   ST_Y(o.localizacao) AS latitude, ST_X(o.localizacao) AS longitude, o.apoios_validos,
                   (o.status IN {ATIVOS} AND now() > o.criado_em + make_interval(hours => s.prazo_solucao_h)) AS atrasada,
                   e.nome AS equipe_nome
              FROM ocorrencias o
              JOIN categorias c ON c.id = o.categoria_id
              JOIN sla_urgencia s ON s.urgencia = o.urgencia
              LEFT JOIN ordens_servico os ON os.ocorrencia_id = o.id AND os.status IN ('ATRIBUIDA', 'EM_EXECUCAO')
              LEFT JOIN equipes e ON e.id = os.equipe_id
             WHERE o.status IN {ATIVOS} OR o.encerrado_em >= now() - make_interval(days => %s)
             ORDER BY o.id DESC LIMIT 5000""", (dias_encerradas,)).fetchall()
    celulas = conn.execute(
        f"""SELECT count(*) AS ativas, avg(ST_Y(localizacao)) AS latitude, avg(ST_X(localizacao)) AS longitude
              FROM ocorrencias WHERE status IN {ATIVOS}
             GROUP BY ST_SnapToGrid(localizacao, 0.005) ORDER BY ativas DESC LIMIT 500""").fetchall()
    return {"pontos": pontos, "celulas": celulas}


# ============================== Equipes e contas ==============================
@router.get("/equipes", summary="Equipes, membros e carga de trabalho")
def equipes(conn: Connection = Depends(conexao)):
    return conn.execute(
        """SELECT e.id, e.nome, e.categoria_id, c.nome AS categoria_nome, e.ativa,
                  COALESCE((SELECT json_agg(json_build_object('id', u.id, 'nome', u.nome, 'ativo', u.ativo) ORDER BY u.nome)
                              FROM equipe_membros m JOIN usuarios u ON u.id = m.usuario_id
                             WHERE m.equipe_id = e.id), '[]'::json) AS membros,
                  (SELECT count(*) FROM ordens_servico os
                    WHERE os.equipe_id = e.id AND os.status IN ('ATRIBUIDA', 'EM_EXECUCAO')) AS os_ativas
             FROM equipes e LEFT JOIN categorias c ON c.id = e.categoria_id
            ORDER BY e.ativa DESC, e.nome""").fetchall()


@router.post("/equipes", status_code=status.HTTP_201_CREATED, summary="Criar equipe")
def criar_equipe(dados: EquipeEntrada, conn: Connection = Depends(conexao)):
    if dados.categoria_id is not None and not conn.execute(
            "SELECT 1 FROM categorias WHERE id = %s", (dados.categoria_id,)).fetchone():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Categoria inválida.")
    try:
        with conn.transaction():
            return conn.execute("INSERT INTO equipes (nome, categoria_id) VALUES (%s, %s) RETURNING id, nome",
                                (dados.nome, dados.categoria_id)).fetchone()
    except UniqueViolation:
        raise HTTPException(status.HTTP_409_CONFLICT, "Já existe uma equipe com esse nome.")


@router.post("/equipes/{equipe_id}/membros", summary="Colocar (ou transferir) um colaborador na equipe")
def incluir_membro(equipe_id: int, dados: MembroEntrada, conn: Connection = Depends(conexao)):
    if not conn.execute("SELECT 1 FROM equipes WHERE id = %s AND ativa", (equipe_id,)).fetchone():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Equipe não encontrada.")
    try:
        with conn.transaction():
            conn.execute(
                "INSERT INTO equipe_membros (usuario_id, equipe_id) VALUES (%s, %s) "
                "ON CONFLICT (usuario_id) DO UPDATE SET equipe_id = EXCLUDED.equipe_id, desde = now()",
                (dados.usuario_id, equipe_id))
    except CheckViolation as e:               # trigger validar_membro()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, e.diag.message_primary + ".")
    return {"equipe_id": equipe_id, "usuario_id": dados.usuario_id}


@router.delete("/equipes/{equipe_id}/membros/{usuario_id}", status_code=status.HTTP_204_NO_CONTENT,
               summary="Tirar um colaborador da equipe")
def remover_membro(equipe_id: int, usuario_id: int, conn: Connection = Depends(conexao)):
    if not conn.execute("DELETE FROM equipe_membros WHERE equipe_id = %s AND usuario_id = %s",
                        (equipe_id, usuario_id)).rowcount:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Este colaborador não está na equipe.")


@router.get("/usuarios", summary="Contas (sem CPF; e-mail só de servidores)")
def usuarios(perfil: Literal["CIDADAO", "COLABORADOR", "GESTOR", "ADMIN"] | None = None,
             limite: int = Query(200, ge=1, le=500), conn: Connection = Depends(conexao)):
    # LGPD: o gestor não precisa do CPF de ninguém nem do e-mail do cidadão para trabalhar
    return conn.execute(
        """SELECT u.id, u.nome, u.perfil, u.ativo, u.criado_em,
                  CASE WHEN u.perfil <> 'CIDADAO' THEN u.email END AS email,
                  m.equipe_id, e.nome AS equipe_nome
             FROM usuarios u
             LEFT JOIN equipe_membros m ON m.usuario_id = u.id
             LEFT JOIN equipes e ON e.id = m.equipe_id
            WHERE (%(perfil)s::text IS NULL OR u.perfil = %(perfil)s)
            ORDER BY u.ativo DESC, u.nome LIMIT %(lim)s""", {"perfil": perfil, "lim": limite}).fetchall()


@router.post("/usuarios", status_code=status.HTTP_201_CREATED, summary="Criar conta de colaborador ou gestor")
def criar_servidor(dados: ServidorEntrada, g: dict = Depends(_gestor), conn: Connection = Depends(conexao)):
    if dados.perfil == "GESTOR" and g["perfil"] != "ADMIN":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Só o administrador cria contas de gestor.")
    try:
        with conn.transaction():
            novo = conn.execute(
                "INSERT INTO usuarios (nome, cpf, email, senha_hash, data_nascimento, perfil) "
                "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id, nome, email, perfil",
                (dados.nome, dados.cpf, dados.email, gerar_hash(dados.senha), dados.data_nascimento,
                 dados.perfil)).fetchone()
            if dados.equipe_id is not None and dados.perfil == "COLABORADOR":
                if not conn.execute("SELECT 1 FROM equipes WHERE id = %s AND ativa", (dados.equipe_id,)).fetchone():
                    raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Equipe inválida ou inativa.")
                conn.execute("INSERT INTO equipe_membros (usuario_id, equipe_id) VALUES (%s, %s)",
                             (novo["id"], dados.equipe_id))
    except UniqueViolation:
        raise HTTPException(status.HTTP_409_CONFLICT, "CPF ou e-mail já cadastrado.")
    auditar(conn, g["id"], "CONTA_CRIADA", usuario_alvo_id=novo["id"], novo=dados.perfil)
    return novo


@router.patch("/usuarios/{usuario_id}", summary="Suspender ou reativar uma conta (com motivo)")
def situacao_da_conta(usuario_id: int, dados: ContaSituacaoEntrada,
                      g: dict = Depends(_gestor), conn: Connection = Depends(conexao)):
    """Suspender corta o acesso na hora e tira do ranking todos os apoios da conta
    (trigger apoios_seguem_conta). Reativar devolve os dois."""
    alvo = conn.execute("SELECT id, nome, perfil, ativo FROM usuarios WHERE id = %s FOR UPDATE", (usuario_id,)).fetchone()
    if not alvo:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conta não encontrada.")
    if alvo["id"] == g["id"]:
        raise HTTPException(status.HTTP_409_CONFLICT, "Você não pode suspender a própria conta.")
    if alvo["perfil"] in ("GESTOR", "ADMIN") and g["perfil"] != "ADMIN":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Só o administrador altera contas de gestão.")
    if alvo["ativo"] != dados.ativo:
        conn.execute("UPDATE usuarios SET ativo = %s WHERE id = %s", (dados.ativo, usuario_id))
        if not dados.ativo:
            conn.execute("DELETE FROM equipe_membros WHERE usuario_id = %s", (usuario_id,))
        auditar(conn, g["id"], "CONTA_SUSPENSA" if not dados.ativo else "CONTA_REATIVADA",
                usuario_alvo_id=usuario_id, motivo=dados.motivo)
    return {"id": alvo["id"], "nome": alvo["nome"], "perfil": alvo["perfil"], "ativo": dados.ativo}


# ============================== Antifraude ==============================
_GRAVIDADE = {"ALTA": 0, "MEDIA": 1, "BAIXA": 2}


@router.get("/fraude", summary="Alertas de padrões suspeitos, do mais grave para o menos grave")
def fraude(conn: Connection = Depends(conexao)):
    par = {r["chave"]: float(r["valor"]) for r in conn.execute("SELECT chave, valor FROM parametros")}
    alertas: list[dict] = []

    # 1) Manipulação do ranking: rajada de apoios e apoios de contas recém-criadas.
    #    A janela deslizante (RANGE) conta, para cada apoio, quantos vieram nos minutos anteriores.
    suspeitas: dict[int, dict] = {}
    for r in conn.execute(
            f"""SELECT t.ocorrencia_id, o.titulo, o.apoios_total, o.apoios_validos, max(t.n) AS pico
                  FROM (SELECT a.ocorrencia_id,
                               count(*) OVER (PARTITION BY a.ocorrencia_id ORDER BY a.criado_em
                                              RANGE BETWEEN make_interval(mins => %(janela)s) PRECEDING
                                                        AND CURRENT ROW) AS n
                          FROM apoios a
                         WHERE a.criado_em > now() - interval '7 days'      -- índice apoios_criado_ix
                           AND (a.valido OR a.motivo_invalidez = 'CONTA_NOVA')) t
                  JOIN ocorrencias o ON o.id = t.ocorrencia_id AND o.status IN {ATIVOS}
                 GROUP BY t.ocorrencia_id, o.titulo, o.apoios_total, o.apoios_validos
                HAVING max(t.n) >= %(qtd)s""",
            {"janela": int(par["rajada_janela_min"]), "qtd": int(par["rajada_apoios_qtd"])}):
        suspeitas[r["ocorrencia_id"]] = {**r, "novas": 0}
    for r in conn.execute(
            f"""SELECT a.ocorrencia_id, o.titulo, o.apoios_total, o.apoios_validos, count(*) AS novas
                  FROM apoios a
                  JOIN usuarios u ON u.id = a.usuario_id
                  JOIN ocorrencias o ON o.id = a.ocorrencia_id AND o.status IN {ATIVOS}
                 WHERE (a.valido OR a.motivo_invalidez = 'CONTA_NOVA')
                   AND a.criado_em > now() - interval '30 days'
                   AND a.criado_em - u.criado_em < make_interval(hours => %(car)s)
                 GROUP BY a.ocorrencia_id, o.titulo, o.apoios_total, o.apoios_validos
                HAVING count(*) >= 3""", {"car": int(par["apoio_carencia_conta_h"])}):
        suspeitas.setdefault(r["ocorrencia_id"], {**r, "pico": 0})["novas"] = r["novas"]
    for s in suspeitas.values():
        partes = []
        if s["pico"]:
            partes.append(f"{s['pico']} apoios em menos de {int(par['rajada_janela_min'])} minutos")
        if s["novas"]:
            partes.append(f"{s['novas']} vindos de contas com menos de {int(par['apoio_carencia_conta_h'])} h de vida")
        alertas.append({
            "tipo": "APOIOS_SUSPEITOS", "gravidade": "ALTA" if s["pico"] and s["novas"] else "MEDIA",
            "titulo": f"Apoios suspeitos em “{s['titulo']}”",
            "detalhe": "; ".join(partes) + f". No ranking contam {s['apoios_validos']} de {s['apoios_total']}.",
            "ocorrencia_id": s["ocorrencia_id"], "pode_invalidar": s["novas"] > 0})

    # 2) Denúncias aguardando parecer
    for r in conn.execute(
            f"""SELECT o.id, o.titulo, o.denuncias_pendentes,
                       string_agg(DISTINCT CASE d.motivo WHEN 'FALSA' THEN 'informação falsa'
                                                WHEN 'DUPLICADA' THEN 'duplicada' WHEN 'OFENSIVA' THEN 'conteúdo ofensivo'
                                                WHEN 'LOCAL_ERRADO' THEN 'local errado' ELSE 'outro' END, ', ') AS motivos
                  FROM ocorrencias o JOIN denuncias d ON d.ocorrencia_id = o.id AND d.situacao = 'PENDENTE'
                 WHERE o.denuncias_pendentes > 0 AND o.status IN {ATIVOS}
                 GROUP BY o.id ORDER BY o.denuncias_pendentes DESC LIMIT 50"""):
        n = r["denuncias_pendentes"]
        alertas.append({
            "tipo": "DENUNCIAS", "gravidade": "ALTA" if n >= 3 else "MEDIA" if n == 2 else "BAIXA",
            "titulo": f"{n} denúncia(s) em “{r['titulo']}”",
            "detalhe": f"Motivos informados: {r['motivos']}.", "ocorrencia_id": r["id"]})

    # 3) Pedidos repetidos: mesma categoria, a poucos metros, ambos em aberto (usa o índice espacial).
    #    Só olha as registradas nos últimos 30 dias contra as demais: duplicata nova é a que interessa.
    for r in conn.execute(
            f"""SELECT a.id AS a_id, a.titulo AS a_titulo, b.id AS b_id, b.titulo AS b_titulo,
                       (a.usuario_id = b.usuario_id) AS mesmo_autor,
                       round(ST_Distance(a.localizacao::geography, b.localizacao::geography)::numeric) AS dist
                  FROM ocorrencias a
                  JOIN ocorrencias b ON b.id > a.id AND b.categoria_id = a.categoria_id AND b.status IN {ATIVOS}
                                    AND b.criado_em > now() - interval '30 days'
                                    AND ST_DWithin(a.localizacao::geography, b.localizacao::geography, %(raio)s)
                 WHERE a.status IN {ATIVOS} ORDER BY dist LIMIT 30""", {"raio": par["duplicata_raio_m"]}):
        alertas.append({
            "tipo": "DUPLICATA", "gravidade": "MEDIA" if r["mesmo_autor"] else "BAIXA",
            "titulo": f"Possível duplicata: nº {r['a_id']} e nº {r['b_id']}",
            "detalhe": f"“{r['a_titulo']}” e “{r['b_titulo']}” estão a {r['dist']} m, na mesma categoria"
                       + (", registradas pela mesma pessoa." if r["mesmo_autor"] else "."),
            "ocorrencia_id": r["b_id"], "principal_id": r["a_id"]})

    # 4) Apoio trocado: duas contas que apoiam repetidamente uma à outra
    for r in conn.execute(
            """WITH pares AS (
                   SELECT a.usuario_id AS apoiador, o.usuario_id AS autor, count(*) AS n
                     FROM apoios a JOIN ocorrencias o ON o.id = a.ocorrencia_id
                    WHERE a.valido AND a.criado_em > now() - interval '30 days'
                    GROUP BY 1, 2)
               SELECT ua.id AS a_id, ua.nome AS a_nome, ub.id AS b_id, ub.nome AS b_nome, p1.n AS ab, p2.n AS ba
                 FROM pares p1 JOIN pares p2 ON p2.apoiador = p1.autor AND p2.autor = p1.apoiador
                 JOIN usuarios ua ON ua.id = p1.apoiador JOIN usuarios ub ON ub.id = p1.autor
                WHERE p1.apoiador < p1.autor AND p1.n >= 4 AND p2.n >= 4
                ORDER BY p1.n + p2.n DESC LIMIT 20"""):
        alertas.append({
            "tipo": "APOIO_TROCADO", "gravidade": "MEDIA",
            "titulo": f"Apoio recíproco entre {r['a_nome']} e {r['b_nome']}",
            "detalhe": f"{r['a_nome']} apoiou {r['ab']} ocorrências de {r['b_nome']}, que apoiou {r['ba']} de volta "
                       "nos últimos 30 dias.",
            "usuario_id": r["a_id"], "usuario_nome": r["a_nome"]})

    # 5) Autor com muitas ocorrências rejeitadas
    for r in conn.execute(
            """SELECT u.id, u.nome, count(*) AS decididas, count(*) FILTER (WHERE o.status = 'REJEITADA') AS rejeitadas
                 FROM ocorrencias o JOIN usuarios u ON u.id = o.usuario_id AND u.ativo
                WHERE o.status IN ('RESOLVIDA', 'REJEITADA') AND o.encerrado_em > now() - interval '90 days'
                  AND o.duplicada_de IS NULL
                GROUP BY u.id
               HAVING count(*) >= 3 AND count(*) FILTER (WHERE o.status = 'REJEITADA') * 2 >= count(*)
                ORDER BY rejeitadas DESC LIMIT 20"""):
        alertas.append({
            "tipo": "AUTOR_REINCIDENTE", "gravidade": "MEDIA",
            "titulo": f"{r['nome']} tem {r['rejeitadas']} de {r['decididas']} ocorrências rejeitadas",
            "detalhe": "Metade ou mais das ocorrências decididas nos últimos 90 dias foi rejeitada.",
            "usuario_id": r["id"], "usuario_nome": r["nome"]})

    # 6) Serviço dado como concluído longe do local (ou sem GPS)
    for r in conn.execute(
            """SELECT os.id, os.ocorrencia_id, o.titulo, os.distancia_conclusao_m, os.fora_do_local,
                      e.nome AS equipe_nome, r.nome AS responsavel_nome
                 FROM ordens_servico os
                 JOIN ocorrencias o ON o.id = os.ocorrencia_id
                 JOIN equipes e ON e.id = os.equipe_id
                 LEFT JOIN usuarios r ON r.id = os.responsavel_id
                WHERE os.status = 'CONCLUIDA' AND os.encerrada_em > now() - interval '30 days'
                  AND (os.fora_do_local OR os.local_conclusao IS NULL)
                ORDER BY os.encerrada_em DESC LIMIT 30"""):
        onde = (f"a {round(r['distancia_conclusao_m'])} m do local" if r["fora_do_local"]
                else "sem localização do aparelho")
        alertas.append({
            "tipo": "CONCLUSAO_FORA_DO_LOCAL", "gravidade": "ALTA" if r["fora_do_local"] else "BAIXA",
            "titulo": f"OS nº {r['id']} concluída {onde}",
            "detalhe": f"“{r['titulo']}” · equipe {r['equipe_nome']}"
                       + (f" · {r['responsavel_nome']}" if r["responsavel_nome"] else "") + ".",
            "ocorrencia_id": r["ocorrencia_id"], "os_id": r["id"]})

    alertas.sort(key=lambda a: _GRAVIDADE[a["gravidade"]])
    return {"total": len(alertas), "alertas": alertas}
