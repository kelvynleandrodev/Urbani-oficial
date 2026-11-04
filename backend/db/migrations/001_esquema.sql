-- =====================================================================
-- 001_esquema.sql · Estrutura do banco do Urbani (PostgreSQL + PostGIS)
-- Escopo: P0 da entrega web de 04/11/2026 (usuários, categorias,
-- ocorrências com localização, apoios e histórico de status).
-- =====================================================================

CREATE EXTENSION IF NOT EXISTS postgis;

-- ---------------------------------------------------------------------
-- USUÁRIOS
-- ---------------------------------------------------------------------
CREATE TABLE usuarios (
    id              BIGSERIAL PRIMARY KEY,
    nome            VARCHAR(120) NOT NULL,
    cpf             CHAR(11)     NOT NULL,           -- só dígitos
    email           VARCHAR(254) NOT NULL,
    senha_hash      TEXT         NOT NULL,           -- Argon2id, gerado pela API
    data_nascimento DATE         NOT NULL,
    cidade          VARCHAR(80),
    bairro          VARCHAR(80),
    perfil          VARCHAR(10)  NOT NULL DEFAULT 'CIDADAO'
                    CHECK (perfil IN ('CIDADAO', 'GESTOR', 'ADMIN')),
    ativo           BOOLEAN      NOT NULL DEFAULT TRUE,
    criado_em       TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT usuarios_cpf_formato CHECK (cpf ~ '^[0-9]{11}$')
);
CREATE UNIQUE INDEX usuarios_cpf_uk   ON usuarios (cpf);
-- E-mail único sem diferenciar maiúsculas de minúsculas
CREATE UNIQUE INDEX usuarios_email_uk ON usuarios (lower(email));

-- Regra de negócio: o CPF identifica a pessoa e não pode ser alterado.
CREATE FUNCTION impedir_troca_cpf() RETURNS trigger AS $$
BEGIN
    IF NEW.cpf <> OLD.cpf THEN
        RAISE EXCEPTION 'O CPF não pode ser alterado' USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END $$ LANGUAGE plpgsql;

CREATE TRIGGER usuarios_cpf_imutavel
    BEFORE UPDATE OF cpf ON usuarios
    FOR EACH ROW EXECUTE FUNCTION impedir_troca_cpf();

-- ---------------------------------------------------------------------
-- CATEGORIAS
-- ---------------------------------------------------------------------
CREATE TABLE categorias (
    id        SMALLSERIAL PRIMARY KEY,
    nome      VARCHAR(60) NOT NULL UNIQUE,
    descricao TEXT,
    ativa     BOOLEAN NOT NULL DEFAULT TRUE
);

-- ---------------------------------------------------------------------
-- OCORRÊNCIAS
-- ---------------------------------------------------------------------
CREATE TABLE ocorrencias (
    id                  BIGSERIAL PRIMARY KEY,
    usuario_id          BIGINT   NOT NULL REFERENCES usuarios (id),
    categoria_id        SMALLINT NOT NULL REFERENCES categorias (id),
    titulo              VARCHAR(120) NOT NULL,
    descricao           TEXT         NOT NULL,
    urgencia            VARCHAR(5)   NOT NULL DEFAULT 'MEDIA'
                        CHECK (urgencia IN ('BAIXA', 'MEDIA', 'ALTA')),
    status              VARCHAR(12)  NOT NULL DEFAULT 'ABERTA'
                        CHECK (status IN ('ABERTA', 'EM_ANALISE', 'EM_ANDAMENTO', 'RESOLVIDA', 'REJEITADA')),
    -- Ponto em WGS84 (o mesmo sistema do GPS). X = longitude, Y = latitude.
    localizacao         geometry(Point, 4326) NOT NULL,
    endereco_referencia VARCHAR(200),
    -- Contador mantido por trigger (ver tabela apoios). Evita COUNT(*) a cada listagem.
    apoios_total        INTEGER     NOT NULL DEFAULT 0 CHECK (apoios_total >= 0),
    criado_em           TIMESTAMPTZ NOT NULL DEFAULT now(),
    atualizado_em       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Índice espacial: acelera "ocorrências perto de mim" (ST_DWithin)
CREATE INDEX ocorrencias_localizacao_gix ON ocorrencias USING GIST (localizacao);
-- Versão em "geography" (distâncias em metros), usada pela busca por proximidade
CREATE INDEX ocorrencias_localizacao_geog_gix ON ocorrencias USING GIST ((localizacao::geography));
CREATE INDEX ocorrencias_usuario_ix      ON ocorrencias (usuario_id);
CREATE INDEX ocorrencias_status_ix       ON ocorrencias (status);
CREATE INDEX ocorrencias_criado_ix       ON ocorrencias (criado_em DESC);
-- Ordenação por prioridade: urgência e, em seguida, validação social
CREATE INDEX ocorrencias_prioridade_ix   ON ocorrencias (
    (CASE urgencia WHEN 'ALTA' THEN 3 WHEN 'MEDIA' THEN 2 ELSE 1 END) DESC,
    apoios_total DESC, criado_em DESC
);

-- ---------------------------------------------------------------------
-- APOIOS (validação social)
-- A chave primária composta impede que a mesma conta apoie
-- a mesma ocorrência mais de uma vez.
-- ---------------------------------------------------------------------
CREATE TABLE apoios (
    usuario_id    BIGINT NOT NULL REFERENCES usuarios (id),
    ocorrencia_id BIGINT NOT NULL REFERENCES ocorrencias (id) ON DELETE CASCADE,
    criado_em     TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (usuario_id, ocorrencia_id)
);
CREATE INDEX apoios_ocorrencia_ix ON apoios (ocorrencia_id);

-- Regras do apoio, garantidas no próprio banco:
--  1) ninguém apoia a própria ocorrência (manipulação do ranking);
--  2) só ocorrências ainda em aberto ou em curso recebem apoio.
CREATE FUNCTION validar_apoio() RETURNS trigger AS $$
DECLARE
    dono   BIGINT;
    st     VARCHAR(12);
BEGIN
    SELECT usuario_id, status INTO dono, st FROM ocorrencias WHERE id = NEW.ocorrencia_id;
    IF dono = NEW.usuario_id THEN
        RAISE EXCEPTION 'Não é possível apoiar a própria ocorrência' USING ERRCODE = 'check_violation';
    END IF;
    IF st IN ('RESOLVIDA', 'REJEITADA') THEN
        RAISE EXCEPTION 'Ocorrência encerrada não recebe apoios' USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END $$ LANGUAGE plpgsql;

CREATE TRIGGER apoios_validar
    BEFORE INSERT ON apoios
    FOR EACH ROW EXECUTE FUNCTION validar_apoio();

-- Mantém ocorrencias.apoios_total sincronizado
CREATE FUNCTION contar_apoios() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        UPDATE ocorrencias SET apoios_total = apoios_total + 1 WHERE id = NEW.ocorrencia_id;
    ELSE
        UPDATE ocorrencias SET apoios_total = apoios_total - 1 WHERE id = OLD.ocorrencia_id;
    END IF;
    RETURN NULL;
END $$ LANGUAGE plpgsql;

CREATE TRIGGER apoios_contador
    AFTER INSERT OR DELETE ON apoios
    FOR EACH ROW EXECUTE FUNCTION contar_apoios();

-- ---------------------------------------------------------------------
-- HISTÓRICO DE STATUS (auditoria, somente inserção)
-- ---------------------------------------------------------------------
CREATE TABLE historico_status (
    id              BIGSERIAL PRIMARY KEY,
    ocorrencia_id   BIGINT NOT NULL REFERENCES ocorrencias (id),
    status_anterior VARCHAR(12),
    status_novo     VARCHAR(12) NOT NULL,
    observacao      TEXT,
    autor_id        BIGINT NOT NULL REFERENCES usuarios (id),
    alterado_em     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX historico_ocorrencia_ix ON historico_status (ocorrencia_id, alterado_em);

-- O histórico não pode ser editado nem apagado: cada mudança vira uma nova linha.
CREATE FUNCTION historico_somente_insercao() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'O histórico de status não pode ser alterado' USING ERRCODE = 'check_violation';
END $$ LANGUAGE plpgsql;

CREATE TRIGGER historico_imutavel
    BEFORE UPDATE OR DELETE ON historico_status
    FOR EACH ROW EXECUTE FUNCTION historico_somente_insercao();
