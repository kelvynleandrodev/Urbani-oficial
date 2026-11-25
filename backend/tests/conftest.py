"""Prepara um banco de TESTE separado (urbani_teste), recriado a cada execução.

Os testes falam com um PostgreSQL + PostGIS de verdade: nada é simulado.
Use TEST_DATABASE_URL para apontar outro banco; por padrão é o mesmo
servidor do DATABASE_URL com o nome trocado para urbani_teste.
"""
import itertools
import os

import psycopg
import pytest
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from app import config

URL_TESTE = os.environ.get("TEST_DATABASE_URL") or make_conninfo(config.DATABASE_URL, dbname="urbani_teste")
config.DATABASE_URL = URL_TESTE        # antes de importar app.db, que cria o pool

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.migrar import migrar  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def banco_de_teste():
    nome = conninfo_to_dict(URL_TESTE)["dbname"]
    admin = make_conninfo(URL_TESTE, dbname="postgres")
    with psycopg.connect(admin, autocommit=True) as c:
        c.execute(f'DROP DATABASE IF EXISTS "{nome}" WITH (FORCE)')
        c.execute(f'CREATE DATABASE "{nome}"')
    migrar(URL_TESTE)                  # esquema + dados de demonstração
    yield


@pytest.fixture(scope="session")
def cliente():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def sql():
    """Conexão direta ao banco de teste, para conferir o que foi gravado."""
    with psycopg.connect(URL_TESTE, autocommit=True) as c:
        yield c


# ------------------------------ Ajudantes ------------------------------
_seq = itertools.count(100_000_001)


def cpf_novo() -> str:
    """Gera um CPF válido e ainda não usado nos testes."""
    d = [int(x) for x in str(next(_seq))[:9]]
    for t in (9, 10):
        d.append(sum(d[i] * (t + 1 - i) for i in range(t)) * 10 % 11 % 10)
    s = "".join(map(str, d))
    return f"{s[:3]}.{s[3:6]}.{s[6:9]}-{s[9:]}"


def dados_cadastro(**extra) -> dict:
    cpf = cpf_novo()
    return {"nome": "Pessoa Teste", "cpf": cpf, "data_nascimento": "1990-05-10",
            "email": f"t{cpf.replace('.', '').replace('-', '')}@exemplo.com", "senha": "segredo123", **extra}


def entrar(cliente, identificador: str, senha: str = "urbani123") -> dict:
    r = cliente.post("/api/login", json={"identificador": identificador, "senha": senha})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def novo_cidadao(cliente) -> dict:
    d = dados_cadastro()
    assert cliente.post("/api/cadastro", json=d).status_code == 201
    return entrar(cliente, d["email"], d["senha"])


def ocorrencia(lat: float = -23.5600, lng: float = -46.6500, **extra) -> dict:
    return {"categoria_id": 1, "titulo": "Buraco de teste", "descricao": "Descrição de teste",
            "urgencia": "MEDIA", "endereco_referencia": "Rua de Teste, 1",
            "latitude": lat, "longitude": lng, **extra}


MARIANA = "mariana.souza@exemplo.com"     # cidadã (dados de demonstração)
CARLOS = "carlos.lima@exemplo.com"        # cidadão
FERNANDA = "fernanda.alves@prefeitura.exemplo.gov.br"   # gestora


# ------------------------- Ajudantes de gestão e campo -------------------------
ADMIN = "admin@urbani.exemplo.com"
_n = itertools.count(1)


def envelhecer_conta(sql, cabecalho: dict, cliente, dias: int = 2) -> None:
    """Faz a conta parecer antiga: os apoios dela passam a contar no ranking."""
    eu = cliente.get("/api/usuarios/me", headers=cabecalho).json()
    sql.execute("UPDATE usuarios SET criado_em = now() - make_interval(days => %s) WHERE id = %s", (dias, eu["id"]))


def nova_equipe(cliente, gestor: dict, membros: int = 1) -> tuple[int, list[dict]]:
    """Cria uma equipe com colaboradores novos. Devolve (equipe_id, [cabeçalhos de login])."""
    r = cliente.post("/api/gestao/equipes", json={"nome": f"Equipe Teste {next(_n)}"}, headers=gestor)
    assert r.status_code == 201, r.text
    equipe_id, logins = r.json()["id"], []
    for _ in range(membros):
        d = dados_cadastro(perfil="COLABORADOR", equipe_id=equipe_id)
        assert cliente.post("/api/gestao/usuarios", json=d, headers=gestor).status_code == 201
        logins.append(entrar(cliente, d["email"], d["senha"]))
    return equipe_id, logins


def nova_ocorrencia(cliente, **extra) -> tuple[int, dict]:
    """Ocorrência nova em um ponto único. Devolve (id, cabeçalho do autor)."""
    autor = novo_cidadao(cliente)
    k = next(_n)
    dados = ocorrencia(-22.0 - k * 0.01, -45.0 - k * 0.01, **extra)
    r = cliente.post("/api/ocorrencias", json=dados, headers=autor)
    assert r.status_code == 201, r.text
    return r.json()["id"], autor
