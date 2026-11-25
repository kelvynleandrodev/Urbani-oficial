"""Rotas usadas pelos três perfis: denúncias, fotos do serviço e pulso de atualização."""
from fastapi import APIRouter, Depends, HTTPException, Response, status
from psycopg import Connection
from psycopg.errors import CheckViolation, UniqueViolation

from ..db import conexao
from ..esquemas import DenunciaEntrada
from ..seguranca import usuario_atual

router = APIRouter(prefix="/api", tags=["Integração"])


@router.get("/pulso", summary="Versão dos dados (muda a cada escrita relevante)")
def pulso(_: dict = Depends(usuario_atual), conn: Connection = Depends(conexao)):
    """Leitura de um único número. As telas consultam esta rota a cada poucos
    segundos e só recarregam as listas e indicadores quando a versão muda."""
    return {"versao": conn.execute("SELECT last_value AS v FROM pulso_seq").fetchone()["v"]}


@router.post("/ocorrencias/{ocorrencia_id}/denuncias", status_code=status.HTTP_201_CREATED,
             summary="Denunciar ocorrência (uma vez por conta)")
def denunciar(ocorrencia_id: int, dados: DenunciaEntrada,
              u: dict = Depends(usuario_atual), conn: Connection = Depends(conexao)):
    if not conn.execute("SELECT 1 FROM ocorrencias WHERE id = %s", (ocorrencia_id,)).fetchone():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ocorrência não encontrada.")
    try:
        with conn.transaction():
            conn.execute("INSERT INTO denuncias (ocorrencia_id, usuario_id, motivo, detalhe) VALUES (%s, %s, %s, %s)",
                         (ocorrencia_id, u["id"], dados.motivo, (dados.detalhe or "").strip() or None))
    except UniqueViolation:
        raise HTTPException(status.HTTP_409_CONFLICT, "Você já denunciou esta ocorrência.")
    except CheckViolation as e:                    # trigger validar_denuncia()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, e.diag.message_primary + ".")
    return {"ocorrencia_id": ocorrencia_id, "denunciada": True}


@router.get("/ocorrencias/{ocorrencia_id}/fotos", summary="Fotos do serviço executado (antes/depois)")
def fotos_da_ocorrencia(ocorrencia_id: int, _: dict = Depends(usuario_atual), conn: Connection = Depends(conexao)):
    return conn.execute(
        """SELECT f.id, f.tipo, f.criado_em, f.os_id
             FROM os_fotos f JOIN ordens_servico os ON os.id = f.os_id
            WHERE os.ocorrencia_id = %s ORDER BY f.id""", (ocorrencia_id,)).fetchall()


@router.get("/fotos/{foto_id}", summary="Conteúdo de uma foto", response_class=Response)
def foto(foto_id: int, _: dict = Depends(usuario_atual), conn: Connection = Depends(conexao)):
    f = conn.execute("SELECT mime, conteudo FROM os_fotos WHERE id = %s", (foto_id,)).fetchone()
    if not f:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Foto não encontrada.")
    return Response(content=bytes(f["conteudo"]), media_type=f["mime"],
                    headers={"Cache-Control": "private, max-age=86400", "X-Content-Type-Options": "nosniff"})
