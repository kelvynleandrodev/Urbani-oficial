"""Equipe de campo: ordens da equipe, execução, prova de presença, fotos e devolução."""
import base64

import pytest

from conftest import FERNANDA, MARIANA, entrar, nova_equipe, nova_ocorrencia

# Menor JPEG válido para os testes (cabeçalho + fim de imagem)
JPEG = "data:image/jpeg;base64," + base64.b64encode(b"\xff\xd8\xff\xe0" + b"\x00" * 64 + b"\xff\xd9").decode()


def _despachar(cliente, membros: int = 1, **extra):
    """Ocorrência nova já com OS atribuída. Devolve (ocorrência, os, gestor, autor, logins, posição)."""
    g = entrar(cliente, FERNANDA)
    equipe, logins = nova_equipe(cliente, g, membros)
    oid, autor = nova_ocorrencia(cliente, **extra)
    f = cliente.post(f"/api/gestao/ocorrencias/{oid}/ordens", json={"equipe_id": equipe}, headers=g).json()
    return oid, f["os_id"], g, autor, logins, {"latitude": f["latitude"], "longitude": f["longitude"]}


def test_so_colaborador_acessa_e_so_ve_a_propria_equipe(cliente):
    _, os_id, g, autor, [c], _ = _despachar(cliente)
    assert cliente.get("/api/campo/ordens").status_code == 401
    assert cliente.get("/api/campo/ordens", headers=autor).status_code == 403
    assert cliente.get("/api/campo/ordens", headers=g).status_code == 403
    r = cliente.get("/api/campo/ordens", headers=c).json()
    assert r["equipe"]["nome"].startswith("Equipe Teste") and [o["id"] for o in r["itens"]] == [os_id]
    _, [outro] = nova_equipe(cliente, g)
    assert cliente.get("/api/campo/ordens", headers=outro).json()["itens"] == []
    assert cliente.get(f"/api/campo/ordens/{os_id}", headers=outro).status_code == 404
    assert cliente.post(f"/api/campo/ordens/{os_id}/iniciar", headers=outro).status_code == 404


def test_fluxo_completo_do_despacho_ate_o_cidadao(cliente):
    oid, os_id, g, autor, [c], pos = _despachar(cliente, urgencia="ALTA")
    # Distância até o serviço a partir da posição do aparelho (~111 m ao norte)
    perto = cliente.get(f"/api/campo/ordens?latitude={pos['latitude'] + 0.001}&longitude={pos['longitude']}", headers=c).json()
    assert 100 < perto["itens"][0]["distancia_m"] < 120
    # Concluir sem iniciar não vale
    assert cliente.post(f"/api/campo/ordens/{os_id}/concluir", json={"relatorio": "Buraco tapado com asfalto"}, headers=c).status_code == 409
    r = cliente.post(f"/api/campo/ordens/{os_id}/iniciar", headers=c)
    assert r.status_code == 200 and r.json()["status"] == "EM_EXECUCAO" and r.json()["responsavel_nome"] == "Pessoa Teste"
    assert cliente.get(f"/api/ocorrencias/{oid}", headers=autor).json()["status"] == "EM_ANDAMENTO"
    assert cliente.post(f"/api/campo/ordens/{os_id}/iniciar", headers=c).status_code == 409
    foto = cliente.post(f"/api/campo/ordens/{os_id}/fotos", json={"tipo": "DEPOIS", "imagem": JPEG}, headers=c)
    assert foto.status_code == 201
    r = cliente.post(f"/api/campo/ordens/{os_id}/concluir", json={"relatorio": "curto", **pos}, headers=c)
    assert r.status_code == 422 and "mínimo de 10 caracteres" in r.json()["detail"]
    r = cliente.post(f"/api/campo/ordens/{os_id}/concluir", json={"relatorio": "Buraco tapado com asfalto quente.", **pos}, headers=c)
    assert r.status_code == 200 and r.json()["status"] == "CONCLUIDA" and r.json()["fotos"] == 1
    # O cidadão vê a ocorrência resolvida, o relato da equipe e a foto
    o = cliente.get(f"/api/ocorrencias/{oid}", headers=autor).json()
    hist = cliente.get(f"/api/ocorrencias/{oid}/historico", headers=autor).json()
    assert o["status"] == "RESOLVIDA"
    assert [h["status_novo"] for h in hist] == ["ABERTA", "EM_ANALISE", "EM_ANDAMENTO", "RESOLVIDA"]
    assert hist[-1]["observacao"] == "Serviço concluído: Buraco tapado com asfalto quente."
    fotos = cliente.get(f"/api/ocorrencias/{oid}/fotos", headers=autor).json()
    assert [f["tipo"] for f in fotos] == ["DEPOIS"]
    img = cliente.get(f"/api/fotos/{fotos[0]['id']}", headers=autor)
    assert img.status_code == 200 and img.headers["content-type"] == "image/jpeg" and img.content.startswith(b"\xff\xd8\xff")
    assert cliente.get(f"/api/fotos/{fotos[0]['id']}").status_code == 401
    # O gestor vê a prova de presença e a OS sai da lista de ativas do colaborador
    os_ = cliente.get(f"/api/gestao/ocorrencias/{oid}", headers=g).json()["ordens"][0]
    assert os_["status"] == "CONCLUIDA" and os_["fora_do_local"] is False and os_["distancia_conclusao_m"] < 1
    assert cliente.get("/api/campo/ordens", headers=c).json()["itens"] == []
    assert [x["id"] for x in cliente.get("/api/campo/ordens?situacao=encerradas", headers=c).json()["itens"]] == [os_id]
    assert cliente.post(f"/api/campo/ordens/{os_id}/fotos", json={"tipo": "DEPOIS", "imagem": JPEG}, headers=c).status_code == 409


@pytest.mark.parametrize("posicao, fora, sem_gps", [
    ({"latitude": -10.0, "longitude": -40.0}, True, False),      # a centenas de km
    ({}, False, True),                                           # GPS indisponível
])
def test_conclusao_longe_ou_sem_gps_vira_alerta(cliente, posicao, fora, sem_gps):
    oid, os_id, g, _, [c], _ = _despachar(cliente)
    cliente.post(f"/api/campo/ordens/{os_id}/iniciar", headers=c)
    r = cliente.post(f"/api/campo/ordens/{os_id}/concluir", json={"relatorio": "Serviço executado no local.", **posicao}, headers=c)
    assert r.status_code == 200                                  # não bloqueia o trabalho...
    os_ = cliente.get(f"/api/gestao/ocorrencias/{oid}", headers=g).json()["ordens"][0]
    assert (os_["fora_do_local"], os_["sem_gps"]) == (fora, sem_gps)
    alerta = next(a for a in cliente.get("/api/gestao/fraude", headers=g).json()["alertas"]     # ...mas o gestor fica sabendo
                  if a["tipo"] == "CONCLUSAO_FORA_DO_LOCAL" and a["os_id"] == os_id)
    assert alerta["gravidade"] == ("ALTA" if fora else "BAIXA")


def test_devolucao_volta_para_o_gestor_redespachar(cliente):
    oid, os_id, g, autor, [c], _ = _despachar(cliente)
    assert cliente.post(f"/api/campo/ordens/{os_id}/devolver", json={"motivo": "  "}, headers=c).status_code == 422
    r = cliente.post(f"/api/campo/ordens/{os_id}/devolver", json={"motivo": "Rua interditada pela CET"}, headers=c)
    assert r.status_code == 200 and r.json()["status"] == "DEVOLVIDA"
    o = cliente.get(f"/api/ocorrencias/{oid}", headers=autor).json()
    assert o["status"] == "EM_ANALISE"                           # a ocorrência continua viva
    assert "Rua interditada pela CET" in cliente.get(f"/api/ocorrencias/{oid}/historico", headers=autor).json()[-1]["observacao"]
    sem_os = [x["id"] for x in cliente.get("/api/gestao/fila?sem_os=true&limite=200", headers=g).json()["itens"]]
    assert oid in sem_os
    equipe2, _ = nova_equipe(cliente, g)
    assert cliente.post(f"/api/gestao/ocorrencias/{oid}/ordens", json={"equipe_id": equipe2}, headers=g).status_code == 201


def test_qualquer_membro_da_equipe_assume_a_os(cliente):
    _, os_id, _, _, [a, b], _ = _despachar(cliente, membros=2)
    assert cliente.post(f"/api/campo/ordens/{os_id}/iniciar", headers=b).status_code == 200
    assert cliente.get("/api/campo/ordens", headers=a).json()["itens"][0]["status"] == "EM_EXECUCAO"


@pytest.mark.parametrize("imagem", [
    "data:image/jpeg;base64,AAAA",                               # não é JPEG de verdade
    "data:text/html;base64,PGgxPm9pPC9oMT4=",                    # tipo não aceito
    "data:image/png;base64,###",                                 # base64 inválido
])
def test_foto_invalida_e_recusada(cliente, imagem):
    _, os_id, _, _, [c], _ = _despachar(cliente)
    r = cliente.post(f"/api/campo/ordens/{os_id}/fotos", json={"tipo": "ANTES", "imagem": imagem}, headers=c)
    assert r.status_code == 422 and r.json()["detail"] == "Envie uma imagem JPEG, PNG ou WebP."


def test_colaborador_removido_da_equipe_perde_as_ordens(cliente):
    _, os_id, g, _, [c], _ = _despachar(cliente)
    eu = cliente.get("/api/usuarios/me", headers=c).json()
    equipe = cliente.get("/api/campo/ordens", headers=c).json()["equipe"]["id"]
    assert cliente.delete(f"/api/gestao/equipes/{equipe}/membros/{eu['id']}", headers=g).status_code == 204
    assert cliente.get("/api/campo/ordens", headers=c).json() == {"equipe": None, "itens": []}
    assert cliente.post(f"/api/campo/ordens/{os_id}/iniciar", headers=c).status_code == 404
    assert cliente.get("/api/ocorrencias", headers=entrar(cliente, MARIANA)).status_code == 200
