# Urbani — Plataforma de Zeladoria Urbana

Projeto Integrador · FATEC Cotia · DSM · Equipe: Felipe Ribeiro de Moraes, Kaique Daniel Rocha da Silva, Kelvyn Thainam Neves Leandro e Matheus Pedroso Ferreira.

O cidadão registra problemas da cidade (buraco, poste apagado, árvore em risco), outros moradores apoiam e a prefeitura acompanha e resolve.

São três telas sobre a mesma API e o mesmo banco. O login é um só (`index.html`) e leva cada perfil para a sua:

| Perfil | Tela | O que faz |
|---|---|---|
| Cidadão | `index.html` | Registra, apoia, denuncia e acompanha a linha do tempo e as fotos do serviço |
| Gestor / Admin | `gestor.html` | Painel de indicadores ao vivo, fila de prioridade, despacho de ordens de serviço, mapa em camadas, equipes e antifraude |
| Colaborador (equipe de campo) | `campo.html` | Recebe as ordens de serviço da equipe, traça rota, inicia, fotografa e conclui (feito para celular) |

**Fluxo integrado:** cidadão registra (`ABERTA`) → gestor despacha uma ordem de serviço para uma equipe (`EM_ANALISE`) → colaborador inicia em campo (`EM_ANDAMENTO`) → colaborador conclui com relato, foto e localização (`RESOLVIDA`). Cada passo entra na linha do tempo que o cidadão vê.

```
Front-end web (HTML + CSS + JavaScript puro)   →   API REST (Python + FastAPI)   →   PostgreSQL + PostGIS
   index.html, css/, js/                            backend/app/                       backend/db/migrations/
```

## Estrutura

```
Urbani-oficial/
├── index.html            cidadão: login, cadastro e painel (SPA)
├── gestor.html           gestor: painel, fila, mapa, equipes, antifraude
├── campo.html            equipe de campo: ordens de serviço (mobile)
├── css/                  base.css · auth.css · app.css · gestao.css · campo.css
├── js/
│   ├── api.js            cliente HTTP da API (endereço e token de sessão), usado pelas três telas
│   ├── app.js            cidadão: abas, cards, mapa Leaflet, apoios, nova ocorrência, denúncia
│   ├── auth.js           login, cadastro, sessão e redirecionamento por perfil
│   ├── comum.js          utilitários das telas de gestão e campo (sessão, tempo real, fotos, GPS)
│   ├── gestor.js         painel do gestor
│   └── campo.js          app da equipe de campo
└── backend/
    ├── app/              código da API (rotas, validações, segurança)
    ├── db/migrations/    001_esquema.sql · 002_dados_demo.sql · 003_gestao_campo.sql · 004_dados_demo_gestao.sql
    ├── tests/            79 testes automatizados contra um PostgreSQL real
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
| Colaborador (equipe Pavimentação) | joao.pereira@urbani.exemplo.com | 700.131.876-00 |
| Colaboradora (equipe Iluminação Pública) | ana.ribeiro@urbani.exemplo.com | 700.147.714-11 |
| Colaboradora (equipe Arborização) | luciana.costa@urbani.exemplo.com | 700.155.633-59 |
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

### Integração (qualquer perfil logado)

| Método | Rota | O que faz |
|---|---|---|
| GET | `/api/pulso` | Versão dos dados (um número que muda a cada escrita). As telas consultam a cada 5 s e só recarregam quando muda |
| POST | `/api/ocorrencias/{id}/denuncias` | Denuncia a ocorrência (uma vez por conta; não a própria) |
| GET | `/api/ocorrencias/{id}/fotos` · `/api/fotos/{id}` | Fotos antes/depois anexadas pela equipe |

### Gestão (🔒 GESTOR, ADMIN) — prefixo `/api/gestao`

| Método | Rota | O que faz |
|---|---|---|
| GET | `/fila` | Fila de prioridade com prazo (SLA), apoios válidos, denúncias e OS. Filtros: `situacao`, `status`, `categoria_id`, `urgencia`, `atrasadas`, `sem_os` |
| GET | `/ocorrencias/{id}` | Ficha completa: histórico, auditoria, ordens, denúncias, apoios suspeitos, possíveis duplicatas |
| PATCH | `/ocorrencias/{id}/urgencia` | Reclassifica a urgência (motivo obrigatório, auditado) |
| POST | `/ocorrencias/{id}/ordens` | Despacha: cria a ordem de serviço para uma equipe |
| POST | `/ordens/{id}/cancelar` | Cancela a OS ativa |
| POST | `/ocorrencias/{id}/duplicata` | Unifica com outra ocorrência e transfere os apoios |
| POST | `/ocorrencias/{id}/apoios/invalidar-suspeitos` | Tira do ranking os apoios de contas recém-criadas |
| POST | `/ocorrencias/{id}/denuncias/analisar` | Parecer das denúncias pendentes |
| GET | `/painel?dias=30` | KPIs: tempo de 1ª resposta e de solução (média e mediana), % no prazo, taxa de validação, série diária, categorias, equipes, densidade por região, validação por usuário |
| GET | `/mapa` | Pontos e células de densidade para as camadas do mapa |
| GET | `/fraude` | Alertas: rajada de apoios, contas recém-criadas, denúncias, duplicatas, apoio recíproco, autor reincidente, conclusão fora do local |
| GET/POST | `/equipes`, `/equipes/{id}/membros` | Equipes e membros |
| GET/POST/PATCH | `/usuarios`, `/usuarios/{id}` | Contas de servidores; suspender/reativar conta (motivo obrigatório) |

### Campo (🔒 COLABORADOR) — prefixo `/api/campo`

| Método | Rota | O que faz |
|---|---|---|
| GET | `/ordens` | OS da minha equipe (`situacao=ativas|encerradas`; com `latitude`/`longitude` devolve a distância) |
| POST | `/ordens/{id}/iniciar` | Inicia: ocorrência vai para `EM_ANDAMENTO` |
| POST | `/ordens/{id}/fotos` | Anexa foto antes/depois (JPEG, PNG ou WebP até 2 MB) |
| POST | `/ordens/{id}/concluir` | Conclui com relato e posição: ocorrência vai para `RESOLVIDA` |
| POST | `/ordens/{id}/devolver` | Devolve ao gestor com o motivo do impedimento |

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
- **Prioridade:** ocorrências em aberto primeiro, depois maior urgência, depois mais apoios **válidos**, depois as que esperam há mais tempo. A fila do gestor sai de um índice parcial na mesma ordem (`ocorrencias_fila_ix`).
- **Blindagem do ranking:** `apoios_total` é o que o cidadão vê; `apoios_validos` é o que conta. Apoio de conta com menos de 24 h de vida fica em carência; cada conta dá no máximo 20 apoios por hora; suspender uma conta tira todos os apoios dela do ranking na hora; a urgência informada pelo cidadão pode ser reclassificada pelo gestor. Os limites ficam na tabela `parametros`.
- **Ordem de serviço:** no máximo uma OS ativa por ocorrência (índice único parcial); transições `ATRIBUIDA → EM_EXECUCAO → CONCLUIDA` (ou `DEVOLVIDA` / `CANCELADA`) garantidas por trigger; encerrar a ocorrência cancela a OS ativa.
- **Prova de presença:** ao concluir, a API mede a distância entre o aparelho e o local. Acima de 200 m, ou sem GPS, o serviço é aceito mas vira alerta para o gestor.
- **Prazos (SLA):** tabela `sla_urgencia` (alta: resposta em 4 h e solução em 48 h; média: 24 h e 5 dias; baixa: 48 h e 10 dias).
- **Auditoria:** reclassificação, unificação, invalidação de apoios e suspensão de contas ficam na tabela `auditoria`, que só aceita inserção.
- **Privacidade:** listagens mostram só o nome do autor; CPF e e-mail aparecem apenas para o próprio usuário.

## Testes

Os testes criam um banco separado (`urbani_teste`), aplicam as migrações e falam com o PostgreSQL de verdade.

```bash
cd backend
python -m pytest -v
```

79 testes. Os de gestão e campo (`test_gestao.py`, `test_campo.py`) cobrem permissões por perfil, ordem da fila, carência e limite de apoios, suspensão de conta, despacho, cancelamento, duplicatas, denúncias, painel, antifraude, o fluxo completo do despacho até o cidadão, prova de presença, devolução e fotos. Os 41 originais cobrem: cadastro válido e inválido (CPF, e-mail, senha, nome, data), menor de 18 sem gravar nada, CPF e e-mail duplicados, login por e-mail e CPF, login inválido, acesso sem token, conta desativada, ocorrência válida e inválida, coordenadas inválidas, antifraude, persistência, filtros, prioridade, consulta espacial por raio, permissão e transições de status, histórico imutável, CPF imutável, apoio válido, duplicado, próprio e em ocorrência encerrada.

## Situação atual

| Item | Situação |
|---|---|
| Cadastro, login, sessão, perfil | Implementado e testado |
| Ocorrências com localização PostGIS, filtros, prioridade, proximidade | Implementado e testado |
| Apoios com unicidade e regras antifraude | Implementado e testado |
| Mudança de status pelo gestor com histórico | Implementado e testado |
| Painel do gestor (fila, despacho, KPIs ao vivo, equipes, antifraude) | Implementado e testado |
| App da equipe de campo (ordens, rota, fotos, conclusão com GPS) | Implementado e testado |
| Denúncia | Implementada: vai para a análise do gestor |
| Mapa do gestor e do campo | Leaflet + OpenStreetMap, com camadas por status e densidade |
| Mapa do cidadão | Leaflet + OpenStreetMap: marcadores por status, popup que leva à Comunidade e escolha do local clicando no mapa |
| Tempo real | Consulta leve de versão a cada 5 s (`/api/pulso`). SSE ou WebSocket com Redis fica para o módulo Java |
| Upload de fotos | Equipe de campo: implementado (antes/depois). Cidadão: pendente (campo aparece como "em breve") |
| Encerrar sessão no servidor (revogar token) | Pendente: "Sair" apaga o token no navegador |
| Limite de tentativas de login | Pendente |
| App Flutter, módulo Java + Redis | Planejado para depois da entrega web |


## Publicar no Render (passo a passo)

1. Suba esta pasta para um repositório no GitHub (a raiz deve ter `render.yaml`, `backend/`, `index.html`…).
2. No Render: **New → Blueprint** → escolha o repositório → **Apply**. Ele cria o banco `urbani-db` (PostgreSQL 16) e o serviço web `urbani`.
3. A cada deploy o serviço roda `python -m app.migrar` (aplica só as migrações novas, sem apagar dados) e depois sobe a API, que também serve o site.
4. Quando o deploy ficar **Live**, abra a URL `https://urbani-XXXX.onrender.com/`. Teste: `/api/saude` deve responder `{"status":"ok"}`.

**Contas de teste** (senha `urbani123`): cidadã `mariana.souza@exemplo.com` · gestora `fernanda.alves@prefeitura.exemplo.gov.br` · admin `admin@urbani.exemplo.com` · campo `joao.pereira@urbani.exemplo.com`.

**Para produção real:** remova a migração `004_dados_demo_gestao.sql` (e `002`) antes do primeiro deploy e troque as senhas das contas administrativas.

**Observações do plano gratuito:** o serviço dorme após ~15 min sem acesso (o primeiro acesso leva ~50 s) e o banco gratuito expira após 30 dias. O mapa usa os tiles públicos do OpenStreetMap, adequados para testes; em produção com muito tráfego, use um provedor de tiles próprio. Os anúncios são fictícios (`ANUNCIOS` em `js/app.js`).
