"""Regras de validação que valem no servidor (o front só repete para conforto do usuário)."""
import re
from datetime import date, datetime
from zoneinfo import ZoneInfo

from . import config

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]{2,}$")


def so_digitos(texto: str) -> str:
    return re.sub(r"\D", "", texto or "")


def cpf_valido(cpf: str) -> bool:
    """Confere os dois dígitos verificadores do CPF."""
    c = so_digitos(cpf)
    if len(c) != 11 or c == c[0] * 11:
        return False
    for t in (9, 10):
        soma = sum(int(c[i]) * (t + 1 - i) for i in range(t))
        if (soma * 10) % 11 % 10 != int(c[t]):
            return False
    return True


def formatar_cpf(cpf: str) -> str:
    c = so_digitos(cpf)
    return f"{c[:3]}.{c[3:6]}.{c[6:9]}-{c[9:]}"


def hoje() -> date:
    """Data de hoje no fuso de São Paulo (evita erro de um dia perto da meia-noite)."""
    return datetime.now(ZoneInfo(config.FUSO)).date()


def idade(nascimento: date, referencia: date | None = None) -> int:
    """Idade em anos completos, considerando se o aniversário já passou."""
    ref = referencia or hoje()
    anos = ref.year - nascimento.year
    if (ref.month, ref.day) < (nascimento.month, nascimento.day):
        anos -= 1
    return anos
