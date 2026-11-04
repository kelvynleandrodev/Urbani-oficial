"""Senhas (Argon2id), tokens de acesso (JWT) e controle de permissões."""
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from psycopg import Connection

from . import config
from .db import conexao

_hasher = PasswordHasher()          # Argon2id com parâmetros recomendados
_bearer = HTTPBearer(auto_error=False)

# Hash fixo usado quando o usuário não existe: o login leva o mesmo tempo
# com ou sem conta, e ninguém descobre e-mails cadastrados pelo tempo de resposta.
_HASH_FALSO = _hasher.hash("senha-que-nao-existe")


def gerar_hash(senha: str) -> str:
    return _hasher.hash(senha)


def conferir_senha(senha: str, senha_hash: str | None) -> bool:
    try:
        return _hasher.verify(senha_hash or _HASH_FALSO, senha) and senha_hash is not None
    except (VerificationError, InvalidHashError):
        return False


def gerar_token(usuario_id: int) -> str:
    agora = datetime.now(timezone.utc)
    dados = {"sub": str(usuario_id), "iat": agora, "exp": agora + timedelta(minutes=config.JWT_EXPIRA_MIN)}
    return jwt.encode(dados, config.JWT_SECRET, algorithm="HS256")


_NAO_AUTENTICADO = HTTPException(
    status.HTTP_401_UNAUTHORIZED, "Sessão inválida ou expirada. Entre novamente.",
    headers={"WWW-Authenticate": "Bearer"},
)


def usuario_atual(
    cred: HTTPAuthorizationCredentials | None = Depends(_bearer),
    conn: Connection = Depends(conexao),
) -> dict:
    """Lê o token do cabeçalho Authorization e devolve o usuário do banco.

    O usuário é buscado a cada requisição: se a conta for desativada,
    o acesso é cortado na hora, mesmo com um token ainda válido.
    """
    if cred is None:
        raise _NAO_AUTENTICADO
    try:
        dados = jwt.decode(cred.credentials, config.JWT_SECRET, algorithms=["HS256"])
        usuario_id = int(dados["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise _NAO_AUTENTICADO
    u = conn.execute(
        "SELECT id, nome, cpf, email, data_nascimento, cidade, bairro, perfil, ativo, criado_em "
        "FROM usuarios WHERE id = %s", (usuario_id,)).fetchone()
    if not u or not u["ativo"]:
        raise _NAO_AUTENTICADO
    return u


def exigir_perfil(*perfis: str):
    """Cria uma dependência que só deixa passar os perfis informados."""
    def verificar(u: dict = Depends(usuario_atual)) -> dict:
        if u["perfil"] not in perfis:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Seu perfil não tem permissão para esta ação.")
        return u
    return verificar
