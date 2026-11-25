"""Gestor: fila de prioridade, blindagem do ranking, despacho, duplicatas, denúncias, painel e antifraude."""
import psycopg
import pytest
from psycopg.errors import CheckViolation

from conftest import (ADMIN, CARLOS, FERNANDA, MARIANA, URL_TESTE, dados_cadastro, entrar, envelhecer_conta,
                      nova_equipe, nova_ocorrencia, novo_cidadao)

PESO = {"ALTA": 3, "MEDIA": 2, "BAIXA": 1}
ATIVOS = ("ABERTA", "EM_ANALISE", "EM_ANDAMENTO")


def _ficha(cliente, g, oid):
    r = cliente.get(f"/api/gestao/ocorrencias/{oid}", headers=g)
    assert r.status_code == 200, r.text
    return r.json()


# ------------------------------ Permissões ------------------------------
@pytest.mark.parametrize("rota", ["fila", "painel", "mapa", "equipes", "usuarios", "fraude"])
def test_so_gestao_acessa(cliente, rota):
    assert cliente.get(f"/api/gestao/{rota}").status_code == 401
    assert cliente.get(f"/api/gestao/{rota}", headers=entrar(cliente, MARIANA)).status_code == 403
    _, [colab] = nova_equipe(cliente, entrar(cliente, FERNANDA))
    assert cliente.get(f"/api/gestao/{rota}", headers=colab).status_code == 403
    assert cliente.get(f"/api/gestao/{rota}", headers=entrar(cliente, FERNANDA)).status_code == 200


def test_so_admin_cria_gestor(cliente):
    d = dados_cadastro(perfil="GESTOR")
    assert cliente.post("/api/gestao/usuarios", json=d, headers=entrar(cliente, FERNANDA)).status_code == 403
    r = cliente.post("/api/gestao/usuarios", json=d, headers=entrar(cliente, ADMIN))
    assert r.status_code == 201 and r.json()["perfil"] == "GESTOR"
    # A conta nova entra direto no painel do gestor
    assert cliente.get("/api/gestao/fila", headers=entrar(cliente, d["email"], d["senha"])).status_code == 200


# ------------------------------ Fila de prioridade ------------------------------
def test_fila_so_ativas_na_ordem_urgencia_apoios_validos_espera(cliente):
    r = cliente.get("/api/gestao/fila?limite=200", headers=entrar(cliente, FERNANDA)).json()
    itens = r["itens"]
    assert r["total"] >= len(itens) > 5 and all(o["status"] in ATIVOS for o in itens)
    chaves = [(-PESO[o["urgencia"]], -o["apoios_validos"], o["criado_em"]) for o in itens]
    assert chaves == sorted(chaves)
    assert [o["posicao"] for o in itens] == list(range(1, len(itens) + 1))
    assert all(o["sla"] in ("NO_PRAZO", "VENCENDO", "SEM_RESPOSTA", "ATRASADA") for o in itens)


def test_fila_filtros(cliente):
    g = entrar(cliente, FERNANDA)
    altas = cliente.get("/api/gestao/fila?urgencia=ALTA&sem_os=true", headers=g).json()["itens"]
    assert altas and all(o["urgencia"] == "ALTA" and o["os_id"] is None for o in altas)
    atrasadas = cliente.get("/api/gestao/fila?atrasadas=true", headers=g).json()["itens"]
    assert atrasadas and all(o["sla"] == "ATRASADA" for o in atrasadas)      # a nº 1 da demo é de 02/10
    todas = cliente.get("/api/gestao/fila?situacao=todas&limite=200", headers=g).json()["itens"]
    encerradas = [o["status"] not in ATIVOS for o in todas]
    assert any(encerradas) and encerradas == sorted(encerradas)              # encerradas no fim


# ------------------------------ Blindagem do ranking ------------------------------
def test_apoio_de_conta_nova_nao_conta_ate_cumprir_carencia(cliente, sql):
    oid, _ = nova_ocorrencia(cliente)
    apoiador = novo_cidadao(cliente)
    r = cliente.post(f"/api/ocorrencias/{oid}/apoios", headers=apoiador)
    assert r.status_code == 201 and r.json()["apoios_total"] == 1          # o cidadão vê o apoio registrado
    o = cliente.get(f"/api/ocorrencias/{oid}", headers=apoiador).json()
    assert (o["apoios_total"], o["apoios_validos"]) == (1, 0)              # mas ainda não pesa no ranking
    envelhecer_conta(sql, apoiador, cliente)
    cliente.get("/api/gestao/fila", headers=entrar(cliente, FERNANDA))     # a fila revalida os apoios
    assert cliente.get(f"/api/ocorrencias/{oid}", headers=apoiador).json()["apoios_validos"] == 1


def test_contas_recem_criadas_nao_furam_a_fila(cliente, sql):
    """Três contas criadas agora apoiam A; uma conta antiga apoia B. B fica na frente."""
    a, _ = nova_ocorrencia(cliente)
    b, _ = nova_ocorrencia(cliente)
    for _ in range(3):
        assert cliente.post(f"/api/ocorrencias/{a}/apoios", headers=novo_cidadao(cliente)).status_code == 201
    assert cliente.post(f"/api/ocorrencias/{b}/apoios", headers=entrar(cliente, CARLOS)).status_code == 201
    ordem = [o["id"] for o in cliente.get("/api/gestao/fila?limite=200&urgencia=MEDIA",
                                          headers=entrar(cliente, FERNANDA)).json()["itens"]]
    assert ordem.index(b) < ordem.index(a)
    # A lista "prioridade" do cidadão segue a mesma regra
    cid = [o["id"] for o in cliente.get("/api/ocorrencias?ordem=prioridade&limite=200",
                                        headers=entrar(cliente, MARIANA)).json()["itens"]]
    assert cid.index(b) < cid.index(a)


def test_limite_de_apoios_por_hora(cliente, sql):
    ids = [nova_ocorrencia(cliente)[0] for _ in range(3)]
    robo = novo_cidadao(cliente)
    sql.execute("UPDATE parametros SET valor = 2 WHERE chave = 'apoio_limite_por_hora'")
    try:
        respostas = [cliente.post(f"/api/ocorrencias/{i}/apoios", headers=robo) for i in ids]
    finally:
        sql.execute("UPDATE parametros SET valor = 20 WHERE chave = 'apoio_limite_por_hora'")
    assert [r.status_code for r in respostas] == [201, 201, 422]
    assert respostas[2].json()["detail"] == "Muitos apoios em pouco tempo. Tente novamente mais tarde."


def test_suspender_conta_tira_os_apoios_do_ranking_e_corta_o_acesso(cliente, sql):
    g = entrar(cliente, FERNANDA)
    oid, _ = nova_ocorrencia(cliente)
    d = dados_cadastro()
    cliente.post("/api/cadastro", json=d)
    h = entrar(cliente, d["email"], d["senha"])
    envelhecer_conta(sql, h, cliente)
    uid = cliente.get("/api/usuarios/me", headers=h).json()["id"]
    cliente.post(f"/api/ocorrencias/{oid}/apoios", headers=h)
    assert _ficha(cliente, g, oid)["apoios_validos"] == 1
    assert cliente.patch(f"/api/gestao/usuarios/{uid}", json={"ativo": False, "motivo": "x"}, headers=g).status_code == 422
    r = cliente.patch(f"/api/gestao/usuarios/{uid}", json={"ativo": False, "motivo": "Rede de contas falsas"}, headers=g)
    assert r.status_code == 200 and r.json()["ativo"] is False
    f = _ficha(cliente, g, oid)
    assert (f["apoios_total"], f["apoios_validos"], f["apoios"]["de_contas_suspensas"]) == (1, 0, 1)
    assert cliente.get("/api/usuarios/me", headers=h).status_code == 401
    assert sql.execute("SELECT acao, motivo FROM auditoria WHERE usuario_alvo_id = %s", (uid,)).fetchone() == \
        ("CONTA_SUSPENSA", "Rede de contas falsas")
    cliente.patch(f"/api/gestao/usuarios/{uid}", json={"ativo": True, "motivo": "Recurso aceito"}, headers=g)
    assert _ficha(cliente, g, oid)["apoios_validos"] == 1


def test_gestor_nao_suspende_a_si_nem_a_outro_gestor(cliente):
    g = entrar(cliente, FERNANDA)
    corpo = {"ativo": False, "motivo": "teste de permissão"}
    assert cliente.patch("/api/gestao/usuarios/3", json=corpo, headers=g).status_code == 409    # ela mesma
    assert cliente.patch("/api/gestao/usuarios/4", json=corpo, headers=g).status_code == 403    # o admin


def test_reclassificar_urgencia_exige_motivo_e_fica_auditado(cliente):
    g = entrar(cliente, FERNANDA)
    oid, autor = nova_ocorrencia(cliente, urgencia="ALTA")
    r = cliente.patch(f"/api/gestao/ocorrencias/{oid}/urgencia", json={"urgencia": "BAIXA", "motivo": " "}, headers=g)
    assert r.status_code == 422
    r = cliente.patch(f"/api/gestao/ocorrencias/{oid}/urgencia",
                      json={"urgencia": "BAIXA", "motivo": "Vistoria: sem risco imediato"}, headers=g)
    assert r.status_code == 200
    f = r.json()
    assert f["urgencia"] == "BAIXA" and f["urgencia_revisada"] is True
    assert [(a["acao"], a["valor_anterior"], a["valor_novo"]) for a in f["auditoria"]] == [("URGENCIA", "ALTA", "BAIXA")]
    assert cliente.get(f"/api/ocorrencias/{oid}", headers=autor).json()["urgencia"] == "BAIXA"
    # Cidadão não reclassifica
    r = cliente.patch(f"/api/gestao/ocorrencias/{oid}/urgencia",
                      json={"urgencia": "ALTA", "motivo": "quero prioridade"}, headers=autor)
    assert r.status_code == 403


# ------------------------------ Ordens de serviço ------------------------------
def test_despacho_cria_os_muda_status_e_avisa_o_cidadao(cliente):
    g = entrar(cliente, FERNANDA)
    equipe, _ = nova_equipe(cliente, g)
    oid, autor = nova_ocorrencia(cliente, urgencia="ALTA")
    r = cliente.post(f"/api/gestao/ocorrencias/{oid}/ordens", json={"equipe_id": equipe, "instrucoes": "Levar cones"}, headers=g)
    assert r.status_code == 201, r.text
    f = r.json()
    assert f["status"] == "EM_ANALISE" and f["os_status"] == "ATRIBUIDA" and f["primeira_resposta_em"]
    assert f["os_prazo_em"] == f["prazo_solucao_em"]                # prazo padrão = SLA da urgência
    hist = cliente.get(f"/api/ocorrencias/{oid}/historico", headers=autor).json()
    assert hist[-1]["status_novo"] == "EM_ANALISE" and f"nº {f['os_id']}" in hist[-1]["observacao"]
    # Uma OS ativa por ocorrência
    r = cliente.post(f"/api/gestao/ocorrencias/{oid}/ordens", json={"equipe_id": equipe}, headers=g)
    assert r.status_code == 409 and "já tem uma ordem de serviço ativa" in r.json()["detail"]


def test_despacho_valida_equipe_responsavel_e_prazo(cliente):
    g = entrar(cliente, FERNANDA)
    equipe, _ = nova_equipe(cliente, g)
    oid, _ = nova_ocorrencia(cliente)
    url = f"/api/gestao/ocorrencias/{oid}/ordens"
    assert cliente.post(url, json={"equipe_id": 999999}, headers=g).json()["detail"] == "Equipe inválida ou inativa."
    r = cliente.post(url, json={"equipe_id": equipe, "responsavel_id": 1}, headers=g)       # Mariana não é da equipe
    assert r.status_code == 422 and r.json()["detail"] == "O responsável precisa ser membro da equipe."
    r = cliente.post(url, json={"equipe_id": equipe, "prazo_em": "2020-01-01T10:00:00-03:00"}, headers=g)
    assert r.status_code == 422
    assert cliente.post("/api/gestao/ocorrencias/4/ordens", json={"equipe_id": equipe}, headers=g).status_code == 409  # resolvida


def test_cancelar_os_libera_novo_despacho(cliente):
    g = entrar(cliente, FERNANDA)
    equipe, _ = nova_equipe(cliente, g)
    oid, _ = nova_ocorrencia(cliente)
    os_id = cliente.post(f"/api/gestao/ocorrencias/{oid}/ordens", json={"equipe_id": equipe}, headers=g).json()["os_id"]
    r = cliente.post(f"/api/gestao/ordens/{os_id}/cancelar", json={"motivo": "Equipe realocada"}, headers=g)
    assert r.status_code == 200 and r.json()["os_id"] is None and r.json()["ordens"][0]["status"] == "CANCELADA"
    assert cliente.post(f"/api/gestao/ordens/{os_id}/cancelar", json={"motivo": "de novo"}, headers=g).status_code == 409
    assert cliente.post(f"/api/gestao/ocorrencias/{oid}/ordens", json={"equipe_id": equipe}, headers=g).status_code == 201


def test_encerrar_ocorrencia_cancela_a_os_ativa(cliente):
    g = entrar(cliente, FERNANDA)
    equipe, _ = nova_equipe(cliente, g)
    oid, _ = nova_ocorrencia(cliente)
    cliente.post(f"/api/gestao/ocorrencias/{oid}/ordens", json={"equipe_id": equipe}, headers=g)
    assert cliente.patch(f"/api/ocorrencias/{oid}", json={"status": "REJEITADA", "observacao": "Fora do município"},
                         headers=g).status_code == 200
    f = _ficha(cliente, g, oid)
    assert f["os_id"] is None and f["ordens"][0]["status"] == "CANCELADA" and f["encerrado_em"]


def test_regras_da_os_valem_direto_no_banco(cliente):
    g = entrar(cliente, FERNANDA)
    equipe, _ = nova_equipe(cliente, g)
    oid, _ = nova_ocorrencia(cliente)
    os_id = cliente.post(f"/api/gestao/ocorrencias/{oid}/ordens", json={"equipe_id": equipe}, headers=g).json()["os_id"]
    with psycopg.connect(URL_TESTE, autocommit=True) as c:
        with pytest.raises(CheckViolation):                   # ATRIBUIDA não pula direto para CONCLUIDA
            c.execute("UPDATE ordens_servico SET status = 'CONCLUIDA' WHERE id = %s", (os_id,))
        with pytest.raises(psycopg.errors.UniqueViolation):   # segunda OS ativa para a mesma ocorrência
            c.execute("INSERT INTO ordens_servico (ocorrencia_id, equipe_id, prazo_em, criado_por) "
                      "VALUES (%s, %s, now() + interval '1 day', 3)", (oid, equipe))
        with pytest.raises(CheckViolation):                   # cidadão não entra em equipe
            c.execute("INSERT INTO equipe_membros (usuario_id, equipe_id) VALUES (1, %s)", (equipe,))
        with pytest.raises(CheckViolation):                   # auditoria é somente inserção
            c.execute("DELETE FROM auditoria")


# ------------------------------ Duplicatas e denúncias ------------------------------
def test_unificar_duplicata_transfere_apoios_e_autor(cliente, sql):
    g = entrar(cliente, FERNANDA)
    principal, _ = nova_ocorrencia(cliente)
    dup, autor_dup = nova_ocorrencia(cliente)
    envelhecer_conta(sql, autor_dup, cliente)
    apoiador = novo_cidadao(cliente)
    envelhecer_conta(sql, apoiador, cliente)
    cliente.post(f"/api/ocorrencias/{dup}/apoios", headers=apoiador)
    r = cliente.post(f"/api/gestao/ocorrencias/{dup}/duplicata", json={"principal_id": principal}, headers=g)
    assert r.status_code == 200, r.text
    assert r.json()["id"] == principal and r.json()["apoios_validos"] == 2      # o apoiador + o autor da duplicata
    f = _ficha(cliente, g, dup)
    assert f["status"] == "REJEITADA" and f["duplicada_de"] == principal
    assert f"nº {principal}" in cliente.get(f"/api/ocorrencias/{dup}/historico", headers=autor_dup).json()[-1]["observacao"]
    # Não unifica consigo mesma nem com ocorrência encerrada
    assert cliente.post(f"/api/gestao/ocorrencias/{principal}/duplicata", json={"principal_id": principal}, headers=g).status_code == 422
    assert cliente.post(f"/api/gestao/ocorrencias/{principal}/duplicata", json={"principal_id": dup}, headers=g).status_code == 409


def test_ficha_aponta_possivel_duplicata_por_proximidade(cliente):
    g = entrar(cliente, FERNANDA)
    a = cliente.post("/api/ocorrencias", json={"categoria_id": 2, "titulo": "Poste A", "descricao": "d", "urgencia": "MEDIA",
                                               "endereco_referencia": "Rua X", "latitude": -21.5, "longitude": -44.5},
                     headers=novo_cidadao(cliente)).json()["id"]
    b = cliente.post("/api/ocorrencias", json={"categoria_id": 2, "titulo": "Poste B", "descricao": "d", "urgencia": "MEDIA",
                                               "endereco_referencia": "Rua X", "latitude": -21.5002, "longitude": -44.5},
                     headers=novo_cidadao(cliente)).json()["id"]      # ~22 m, outra pessoa: o cadastro deixa passar
    dups = _ficha(cliente, g, b)["possiveis_duplicatas"]
    assert [d["id"] for d in dups] == [a] and 15 < dups[0]["distancia_m"] < 30
    alertas = cliente.get("/api/gestao/fraude", headers=g).json()["alertas"]
    assert any(x["tipo"] == "DUPLICATA" and {x["ocorrencia_id"], x["principal_id"]} == {a, b} for x in alertas)


def test_denuncia_unica_por_conta_e_parecer_do_gestor(cliente):
    g = entrar(cliente, FERNANDA)
    oid, autor = nova_ocorrencia(cliente)
    h = novo_cidadao(cliente)
    url = f"/api/ocorrencias/{oid}/denuncias"
    assert cliente.post(url, json={"motivo": "FALSA", "detalhe": "Não existe"}, headers=h).status_code == 201
    assert cliente.post(url, json={"motivo": "FALSA"}, headers=h).json()["detail"] == "Você já denunciou esta ocorrência."
    r = cliente.post(url, json={"motivo": "OUTRO"}, headers=autor)
    assert r.status_code == 422 and r.json()["detail"] == "Não é possível denunciar a própria ocorrência."
    assert cliente.post(url, json={"motivo": "INVENTADO"}, headers=novo_cidadao(cliente)).status_code == 422
    f = _ficha(cliente, g, oid)
    assert f["denuncias_pendentes"] == 1 and f["denuncias"][0]["motivo"] == "FALSA"
    assert any(a["tipo"] == "DENUNCIAS" and a["ocorrencia_id"] == oid
               for a in cliente.get("/api/gestao/fraude", headers=g).json()["alertas"])
    r = cliente.post(f"/api/gestao/ocorrencias/{oid}/denuncias/analisar", json={"procedente": False}, headers=g)
    assert r.json()["analisadas"] == 1 and r.json()["ocorrencia"]["denuncias_pendentes"] == 0
    assert r.json()["ocorrencia"]["denuncias"][0]["situacao"] == "IMPROCEDENTE"


# ------------------------------ Antifraude, painel, mapa, pulso ------------------------------
def test_rajada_de_contas_novas_vira_alerta_e_gestor_invalida(cliente):
    g = entrar(cliente, FERNANDA)
    oid, _ = nova_ocorrencia(cliente, urgencia="BAIXA")
    for _ in range(5):
        cliente.post(f"/api/ocorrencias/{oid}/apoios", headers=novo_cidadao(cliente))
    alerta = next(a for a in cliente.get("/api/gestao/fraude", headers=g).json()["alertas"]
                  if a["tipo"] == "APOIOS_SUSPEITOS" and a["ocorrencia_id"] == oid)
    assert alerta["gravidade"] == "ALTA" and alerta["pode_invalidar"] and "contam 0 de 5" in alerta["detalhe"]
    r = cliente.post(f"/api/gestao/ocorrencias/{oid}/apoios/invalidar-suspeitos", json={"motivo": "Rajada combinada"}, headers=g)
    assert r.status_code == 200 and r.json()["invalidados"] == 5
    assert r.json()["ocorrencia"]["apoios"]["invalidados"] == 5
    # Invalidado pelo gestor não volta com a carência e o alerta some
    assert not any(a["tipo"] == "APOIOS_SUSPEITOS" and a["ocorrencia_id"] == oid
                   for a in cliente.get("/api/gestao/fraude", headers=g).json()["alertas"])


def test_cenario_de_fraude_da_demonstracao(cliente, sql):
    oid = sql.execute("SELECT id FROM ocorrencias WHERE titulo = 'Paralelepípedos soltos'").fetchone()[0]
    g = entrar(cliente, FERNANDA)
    f = _ficha(cliente, g, oid)
    assert f["apoios"]["suspeitos"] == 6 and f["apoios_total"] - f["apoios_validos"] == 6
    assert f["denuncias_pendentes"] == 2


def test_painel_traz_indicadores_coerentes(cliente):
    g = entrar(cliente, FERNANDA)
    equipe, _ = nova_equipe(cliente, g)
    oid, _ = nova_ocorrencia(cliente)
    antes = cliente.get("/api/gestao/painel?dias=30", headers=g).json()
    cliente.post(f"/api/gestao/ocorrencias/{oid}/ordens", json={"equipe_id": equipe}, headers=g)
    p = cliente.get("/api/gestao/painel?dias=30", headers=g).json()
    r = p["resumo"]
    assert r["em_analise"] == antes["resumo"]["em_analise"] + 1 and r["abertas"] == antes["resumo"]["abertas"] - 1
    assert r["resolvidas"] >= 10 and r["resposta_media_h"] > 0 and r["solucao_media_h"] > r["resposta_media_h"]
    assert 0 <= r["sla_pct"] <= 100 and 0 <= r["validacao_pct"] <= 100
    assert len(p["serie"]) in (31, 32) and sum(d["novas"] for d in p["serie"]) >= 20
    assert {c["nome"] for c in p["categorias"]} == {"Buraco na via", "Iluminação pública", "Poda de árvore"}
    assert next(e for e in p["equipes"] if e["id"] == equipe)["ativas"] == 1
    assert p["regioes"] and p["regioes"][0]["ativas"] >= p["regioes"][-1]["ativas"]
    assert all(u["validacao_pct"] is None or 0 <= u["validacao_pct"] <= 100 for u in p["usuarios"])
    assert cliente.get("/api/gestao/painel?dias=0", headers=g).status_code == 422


def test_mapa_e_pulso(cliente):
    g = entrar(cliente, FERNANDA)
    m = cliente.get("/api/gestao/mapa", headers=g).json()
    assert len(m["pontos"]) > 10 and m["celulas"] and all(-90 <= p["latitude"] <= 90 for p in m["pontos"])
    v1 = cliente.get("/api/pulso", headers=g).json()["versao"]
    assert cliente.get("/api/pulso", headers=g).json()["versao"] == v1      # leitura não muda a versão
    nova_ocorrencia(cliente)
    assert cliente.get("/api/pulso", headers=g).json()["versao"] > v1
    assert cliente.get("/api/pulso").status_code == 401


def test_usuarios_nao_expoe_cpf_nem_email_de_cidadao(cliente):
    lista = cliente.get("/api/gestao/usuarios?limite=500", headers=entrar(cliente, FERNANDA)).json()
    assert all("cpf" not in u and "senha_hash" not in u for u in lista)
    assert all(u["email"] is None for u in lista if u["perfil"] == "CIDADAO")
    assert any(u["email"] and u["equipe_nome"] for u in lista if u["perfil"] == "COLABORADOR")
