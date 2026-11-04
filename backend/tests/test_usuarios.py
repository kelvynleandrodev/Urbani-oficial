"""Cadastro, login, perfil e controle de acesso."""
from datetime import date

import pytest
from psycopg.errors import CheckViolation

from conftest import CARLOS, MARIANA, cpf_novo, dados_cadastro, entrar


def test_cadastro_valido_grava_no_postgres_com_senha_protegida(cliente, sql):
    d = dados_cadastro()
    r = cliente.post("/api/cadastro", json=d)
    assert r.status_code == 201
    corpo = r.json()
    assert corpo["perfil"] == "CIDADAO" and corpo["cpf"] == d["cpf"]
    assert "senha" not in corpo and "senha_hash" not in corpo
    linha = sql.execute("SELECT cpf, senha_hash FROM usuarios WHERE id = %s", (corpo["id"],)).fetchone()
    assert linha[0] == d["cpf"].replace(".", "").replace("-", "")   # guardado só com dígitos
    assert linha[1].startswith("$argon2id$") and "segredo123" not in linha[1]


def test_perfil_nao_pode_ser_escolhido_no_cadastro(cliente):
    r = cliente.post("/api/cadastro", json=dados_cadastro(perfil="ADMIN"))
    assert r.status_code == 201 and r.json()["perfil"] == "CIDADAO"


@pytest.mark.parametrize("campo, valor, mensagem", [
    ("cpf", "123.456.789-00", "CPF inválido."),
    ("cpf", "111.111.111-11", "CPF inválido."),
    ("email", "sem-arroba.com", "E-mail inválido."),
    ("senha", "123", "A senha precisa ter no mínimo 6 caracteres."),
    ("nome", "Ana", "Informe nome e sobrenome."),
    ("data_nascimento", "2999-01-01", "Data de nascimento inválida."),
])
def test_cadastro_invalido(cliente, campo, valor, mensagem):
    r = cliente.post("/api/cadastro", json=dados_cadastro(**{campo: valor}))
    assert r.status_code == 422 and r.json()["detail"] == mensagem


def test_menor_de_18_e_recusado_sem_gravar_nada(cliente, sql):
    hoje = date.today()
    d = dados_cadastro(data_nascimento=date(hoje.year - 17, hoje.month, 1).isoformat())
    r = cliente.post("/api/cadastro", json=d)
    assert r.status_code == 422 and "18 anos" in r.json()["detail"]
    cpf = d["cpf"].replace(".", "").replace("-", "")
    assert sql.execute("SELECT count(*) FROM usuarios WHERE cpf = %s", (cpf,)).fetchone()[0] == 0


def test_cpf_duplicado(cliente):
    r = cliente.post("/api/cadastro", json=dados_cadastro(cpf="123.456.789-09"))   # CPF da Mariana
    assert r.status_code == 409 and r.json()["detail"] == "Este CPF já está cadastrado."


def test_email_duplicado_ignora_maiusculas(cliente):
    r = cliente.post("/api/cadastro", json=dados_cadastro(email=MARIANA.upper()))
    assert r.status_code == 409 and r.json()["detail"] == "Este e-mail já está cadastrado."


def test_login_por_email_e_por_cpf(cliente):
    assert cliente.get("/api/usuarios/me", headers=entrar(cliente, MARIANA)).json()["nome"] == "Mariana Souza"
    assert cliente.get("/api/usuarios/me", headers=entrar(cliente, "12345678909")).json()["id"] == 1


@pytest.mark.parametrize("ident, senha", [(MARIANA, "errada"), ("ninguem@exemplo.com", "urbani123"),
                                          (cpf_novo(), "urbani123")])
def test_login_invalido_tem_mensagem_unica(cliente, ident, senha):
    r = cliente.post("/api/login", json={"identificador": ident, "senha": senha})
    assert r.status_code == 401 and r.json()["detail"] == "E-mail/CPF ou senha incorretos."


@pytest.mark.parametrize("cabecalho", [{}, {"Authorization": "Bearer token-falso"}])
def test_rota_privada_sem_token_valido(cliente, cabecalho):
    assert cliente.get("/api/usuarios/me", headers=cabecalho).status_code == 401
    assert cliente.get("/api/ocorrencias", headers=cabecalho).status_code == 401


def test_conta_desativada_perde_acesso_na_hora(cliente, sql):
    d = dados_cadastro()
    uid = cliente.post("/api/cadastro", json=d).json()["id"]
    h = entrar(cliente, d["email"], d["senha"])
    sql.execute("UPDATE usuarios SET ativo = FALSE WHERE id = %s", (uid,))
    assert cliente.get("/api/usuarios/me", headers=h).status_code == 401


def test_completar_perfil(cliente):
    h = entrar(cliente, CARLOS)
    r = cliente.patch("/api/usuarios/me", json={"cidade": " São  Paulo ", "bairro": "Bela Vista"}, headers=h)
    assert r.status_code == 200 and r.json()["cidade"] == "São Paulo"


def test_cpf_e_imutavel_no_banco(sql):
    with pytest.raises(CheckViolation):
        sql.execute("UPDATE usuarios SET cpf = '52998224725' WHERE id = 2")
