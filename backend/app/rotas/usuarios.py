"""Cadastro, login e dados do usuário autenticado."""
from fastapi import APIRouter, Depends, HTTPException, status
from psycopg import Connection
from psycopg.errors import UniqueViolation

from ..db import conexao
from ..esquemas import CadastroEntrada, LoginEntrada, LoginSaida, PerfilEntrada, UsuarioSaida
from ..seguranca import conferir_senha, gerar_hash, gerar_token, usuario_atual
from ..validacoes import formatar_cpf, so_digitos

router = APIRouter(prefix="/api", tags=["Usuários"])

_COLUNAS = "id, nome, cpf, email, data_nascimento, cidade, bairro, perfil, criado_em"


def _saida(u: dict) -> UsuarioSaida:
    return UsuarioSaida(**{**{k: u[k] for k in UsuarioSaida.model_fields}, "cpf": formatar_cpf(u["cpf"])})


@router.post("/cadastro", response_model=UsuarioSaida, status_code=status.HTTP_201_CREATED,
             summary="Criar conta de cidadão")
def cadastrar(dados: CadastroEntrada, conn: Connection = Depends(conexao)):
    """Valida CPF, idade mínima e duplicidade **antes** de gravar qualquer dado.
    O perfil é sempre CIDADAO: gestores e administradores não se cadastram por aqui."""
    existe = conn.execute(
        "SELECT cpf = %s AS mesmo_cpf FROM usuarios WHERE cpf = %s OR lower(email) = %s LIMIT 1",
        (dados.cpf, dados.cpf, dados.email)).fetchone()
    if existe:
        msg = "Este CPF já está cadastrado." if existe["mesmo_cpf"] else "Este e-mail já está cadastrado."
        raise HTTPException(status.HTTP_409_CONFLICT, msg)
    try:
        u = conn.execute(
            f"INSERT INTO usuarios (nome, cpf, email, senha_hash, data_nascimento, perfil) "
            f"VALUES (%s, %s, %s, %s, %s, 'CIDADAO') RETURNING {_COLUNAS}",
            (dados.nome, dados.cpf, dados.email, gerar_hash(dados.senha), dados.data_nascimento),
        ).fetchone()
    except UniqueViolation:
        # Dois cadastros iguais ao mesmo tempo: o índice único do banco barra o segundo.
        raise HTTPException(status.HTTP_409_CONFLICT, "CPF ou e-mail já cadastrado.")
    return _saida(u)


@router.post("/login", response_model=LoginSaida, summary="Entrar com e-mail ou CPF")
def login(dados: LoginEntrada, conn: Connection = Depends(conexao)):
    ident = dados.identificador.strip().lower()
    if "@" in ident:
        u = conn.execute("SELECT * FROM usuarios WHERE lower(email) = %s", (ident,)).fetchone()
    else:
        u = conn.execute("SELECT * FROM usuarios WHERE cpf = %s", (so_digitos(ident),)).fetchone()
    # Mesma mensagem para "não existe" e "senha errada": não revela quem tem conta.
    if not conferir_senha(dados.senha, u["senha_hash"] if u else None) or not u["ativo"]:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "E-mail/CPF ou senha incorretos.")
    return LoginSaida(token=gerar_token(u["id"]), usuario=_saida(u))


@router.get("/usuarios/me", response_model=UsuarioSaida, summary="Dados do usuário logado")
def meus_dados(u: dict = Depends(usuario_atual)):
    return _saida(u)


@router.patch("/usuarios/me", response_model=UsuarioSaida, summary="Completar cidade e bairro")
def completar_perfil(dados: PerfilEntrada, u: dict = Depends(usuario_atual),
                     conn: Connection = Depends(conexao)):
    novo = conn.execute(
        f"UPDATE usuarios SET cidade = %s, bairro = %s WHERE id = %s RETURNING {_COLUNAS}",
        (dados.cidade, dados.bairro, u["id"])).fetchone()
    return _saida(novo)
