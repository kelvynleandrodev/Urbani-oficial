"""Formatos de entrada e saída da API (Pydantic).

Os validadores levantam ValueError com mensagens em português;
o main.py transforma esses erros na resposta 422 que o front exibe.
"""
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from . import config
from .validacoes import EMAIL_RE, cpf_valido, hoje, idade, so_digitos

Status = Literal["ABERTA", "EM_ANALISE", "EM_ANDAMENTO", "RESOLVIDA", "REJEITADA"]
Urgencia = Literal["BAIXA", "MEDIA", "ALTA"]


# ----------------------------- Usuários -----------------------------
class CadastroEntrada(BaseModel):
    nome: str = Field(max_length=120)
    cpf: str
    data_nascimento: date
    email: str = Field(max_length=254)
    senha: str = Field(max_length=128)

    @field_validator("nome")
    @classmethod
    def _nome(cls, v: str) -> str:
        v = " ".join(v.split())
        if len(v.split(" ")) < 2:
            raise ValueError("Informe nome e sobrenome.")
        return v

    @field_validator("cpf")
    @classmethod
    def _cpf(cls, v: str) -> str:
        if not cpf_valido(v):
            raise ValueError("CPF inválido.")
        return so_digitos(v)

    @field_validator("data_nascimento")
    @classmethod
    def _nascimento(cls, v: date) -> date:
        if v > hoje() or idade(v) > 120:
            raise ValueError("Data de nascimento inválida.")
        if idade(v) < config.IDADE_MINIMA:
            raise ValueError(f"É preciso ter {config.IDADE_MINIMA} anos ou mais para criar uma conta.")
        return v

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        v = v.strip().lower()
        if not EMAIL_RE.match(v):
            raise ValueError("E-mail inválido.")
        return v

    @field_validator("senha")
    @classmethod
    def _senha(cls, v: str) -> str:
        if len(v) < 6:
            raise ValueError("A senha precisa ter no mínimo 6 caracteres.")
        return v


class LoginEntrada(BaseModel):
    identificador: str = Field(description="E-mail ou CPF")
    senha: str


class PerfilEntrada(BaseModel):
    cidade: str = Field(min_length=1, max_length=80)
    bairro: str = Field(min_length=1, max_length=80)

    @field_validator("cidade", "bairro")
    @classmethod
    def _texto(cls, v: str) -> str:
        v = " ".join(v.split())
        if not v:
            raise ValueError("Informe cidade e bairro.")
        return v


class UsuarioSaida(BaseModel):
    id: int
    nome: str
    cpf: str               # formatado e visível só para o próprio usuário
    email: str
    data_nascimento: date
    cidade: str | None
    bairro: str | None
    perfil: str
    criado_em: datetime


class LoginSaida(BaseModel):
    token: str
    usuario: UsuarioSaida


# ---------------------------- Categorias ----------------------------
class CategoriaSaida(BaseModel):
    id: int
    nome: str
    descricao: str | None


# ---------------------------- Ocorrências ---------------------------
class OcorrenciaEntrada(BaseModel):
    categoria_id: int
    titulo: str = Field(max_length=120)
    descricao: str = Field(max_length=4000)
    urgencia: Urgencia = "MEDIA"
    endereco_referencia: str = Field(max_length=200)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)

    @field_validator("titulo", "descricao", "endereco_referencia")
    @classmethod
    def _obrigatorio(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Preencha título, descrição e endereço.")
        return v


class StatusEntrada(BaseModel):
    status: Status
    observacao: str | None = Field(default=None, max_length=1000)


class OcorrenciaSaida(BaseModel):
    id: int
    titulo: str
    descricao: str
    urgencia: Urgencia
    status: Status
    categoria_id: int
    categoria_nome: str
    usuario_id: int
    autor_nome: str
    endereco_referencia: str | None
    latitude: float
    longitude: float
    apoios_total: int
    apoios_validos: int = 0     # apoios que contam no ranking (ver 003_gestao_campo.sql)
    apoiado_por_mim: bool
    criado_em: datetime
    atualizado_em: datetime
    distancia_m: float | None = None


class HistoricoSaida(BaseModel):
    status_anterior: Status | None
    status_novo: Status
    observacao: str | None
    autor_nome: str
    alterado_em: datetime


class ApoiosSaida(BaseModel):
    ocorrencia_id: int
    apoios_total: int
    apoiado_por_mim: bool


# ------------------- Gestão e campo (003_gestao_campo.sql) -------------------
StatusOS = Literal["ATRIBUIDA", "EM_EXECUCAO", "CONCLUIDA", "DEVOLVIDA", "CANCELADA"]
MotivoDenuncia = Literal["FALSA", "DUPLICADA", "OFENSIVA", "LOCAL_ERRADO", "OUTRO"]


def _texto_obrigatorio(v: str, minimo: int, mensagem: str) -> str:
    v = " ".join((v or "").split())
    if len(v) < minimo:
        raise ValueError(mensagem)
    return v


class DenunciaEntrada(BaseModel):
    motivo: MotivoDenuncia
    detalhe: str | None = Field(default=None, max_length=500)


class UrgenciaEntrada(BaseModel):
    urgencia: Urgencia
    motivo: str = Field(max_length=500)

    @field_validator("motivo")
    @classmethod
    def _motivo(cls, v: str) -> str:
        return _texto_obrigatorio(v, 5, "Explique o motivo da reclassificação (mínimo de 5 caracteres).")


class MotivoEntrada(BaseModel):
    motivo: str = Field(max_length=500)

    @field_validator("motivo")
    @classmethod
    def _motivo(cls, v: str) -> str:
        return _texto_obrigatorio(v, 5, "Informe o motivo (mínimo de 5 caracteres).")


class DuplicataEntrada(BaseModel):
    principal_id: int


class DenunciasAnaliseEntrada(BaseModel):
    procedente: bool


class OrdemEntrada(BaseModel):
    equipe_id: int
    responsavel_id: int | None = None
    instrucoes: str | None = Field(default=None, max_length=1000)
    prazo_em: datetime | None = None      # vazio = prazo do SLA da urgência


class EquipeEntrada(BaseModel):
    nome: str = Field(max_length=80)
    categoria_id: int | None = None

    @field_validator("nome")
    @classmethod
    def _nome(cls, v: str) -> str:
        return _texto_obrigatorio(v, 3, "Informe o nome da equipe (mínimo de 3 caracteres).")


class MembroEntrada(BaseModel):
    usuario_id: int


class ServidorEntrada(CadastroEntrada):
    """Conta de servidor (colaborador de campo ou gestor), criada pela gestão."""
    perfil: Literal["COLABORADOR", "GESTOR"] = "COLABORADOR"
    equipe_id: int | None = None


class ContaSituacaoEntrada(MotivoEntrada):
    ativo: bool


class PosicaoEntrada(BaseModel):
    """Posição do aparelho do colaborador (opcional: o GPS pode falhar)."""
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)


class ConclusaoEntrada(PosicaoEntrada):
    relatorio: str = Field(max_length=2000)

    @field_validator("relatorio")
    @classmethod
    def _relatorio(cls, v: str) -> str:
        return _texto_obrigatorio(v, 10, "Descreva o serviço executado (mínimo de 10 caracteres).")


class FotoEntrada(BaseModel):
    tipo: Literal["ANTES", "DEPOIS"]
    imagem: str = Field(description="Data URL: data:image/jpeg;base64,...", max_length=2_900_000)
