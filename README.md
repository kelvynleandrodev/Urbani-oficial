# Urbani — Plataforma de Zeladoria Urbana

Projeto Integrador · FATEC Cotia · DSM · Equipe: Felipe Ribeiro de Moraes, Kaique Daniel Rocha da Silva, Kelvyn Thainam Neves Leandro e Matheus Pedroso Ferreira.

O cidadão registra problemas da cidade (buraco, poste apagado, árvore em risco), outros moradores apoiam e a prefeitura acompanha e resolve.

```
Front-end web (HTML + CSS + JavaScript puro)   →   API REST (Python + FastAPI)   →   PostgreSQL + PostGIS
   index.html, css/, js/                            backend/app/                       backend/db/migrations/
```

## Estrutura

```
Urbani-oficial/
├── index.html            telas de login, cadastro e painel (SPA)
├── css/                  base.css · auth.css · app.css
├── js/
│   ├── api.js            cliente HTTP da API (endereço e token de sessão)
│   ├── app.js            painel: abas, cards, mapa, apoios, nova ocorrência
│   └── auth.js           login, cadastro e sessão
└── backend/
    ├── app/              código da API (rotas, validações, segurança)
    ├── db/migrations/    001_esquema.sql (tabelas) · 002_dados_demo.sql (dados fictícios)
    ├── tests/            41 testes automatizados contra um PostgreSQL real
    ├── docker-compose.yml  PostgreSQL + PostGIS em um comando
    ├── requirements.txt
    └── .env.example      modelo de configuração
```

## Como rodar (passo a passo)

Você precisa de: **Python 3.11+**, **PostgreSQL 16 com PostGIS** e o **VS Code com a extensão Live Server**.

### 1. Banco de dados

**Opção A — com Docker** (mais simples):

```bash
cd backend
docker compose up -d
```

**Opção B — PostgreSQL instalado no Windows:** instale o PostgreSQL 16 e, no *Stack Builder* que abre ao final, marque **PostGIS** (em *Spatial Extensions*). Depois, no pgAdmin ou no `psql`, crie o banco:

```sql
CREATE DATABASE urbani;
```

### 2. API

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows (no Git Bash: source .venv/Scripts/activate)
pip install -r requirements.txt
copy .env.example .env          # Git Bash: cp .env.example .env
```

Abra o `.env` e ajuste:

- `DATABASE_URL`: com Docker, deixe como está. Com PostgreSQL local, use `postgresql://postgres:SUA_SENHA@localhost:5432/urbani`.
- `JWT_SECRET`: gere um com `python -c "import secrets; print(secrets.token_hex(32))"` e cole o resultado.

Crie as tabelas e os dados de demonstração, e suba a API:

```bash
python -m app.migrar
uvicorn app.main:app --reload
```

A API fica em `http://localhost:8000`. A documentação interativa (Swagger) fica em **http://localhost:8000/docs**: dá para testar cada rota pelo navegador.

### 3. Front-end

No VS Code, clique com o botão direito em `index.html` → **Open with Live Server**. Ele abre em `http://127.0.0.1:5500`, que já está liberado no CORS da API.

> Abrir o `index.html` com duplo clique **não funciona** mais: o navegador bloqueia chamadas de um arquivo local para a API. Use o Live Server.

### Contas de demonstração

Senha de todas: `urbani123`. CPFs fictícios.

| Perfil | E-mail | CPF |
|---|---|---|
| Cidadã (perfil incompleto) | mariana.souza@exemplo.com | 123.456.789-09 |
| Cidadão | carlos.lima@exemplo.com | 987.654.321-00 |
| Gestora | fernanda.alves@prefeitura.exemplo.gov.br | 246.813.579-28 |
| Administrador | admin@urbani.exemplo.com | 135.792.468-28 |

CPFs válidos e livres para testar o cadastro: `529.982.247-25`, `111.444.777-35`, `452.371.890-32`.

## Endpoints da API

Rotas marcadas com 🔒 exigem o cabeçalho `Authorization: Bearer <token>` recebido no login.

| Método | Rota | Quem pode | O que faz |
|---|---|---|---|
| GET | `/api/saude` | todos | Confere se API e banco estão no ar |
| POST | `/api/cadastro` | todos | Cria conta de cidadão (valida CPF, idade ≥ 18, duplicidade) |
| POST | `/api/login` | todos | Entra com e-mail **ou** CPF; devolve `token` e `usuario` |
| GET | `/api/usuarios/me` | 🔒 logado | Dados do próprio usuário |
| PATCH | `/api/usuarios/me` | 🔒 logado | Completa cidade e bairro |
| GET | `/api/categorias` | todos | Categorias ativas |
| GET | `/api/ocorrencias` | 🔒 logado | Lista com filtros `categoria_id`, `status`, `minhas`, `ordem` (`recentes`, `apoiadas`, `prioridade`) e paginação `limite`/`deslocamento` |
| GET | `/api/ocorrencias/proximas` | 🔒 logado | Ocorrências num raio: `latitude`, `longitude`, `raio_m` (PostGIS) |
| GET | `/api/ocorrencias/{id}` | 🔒 logado | Detalhe |
| POST | `/api/ocorrencias` | 🔒 logado | Registra ocorrência (começa como `ABERTA`) |
| PATCH | `/api/ocorrencias/{id}` | 🔒 GESTOR, ADMIN | Muda o status e grava no histórico |
| GET | `/api/ocorrencias/{id}/historico` | 🔒 logado | Linha do tempo de status |
| GET | `/api/ocorrencias/{id}/apoios` | 🔒 logado | Total de apoios e se eu apoiei |
| POST | `/api/ocorrencias/{id}/apoios` | 🔒 logado | Apoia (uma vez por conta) |
| DELETE | `/api/ocorrencias/{id}/apoios` | 🔒 logado | Retira o próprio apoio |

**Erros** sempre vêm como `{"detail": "mensagem em português"}`: 401 (sem login), 403 (sem permissão), 404 (não existe), 409 (duplicado ou mudança de status proibida), 422 (dado inválido).

Exemplo — registrar ocorrência:

```http
POST /api/ocorrencias
Authorization: Bearer eyJhbGciOi...
Content-Type: application/json

{ "categoria_id": 1, "titulo": "Bueiro sem tampa", "descricao": "Risco para pedestres",
  "urgencia": "ALTA", "endereco_referencia": "Rua Haddock Lobo, 300",
  "latitude": -23.556, "longitude": -46.662 }
```

Resposta `201`: a ocorrência com `id`, `status: "ABERTA"`, `autor_nome`, `categoria_nome`, `apoios_total`, `apoiado_por_mim`, `criado_em`…

## Regras de negócio garantidas no servidor

- **Cadastro:** CPF com dígitos verificadores válidos; CPF e e-mail únicos (índices `UNIQUE` no banco); idade mínima de 18 anos no fuso de São Paulo, checada **antes** de gravar; perfil sempre `CIDADAO`.
- **CPF imutável:** um trigger no banco recusa qualquer alteração de CPF.
- **Senhas:** guardadas com **Argon2id**; o texto da senha nunca é gravado. Login errado sempre responde a mesma mensagem, exista a conta ou não.
- **Sessão:** token JWT válido por 8 horas. A conta é conferida a cada requisição: desativar um usuário corta o acesso na hora.
- **Ocorrência:** coordenadas validadas (latitude −90 a 90, longitude −180 a 180) e gravadas como ponto PostGIS (`geometry(Point, 4326)`, ordem longitude/latitude). Antifraude: a mesma pessoa não registra duas ocorrências da mesma categoria a menos de 50 m em 24 h.
- **Status:** só GESTOR e ADMIN alteram. Transições permitidas: `ABERTA → EM_ANALISE / EM_ANDAMENTO / REJEITADA`, `EM_ANALISE → EM_ANDAMENTO / REJEITADA`, `EM_ANDAMENTO → RESOLVIDA`. Cada mudança vira uma linha nova em `historico_status`, que não pode ser editada nem apagada (trigger).
- **Apoios:** chave primária `(usuario_id, ocorrencia_id)` impede apoio duplicado; trigger impede apoiar a própria ocorrência ou uma ocorrência encerrada; o total (`apoios_total`) é mantido por trigger, sem `COUNT(*)` a cada listagem.
- **Prioridade:** ocorrências em aberto primeiro, depois maior urgência, depois mais apoios, depois as que esperam há mais tempo.
- **Privacidade:** listagens mostram só o nome do autor; CPF e e-mail aparecem apenas para o próprio usuário.

## Testes

Os testes criam um banco separado (`urbani_teste`), aplicam as migrações e falam com o PostgreSQL de verdade.

```bash
cd backend
python -m pytest -v
```

41 testes cobrem: cadastro válido e inválido (CPF, e-mail, senha, nome, data), menor de 18 sem gravar nada, CPF e e-mail duplicados, login por e-mail e CPF, login inválido, acesso sem token, conta desativada, ocorrência válida e inválida, coordenadas inválidas, antifraude, persistência, filtros, prioridade, consulta espacial por raio, permissão e transições de status, histórico imutável, CPF imutável, apoio válido, duplicado, próprio e em ocorrência encerrada.

## Situação atual

| Item | Situação |
|---|---|
| Cadastro, login, sessão, perfil | Implementado e testado |
| Ocorrências com localização PostGIS, filtros, prioridade, proximidade | Implementado e testado |
| Apoios com unicidade e regras antifraude | Implementado e testado |
| Mudança de status pelo gestor com histórico | Implementado e testado |
| Mapa web | Protótipo em CSS (marcadores reais, sem mapa de ruas). Leaflet + OpenStreetMap é o próximo passo |
| Upload de fotos | Pendente (campo aparece como "em breve") |
| Denúncia | Simulada no front |
| Encerrar sessão no servidor (revogar token) | Pendente: "Sair" apaga o token no navegador |
| Limite de tentativas de login | Pendente |
| App Flutter, módulo Java + Redis, dashboards | Planejado para depois da entrega web |
