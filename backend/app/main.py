"""Ponto de entrada da API do Urbani.

Rodar:  uvicorn app.main:app --reload      (dentro da pasta backend)
Docs:   http://localhost:8000/docs         (Swagger gerado automaticamente)
"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config
from .db import pool
from .rotas import campo, categorias, compartilhadas, gestao, ocorrencias, usuarios


@asynccontextmanager
async def ciclo_de_vida(_: FastAPI):
    pool.open(wait=True)        # abre as conexões ao iniciar
    yield
    pool.close()                # e fecha ao encerrar


app = FastAPI(
    title="Urbani API",
    version="1.1.0",
    description="API REST da plataforma de zeladoria urbana Urbani: cidadão, gestor e equipe de campo.",
    lifespan=ciclo_de_vida,
)

# Só as origens listadas em CORS_ORIGENS (ex.: o Live Server) podem chamar a API pelo navegador.
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGENS,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.exception_handler(RequestValidationError)
async def erro_de_validacao(_: Request, exc: RequestValidationError):
    """Transforma os erros do Pydantic em mensagens curtas em português."""
    mensagens = []
    for e in exc.errors():
        campo = str(e["loc"][-1]) if e.get("loc") else "dados"
        if e["type"] == "missing":
            mensagens.append(f"Campo obrigatório: {campo}.")
        elif e["type"] == "value_error":
            mensagens.append(str(e["msg"]).removeprefix("Value error, "))
        else:
            mensagens.append(f"Valor inválido no campo {campo}.")
    return JSONResponse(status_code=422, content={"detail": mensagens[0], "erros": mensagens})


@app.exception_handler(Exception)
async def erro_inesperado(_: Request, exc: Exception):
    """Erros não tratados: resposta genérica, sem expor detalhes internos."""
    return JSONResponse(status_code=500, content={"detail": "Erro interno. Tente novamente em instantes."})


@app.get("/api/saude", tags=["Sistema"], summary="Verifica se a API e o banco estão no ar")
def saude():
    with pool.connection() as conn:
        conn.execute("SELECT 1")
    return {"status": "ok"}


app.include_router(usuarios.router)
app.include_router(categorias.router)
app.include_router(compartilhadas.router)   # antes de ocorrencias: /ocorrencias/{id}/denuncias e /fotos
app.include_router(ocorrencias.router)
app.include_router(gestao.router)
app.include_router(campo.router)

# Front-end no mesmo endereço (publicação no Render).
# Só as páginas abaixo, css/ e js/ ficam públicos; o resto do repositório não.
_FRONT = Path(__file__).resolve().parents[2]
_PAGINAS = {"": "index.html", "index.html": "index.html",        # cidadão (e login de todos)
            "gestor.html": "gestor.html", "gestor": "gestor.html",    # painel do gestor
            "campo.html": "campo.html", "campo": "campo.html"}        # app da equipe de campo
if (_FRONT / "index.html").exists():
    app.mount("/css", StaticFiles(directory=_FRONT / "css"), name="css")
    app.mount("/js", StaticFiles(directory=_FRONT / "js"), name="js")

    def _servir(arquivo: str):
        return lambda: FileResponse(_FRONT / arquivo)

    for _rota, _arquivo in _PAGINAS.items():
        if (_FRONT / _arquivo).exists():
            app.add_api_route("/" + _rota, _servir(_arquivo), include_in_schema=False)
