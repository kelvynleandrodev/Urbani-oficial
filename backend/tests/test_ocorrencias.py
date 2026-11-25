"""Ocorrências: criação, validação, listagem, prioridade, proximidade, status e apoios."""
import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.errors import CheckViolation

from app.main import app
from conftest import CARLOS, FERNANDA, MARIANA, URL_TESTE, entrar, novo_cidadao, ocorrencia


# ------------------------------- Criação -------------------------------
def test_criar_ocorrencia_comeca_aberta_e_gera_historico(cliente, sql):
    h = novo_cidadao(cliente)
    r = cliente.post("/api/ocorrencias", json=ocorrencia(-23.50, -46.60, urgencia="ALTA"), headers=h)
    assert r.status_code == 201, r.text
    o = r.json()
    assert o["status"] == "ABERTA" and o["urgencia"] == "ALTA" and o["apoios_total"] == 0
    assert (o["latitude"], o["longitude"]) == (-23.50, -46.60)
    # No PostGIS o ponto fica como (longitude, latitude)
    assert sql.execute("SELECT ST_AsText(localizacao) FROM ocorrencias WHERE id = %s",
                       (o["id"],)).fetchone()[0] == "POINT(-46.6 -23.5)"
    hist = cliente.get(f"/api/ocorrencias/{o['id']}/historico", headers=h).json()
    assert [(x["status_anterior"], x["status_novo"]) for x in hist] == [(None, "ABERTA")]


def test_ocorrencia_persiste_e_aparece_para_outra_sessao(cliente):
    h = novo_cidadao(cliente)
    oid = cliente.post("/api/ocorrencias", json=ocorrencia(-23.40, -46.40), headers=h).json()["id"]
    # Conexão nova e independente: só enxerga o que foi confirmado (commit) no banco
    with psycopg.connect(URL_TESTE) as c:
        assert c.execute("SELECT status FROM ocorrencias WHERE id = %s", (oid,)).fetchone() == ("ABERTA",)
    outro = TestClient(app)            # outro "navegador", com outra pessoa logada
    lista = outro.get("/api/ocorrencias?limite=200", headers=entrar(outro, CARLOS)).json()["itens"]
    assert oid in [o["id"] for o in lista]


@pytest.mark.parametrize("mudanca, mensagem", [
    ({"titulo": "   "}, "Preencha título, descrição e endereço."),
    ({"latitude": 200}, "Valor inválido no campo latitude."),
    ({"longitude": -181}, "Valor inválido no campo longitude."),
    ({"urgencia": "URGENTISSIMA"}, "Valor inválido no campo urgencia."),
    ({"categoria_id": 999}, "Categoria inválida."),
])
def test_ocorrencia_com_dados_invalidos(cliente, mudanca, mensagem):
    r = cliente.post("/api/ocorrencias", json=ocorrencia(**mudanca), headers=novo_cidadao(cliente))
    assert r.status_code == 422 and r.json()["detail"] == mensagem


def test_ocorrencia_sem_campo_obrigatorio(cliente):
    dados = ocorrencia(); dados.pop("descricao")
    r = cliente.post("/api/ocorrencias", json=dados, headers=novo_cidadao(cliente))
    assert r.status_code == 422 and r.json()["detail"] == "Campo obrigatório: descricao."


def test_antifraude_bloqueia_ocorrencia_repetida_no_mesmo_local(cliente):
    h = novo_cidadao(cliente)
    assert cliente.post("/api/ocorrencias", json=ocorrencia(-23.30, -46.30), headers=h).status_code == 201
    # 20 m de distância, mesma categoria, mesma pessoa
    r = cliente.post("/api/ocorrencias", json=ocorrencia(-23.30018, -46.30), headers=h)
    assert r.status_code == 409 and "últimas 24 horas" in r.json()["detail"]
    # Outra categoria no mesmo lugar é permitida
    assert cliente.post("/api/ocorrencias", json=ocorrencia(-23.30, -46.30, categoria_id=2),
                        headers=h).status_code == 201


# ------------------------------- Consultas ------------------------------
def test_filtros_e_minhas(cliente):
    h = entrar(cliente, MARIANA)
    minhas = cliente.get("/api/ocorrencias?minhas=true", headers=h).json()["itens"]
    assert minhas and all(o["usuario_id"] == 1 for o in minhas)
    abertas = cliente.get("/api/ocorrencias?status=RESOLVIDA", headers=h).json()["itens"]
    assert {o["id"] for o in abertas} >= {4, 5} and all(o["status"] == "RESOLVIDA" for o in abertas)
    assert cliente.get("/api/ocorrencias?status=INEXISTENTE", headers=h).status_code == 422


def test_prioridade_urgencia_depois_apoios_e_encerradas_no_fim(cliente):
    itens = cliente.get("/api/ocorrencias?ordem=prioridade&limite=200",
                        headers=entrar(cliente, MARIANA)).json()["itens"]
    peso = {"ALTA": 3, "MEDIA": 2, "BAIXA": 1}
    # O ranking usa os apoios VÁLIDOS (apoios de contas recém-criadas não contam)
    chaves = [(o["status"] in ("RESOLVIDA", "REJEITADA"), -peso[o["urgencia"]], -o["apoios_validos"]) for o in itens]
    assert chaves == sorted(chaves)


def test_consulta_espacial_por_raio(cliente):
    h = entrar(cliente, MARIANA)
    # Ponto a ~100 m da ocorrência 1 (Av. Paulista)
    r = cliente.get("/api/ocorrencias/proximas?latitude=-23.5605&longitude=-46.6559&raio_m=300", headers=h)
    assert r.status_code == 200
    perto = r.json()
    assert [o["id"] for o in perto] == [1]
    assert 90 < perto[0]["distancia_m"] < 110
    # Raio maior inclui mais ocorrências, ordenadas da mais perto para a mais longe
    longe = cliente.get("/api/ocorrencias/proximas?latitude=-23.5605&longitude=-46.6559&raio_m=5000",
                        headers=h).json()
    distancias = [o["distancia_m"] for o in longe]
    assert len(longe) > 1 and distancias == sorted(distancias)


def test_detalhe_inexistente(cliente):
    assert cliente.get("/api/ocorrencias/999999", headers=entrar(cliente, MARIANA)).status_code == 404


# ------------------------------- Status --------------------------------
def test_cidadao_nao_altera_status(cliente):
    r = cliente.patch("/api/ocorrencias/1", json={"status": "EM_ANALISE"}, headers=entrar(cliente, MARIANA))
    assert r.status_code == 403


def test_gestor_altera_status_e_historico_cresce(cliente):
    oid = cliente.post("/api/ocorrencias", json=ocorrencia(-23.20, -46.20), headers=novo_cidadao(cliente)).json()["id"]
    g = entrar(cliente, FERNANDA)
    for novo in ("EM_ANALISE", "EM_ANDAMENTO", "RESOLVIDA"):
        r = cliente.patch(f"/api/ocorrencias/{oid}", json={"status": novo, "observacao": "ok"}, headers=g)
        assert r.status_code == 200 and r.json()["status"] == novo
    hist = cliente.get(f"/api/ocorrencias/{oid}/historico", headers=g).json()
    assert [x["status_novo"] for x in hist] == ["ABERTA", "EM_ANALISE", "EM_ANDAMENTO", "RESOLVIDA"]
    assert hist[-1]["autor_nome"] == "Fernanda Alves"


def test_transicao_de_status_invalida(cliente):
    r = cliente.patch("/api/ocorrencias/4", json={"status": "ABERTA"}, headers=entrar(cliente, FERNANDA))
    assert r.status_code == 409 and r.json()["detail"] == "Não é possível mudar de RESOLVIDA para ABERTA."


def test_historico_nao_pode_ser_apagado(sql):
    with pytest.raises(CheckViolation):
        sql.execute("DELETE FROM historico_status WHERE ocorrencia_id = 4")


# ------------------------------- Apoios --------------------------------
def test_apoio_valido_duplicado_e_retirada(cliente, sql):
    dono = novo_cidadao(cliente)
    oid = cliente.post("/api/ocorrencias", json=ocorrencia(-23.10, -46.10), headers=dono).json()["id"]
    h = novo_cidadao(cliente)
    r = cliente.post(f"/api/ocorrencias/{oid}/apoios", headers=h)
    assert r.status_code == 201 and r.json() == {"ocorrencia_id": oid, "apoios_total": 1, "apoiado_por_mim": True}
    r = cliente.post(f"/api/ocorrencias/{oid}/apoios", headers=h)
    assert r.status_code == 409 and r.json()["detail"] == "Você já apoiou esta ocorrência."
    assert sql.execute("SELECT count(*) FROM apoios WHERE ocorrencia_id = %s", (oid,)).fetchone()[0] == 1
    assert cliente.delete(f"/api/ocorrencias/{oid}/apoios", headers=h).status_code == 204
    assert cliente.get(f"/api/ocorrencias/{oid}/apoios", headers=h).json()["apoios_total"] == 0
    assert cliente.delete(f"/api/ocorrencias/{oid}/apoios", headers=h).status_code == 404


def test_nao_apoia_a_propria_ocorrencia(cliente):
    r = cliente.post("/api/ocorrencias/1/apoios", headers=entrar(cliente, MARIANA))   # a 1 é da Mariana
    assert r.status_code == 422 and r.json()["detail"] == "Não é possível apoiar a própria ocorrência."


def test_nao_apoia_ocorrencia_encerrada(cliente):
    r = cliente.post("/api/ocorrencias/5/apoios", headers=entrar(cliente, CARLOS))     # a 5 está RESOLVIDA
    assert r.status_code == 422 and r.json()["detail"] == "Ocorrência encerrada não recebe apoios."


def test_unicidade_do_apoio_vale_direto_no_banco():
    """Mesmo sem passar pela API, o banco recusa o segundo apoio da mesma conta."""
    with psycopg.connect(URL_TESTE, autocommit=True) as c:
        with pytest.raises(psycopg.errors.UniqueViolation):
            c.execute("INSERT INTO apoios (usuario_id, ocorrencia_id) VALUES (2, 1)")   # já existe na demo
