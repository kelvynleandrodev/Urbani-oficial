"""Configurações lidas de variáveis de ambiente (ou do arquivo backend/.env).

Segredos nunca ficam no código: copie .env.example para .env e ajuste.
"""
import os
from pathlib import Path

_ENV = Path(__file__).resolve().parent.parent / ".env"


def _carregar_env() -> None:
    """Lê backend/.env (formato CHAVE=valor) sem sobrescrever o ambiente real."""
    if not _ENV.exists():
        return
    for linha in _ENV.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        os.environ.setdefault(chave.strip(), valor.strip().strip('"').strip("'"))


_carregar_env()

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://urbani:urbani@localhost:5432/urbani")
JWT_SECRET = os.environ.get("JWT_SECRET", "")
JWT_EXPIRA_MIN = int(os.environ.get("JWT_EXPIRA_MIN", "480"))  # 8 horas
CORS_ORIGENS = [o.strip() for o in os.environ.get(
    "CORS_ORIGENS", "http://127.0.0.1:5500,http://localhost:5500").split(",") if o.strip()]
FUSO = "America/Sao_Paulo"     # usado para calcular a idade pela data local
IDADE_MINIMA = 18

if len(JWT_SECRET) < 32:
    raise RuntimeError(
        "Defina JWT_SECRET com pelo menos 32 caracteres no backend/.env "
        "(ex.: python -c \"import secrets; print(secrets.token_hex(32))\")."
    )
