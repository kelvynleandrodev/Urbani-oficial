-- =====================================================================
-- 003_gestao_campo.sql · Módulos do GESTOR e do COLABORADOR DE CAMPO
--
-- O que este arquivo acrescenta ao esquema do cidadão (001):
--   1. perfil COLABORADOR (equipe de campo);
--   2. parâmetros de sistema e prazos de atendimento (SLA) por urgência;
--   3. apoio VÁLIDO x apoio total (blindagem do ranking de prioridade);
--   4. denúncias de ocorrência;
--   5. equipes e seus membros;
--   6. ordens de serviço (OS), com prova de presença e fotos;
--   7. auditoria de decisões do gestor (somente inserção);
--   8. "pulso": contador de mudanças que alimenta o painel em tempo real.
--
-- É seguro rodar em um banco que já tem dados: só acrescenta colunas,
-- tabelas e preenche os valores novos a partir do histórico existente.
-- =====================================================================

-- ---------------------------------------------------------------------
-- 1. PERFIL COLABORADOR
-- ---------------------------------------------------------------------
ALTER TABLE usuarios ALTER COLUMN perfil TYPE VARCHAR(12);
ALTER TABLE usuarios DROP CONSTRAINT usuarios_perfil_check;
ALTER TABLE usuarios ADD CONSTRAINT usuarios_perfil_check
      CHECK (perfil IN ('CIDADAO', 'COLABORADOR', 'GESTOR', 'ADMIN'));
CREATE INDEX usuarios_perfil_ix ON usuarios (perfil) WHERE perfil <> 'CIDADAO';

-- ---------------------------------------------------------------------
-- 2. PARÂMETROS DE SISTEMA E SLA
-- Ficam em tabela (e não no código) para a prefeitura ajustar sem deploy.
-- ---------------------------------------------------------------------
CREATE TABLE parametros (
    chave     VARCHAR(40) PRIMARY KEY,
    valor     NUMERIC     NOT NULL,
    descricao TEXT        NOT NULL
);
INSERT INTO parametros (chave, valor, descricao) VALUES
 ('apoio_carencia_conta_h', 24,  'Horas de vida que uma conta precisa ter para o apoio dela contar no ranking'),
 ('apoio_limite_por_hora',  20,  'Máximo de apoios que uma conta pode dar por hora'),
 ('rajada_apoios_qtd',      5,   'Quantidade de apoios na janela que caracteriza uma rajada suspeita'),
 ('rajada_janela_min',      10,  'Tamanho da janela (minutos) usada para detectar rajadas de apoio'),
 ('duplicata_raio_m',       50,  'Raio (metros) para considerar duas ocorrências da mesma categoria como possível duplicata'),
 ('conclusao_raio_m',       200, 'Distância máxima (metros) entre o local da ocorrência e o ponto onde a OS foi concluída');

CREATE FUNCTION parametro(p_chave TEXT) RETURNS NUMERIC AS $$
    SELECT valor FROM parametros WHERE chave = p_chave
$$ LANGUAGE sql STABLE;

-- Prazos por urgência: primeira resposta da prefeitura e solução do problema
CREATE TABLE sla_urgencia (
    urgencia         VARCHAR(5) PRIMARY KEY CHECK (urgencia IN ('BAIXA', 'MEDIA', 'ALTA')),
    prazo_resposta_h INTEGER NOT NULL CHECK (prazo_resposta_h > 0),
    prazo_solucao_h  INTEGER NOT NULL CHECK (prazo_solucao_h >= prazo_resposta_h)
);
INSERT INTO sla_urgencia VALUES ('ALTA', 4, 48), ('MEDIA', 24, 120), ('BAIXA', 48, 240);

-- ---------------------------------------------------------------------
-- 3. OCORRÊNCIAS: colunas de gestão
-- ---------------------------------------------------------------------
ALTER TABLE ocorrencias
    ADD COLUMN apoios_validos       INTEGER NOT NULL DEFAULT 0 CHECK (apoios_validos >= 0),
    ADD COLUMN denuncias_pendentes  INTEGER NOT NULL DEFAULT 0 CHECK (denuncias_pendentes >= 0),
    ADD COLUMN primeira_resposta_em TIMESTAMPTZ,     -- quando saiu de ABERTA
    ADD COLUMN encerrado_em         TIMESTAMPTZ,     -- quando virou RESOLVIDA ou REJEITADA
    ADD COLUMN urgencia_revisada    BOOLEAN NOT NULL DEFAULT FALSE,   -- gestor conferiu a urgência
    ADD COLUMN duplicada_de         BIGINT REFERENCES ocorrencias (id),
    ADD CONSTRAINT ocorrencias_nao_duplica_a_si CHECK (duplicada_de IS NULL OR duplicada_de <> id);

-- Preenche as colunas novas com o que já existe no banco
UPDATE ocorrencias o SET
    apoios_validos = o.apoios_total,
    primeira_resposta_em = (SELECT min(h.alterado_em) FROM historico_status h
                             WHERE h.ocorrencia_id = o.id AND h.status_anterior = 'ABERTA'),
    encerrado_em = CASE WHEN o.status IN ('RESOLVIDA', 'REJEITADA') THEN
                        COALESCE((SELECT max(h.alterado_em) FROM historico_status h
                                   WHERE h.ocorrencia_id = o.id AND h.status_novo = o.status), o.atualizado_em) END;

-- Os tempos de resposta são gravados pelo banco na hora da mudança de status:
-- os indicadores do painel não dependem de varrer o histórico inteiro.
CREATE FUNCTION marcar_tempos_ocorrencia() RETURNS trigger AS $$
BEGIN
    IF NEW.status IS DISTINCT FROM OLD.status THEN
        IF OLD.status = 'ABERTA' AND NEW.primeira_resposta_em IS NULL THEN
            NEW.primeira_resposta_em := now();
        END IF;
        IF NEW.status IN ('RESOLVIDA', 'REJEITADA') THEN
            NEW.encerrado_em := now();
        END IF;
    END IF;
    RETURN NEW;
END $$ LANGUAGE plpgsql;

CREATE TRIGGER ocorrencias_tempos
    BEFORE UPDATE OF status ON ocorrencias
    FOR EACH ROW EXECUTE FUNCTION marcar_tempos_ocorrencia();

-- Fila de prioridade do gestor: índice PARCIAL só com o que está em aberto,
-- na mesma ordem do ORDER BY (urgência, apoios válidos, mais antiga primeiro).
-- A fila é lida direto do índice, sem ordenar a tabela inteira.
DROP INDEX ocorrencias_prioridade_ix;
CREATE INDEX ocorrencias_fila_ix ON ocorrencias (
    (CASE urgencia WHEN 'ALTA' THEN 3 WHEN 'MEDIA' THEN 2 ELSE 1 END) DESC,
    apoios_validos DESC, criado_em ASC
) WHERE status IN ('ABERTA', 'EM_ANALISE', 'EM_ANDAMENTO');
CREATE INDEX ocorrencias_encerrado_ix ON ocorrencias (encerrado_em) WHERE encerrado_em IS NOT NULL;
CREATE INDEX ocorrencias_categoria_ix ON ocorrencias (categoria_id);

-- ---------------------------------------------------------------------
-- 4. APOIO VÁLIDO (blindagem do ranking)
-- apoios_total  = o que o cidadão vê (todo apoio registrado);
-- apoios_validos = o que entra no ranking de prioridade.
-- ---------------------------------------------------------------------
ALTER TABLE apoios
    ADD COLUMN valido           BOOLEAN NOT NULL DEFAULT TRUE,
    ADD COLUMN motivo_invalidez VARCHAR(20)
        CHECK (motivo_invalidez IN ('CONTA_NOVA', 'CONTA_SUSPENSA', 'INVALIDADO_GESTOR')),
    ADD CONSTRAINT apoios_motivo_coerente CHECK (valido = (motivo_invalidez IS NULL));
CREATE INDEX apoios_usuario_tempo_ix ON apoios (usuario_id, criado_em DESC);
CREATE INDEX apoios_invalidos_ix     ON apoios (usuario_id) WHERE NOT valido;
CREATE INDEX apoios_criado_ix        ON apoios (criado_em);        -- janelas de tempo do antifraude

-- Regras automáticas na hora do apoio:
--  1) limite por hora: barra robôs que apoiam em massa;
--  2) carência: apoio de conta recém-criada fica registrado, mas só passa a
--     contar no ranking quando a conta completa a carência (ver revalidar_apoios).
CREATE FUNCTION antifraude_apoio() RETURNS trigger AS $$
DECLARE
    conta_criada TIMESTAMPTZ;
BEGIN
    IF (SELECT count(*) FROM apoios
         WHERE usuario_id = NEW.usuario_id AND criado_em > now() - interval '1 hour')
       >= parametro('apoio_limite_por_hora') THEN
        RAISE EXCEPTION 'Muitos apoios em pouco tempo. Tente novamente mais tarde'
              USING ERRCODE = 'check_violation';
    END IF;
    SELECT criado_em INTO conta_criada FROM usuarios WHERE id = NEW.usuario_id;
    IF NEW.valido AND conta_criada > NEW.criado_em - make_interval(hours => parametro('apoio_carencia_conta_h')::int) THEN
        NEW.valido := FALSE;
        NEW.motivo_invalidez := 'CONTA_NOVA';
    END IF;
    RETURN NEW;
END $$ LANGUAGE plpgsql;

CREATE TRIGGER apoios_antifraude
    BEFORE INSERT ON apoios
    FOR EACH ROW EXECUTE FUNCTION antifraude_apoio();

-- O contador passa a manter também apoios_validos
CREATE OR REPLACE FUNCTION contar_apoios() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        UPDATE ocorrencias SET apoios_total = apoios_total + 1,
                               apoios_validos = apoios_validos + NEW.valido::int
         WHERE id = NEW.ocorrencia_id;
    ELSIF TG_OP = 'DELETE' THEN
        UPDATE ocorrencias SET apoios_total = apoios_total - 1,
                               apoios_validos = apoios_validos - OLD.valido::int
         WHERE id = OLD.ocorrencia_id;
    ELSIF NEW.valido <> OLD.valido THEN
        UPDATE ocorrencias SET apoios_validos = apoios_validos + NEW.valido::int - OLD.valido::int
         WHERE id = NEW.ocorrencia_id;
    END IF;
    RETURN NULL;
END $$ LANGUAGE plpgsql;

DROP TRIGGER apoios_contador ON apoios;
CREATE TRIGGER apoios_contador
    AFTER INSERT OR DELETE OR UPDATE OF valido ON apoios
    FOR EACH ROW EXECUTE FUNCTION contar_apoios();

-- Libera os apoios de contas que já cumpriram a carência (chamada pela API
-- ao abrir a fila do gestor). Usa o índice parcial apoios_invalidos_ix.
CREATE FUNCTION revalidar_apoios() RETURNS INTEGER AS $$
DECLARE
    n INTEGER;
BEGIN
    UPDATE apoios a SET valido = TRUE, motivo_invalidez = NULL
      FROM usuarios u
     WHERE u.id = a.usuario_id AND NOT a.valido AND a.motivo_invalidez = 'CONTA_NOVA' AND u.ativo
       AND u.criado_em <= now() - make_interval(hours => parametro('apoio_carencia_conta_h')::int);
    GET DIAGNOSTICS n = ROW_COUNT;
    RETURN n;
END $$ LANGUAGE plpgsql;

-- Conta suspensa perde o peso no ranking na hora; reativada, recupera.
CREATE FUNCTION apoios_seguem_conta() RETURNS trigger AS $$
BEGIN
    IF OLD.ativo AND NOT NEW.ativo THEN
        UPDATE apoios SET valido = FALSE, motivo_invalidez = 'CONTA_SUSPENSA'
         WHERE usuario_id = NEW.id AND valido;
    ELSIF NEW.ativo AND NOT OLD.ativo THEN
        UPDATE apoios SET valido = TRUE, motivo_invalidez = NULL
         WHERE usuario_id = NEW.id AND motivo_invalidez = 'CONTA_SUSPENSA';
    END IF;
    RETURN NULL;
END $$ LANGUAGE plpgsql;

CREATE TRIGGER usuarios_apoios_seguem_conta
    AFTER UPDATE OF ativo ON usuarios
    FOR EACH ROW EXECUTE FUNCTION apoios_seguem_conta();

-- ---------------------------------------------------------------------
-- 5. DENÚNCIAS (o cidadão sinaliza; o gestor analisa)
-- ---------------------------------------------------------------------
CREATE TABLE denuncias (
    id            BIGSERIAL PRIMARY KEY,
    ocorrencia_id BIGINT NOT NULL REFERENCES ocorrencias (id) ON DELETE CASCADE,
    usuario_id    BIGINT NOT NULL REFERENCES usuarios (id),
    motivo        VARCHAR(12) NOT NULL
                  CHECK (motivo IN ('FALSA', 'DUPLICADA', 'OFENSIVA', 'LOCAL_ERRADO', 'OUTRO')),
    detalhe       VARCHAR(500),
    situacao      VARCHAR(12) NOT NULL DEFAULT 'PENDENTE'
                  CHECK (situacao IN ('PENDENTE', 'PROCEDENTE', 'IMPROCEDENTE')),
    analisada_por BIGINT REFERENCES usuarios (id),
    analisada_em  TIMESTAMPTZ,
    criado_em     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (ocorrencia_id, usuario_id)               -- uma denúncia por conta
);
CREATE INDEX denuncias_pendentes_ix ON denuncias (ocorrencia_id) WHERE situacao = 'PENDENTE';

CREATE FUNCTION validar_denuncia() RETURNS trigger AS $$
BEGIN
    IF (SELECT usuario_id FROM ocorrencias WHERE id = NEW.ocorrencia_id) = NEW.usuario_id THEN
        RAISE EXCEPTION 'Não é possível denunciar a própria ocorrência' USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END $$ LANGUAGE plpgsql;

CREATE TRIGGER denuncias_validar
    BEFORE INSERT ON denuncias
    FOR EACH ROW EXECUTE FUNCTION validar_denuncia();

CREATE FUNCTION contar_denuncias() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        UPDATE ocorrencias SET denuncias_pendentes = denuncias_pendentes + 1 WHERE id = NEW.ocorrencia_id;
    ELSIF OLD.situacao = 'PENDENTE' AND NEW.situacao <> 'PENDENTE' THEN
        UPDATE ocorrencias SET denuncias_pendentes = denuncias_pendentes - 1 WHERE id = NEW.ocorrencia_id;
    END IF;
    RETURN NULL;
END $$ LANGUAGE plpgsql;

CREATE TRIGGER denuncias_contador
    AFTER INSERT OR UPDATE OF situacao ON denuncias
    FOR EACH ROW EXECUTE FUNCTION contar_denuncias();

-- ---------------------------------------------------------------------
-- 6. EQUIPES DE CAMPO
-- ---------------------------------------------------------------------
CREATE TABLE equipes (
    id           SERIAL PRIMARY KEY,
    nome         VARCHAR(80) NOT NULL,
    categoria_id SMALLINT REFERENCES categorias (id),    -- especialidade (opcional)
    ativa        BOOLEAN NOT NULL DEFAULT TRUE,
    criado_em    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX equipes_nome_uk ON equipes (lower(nome));

-- Cada colaborador pertence a uma equipe por vez (a chave primária garante).
CREATE TABLE equipe_membros (
    usuario_id BIGINT  PRIMARY KEY REFERENCES usuarios (id),
    equipe_id  INTEGER NOT NULL REFERENCES equipes (id) ON DELETE CASCADE,
    desde      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX equipe_membros_equipe_ix ON equipe_membros (equipe_id);

CREATE FUNCTION validar_membro() RETURNS trigger AS $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM usuarios WHERE id = NEW.usuario_id AND perfil = 'COLABORADOR' AND ativo) THEN
        RAISE EXCEPTION 'Só colaboradores ativos podem entrar em uma equipe' USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END $$ LANGUAGE plpgsql;

CREATE TRIGGER equipe_membros_validar
    BEFORE INSERT OR UPDATE ON equipe_membros
    FOR EACH ROW EXECUTE FUNCTION validar_membro();

-- ---------------------------------------------------------------------
-- 7. ORDENS DE SERVIÇO
-- A OS liga a ocorrência do cidadão ao trabalho da equipe em campo.
-- ---------------------------------------------------------------------
CREATE TABLE ordens_servico (
    id                    BIGSERIAL PRIMARY KEY,
    ocorrencia_id         BIGINT  NOT NULL REFERENCES ocorrencias (id),
    equipe_id             INTEGER NOT NULL REFERENCES equipes (id),
    responsavel_id        BIGINT  REFERENCES usuarios (id),       -- quem iniciou em campo
    status                VARCHAR(12) NOT NULL DEFAULT 'ATRIBUIDA'
                          CHECK (status IN ('ATRIBUIDA', 'EM_EXECUCAO', 'CONCLUIDA', 'DEVOLVIDA', 'CANCELADA')),
    instrucoes            VARCHAR(1000),
    prazo_em              TIMESTAMPTZ NOT NULL,
    criado_por            BIGINT NOT NULL REFERENCES usuarios (id),
    criado_em             TIMESTAMPTZ NOT NULL DEFAULT now(),
    iniciada_em           TIMESTAMPTZ,
    encerrada_em          TIMESTAMPTZ,
    relatorio             VARCHAR(2000),                           -- o que foi feito
    motivo_encerramento   VARCHAR(500),                            -- devolução ou cancelamento
    -- Prova de presença: onde o colaborador estava ao concluir
    local_conclusao       geometry(Point, 4326),
    distancia_conclusao_m REAL,
    fora_do_local         BOOLEAN NOT NULL DEFAULT FALSE
);
-- Integridade: no máximo UMA OS ativa por ocorrência (vale mesmo com dois gestores clicando juntos)
CREATE UNIQUE INDEX os_ativa_uk ON ordens_servico (ocorrencia_id) WHERE status IN ('ATRIBUIDA', 'EM_EXECUCAO');
CREATE INDEX os_ocorrencia_ix ON ordens_servico (ocorrencia_id);
CREATE INDEX os_equipe_ix     ON ordens_servico (equipe_id, status);
CREATE INDEX os_encerrada_ix  ON ordens_servico (encerrada_em) WHERE encerrada_em IS NOT NULL;

-- Transições de status da OS garantidas no banco
CREATE FUNCTION validar_transicao_os() RETURNS trigger AS $$
BEGIN
    IF NEW.status = OLD.status THEN
        IF OLD.status IN ('CONCLUIDA', 'DEVOLVIDA', 'CANCELADA') THEN
            RAISE EXCEPTION 'Ordem de serviço encerrada não pode ser alterada' USING ERRCODE = 'check_violation';
        END IF;
        RETURN NEW;
    END IF;
    IF NOT ((OLD.status = 'ATRIBUIDA'   AND NEW.status IN ('EM_EXECUCAO', 'DEVOLVIDA', 'CANCELADA'))
         OR (OLD.status = 'EM_EXECUCAO' AND NEW.status IN ('CONCLUIDA', 'DEVOLVIDA', 'CANCELADA'))) THEN
        RAISE EXCEPTION 'Não é possível mudar a ordem de serviço de % para %', OLD.status, NEW.status
              USING ERRCODE = 'check_violation';
    END IF;
    IF NEW.status = 'EM_EXECUCAO' THEN
        NEW.iniciada_em := COALESCE(NEW.iniciada_em, now());
    ELSE
        NEW.encerrada_em := COALESCE(NEW.encerrada_em, now());
    END IF;
    RETURN NEW;
END $$ LANGUAGE plpgsql;

CREATE TRIGGER os_transicao
    BEFORE UPDATE ON ordens_servico
    FOR EACH ROW EXECUTE FUNCTION validar_transicao_os();

-- Ocorrência encerrada pelo gestor não deixa OS "órfã" em campo
CREATE FUNCTION encerrar_os_da_ocorrencia() RETURNS trigger AS $$
BEGIN
    IF NEW.status IN ('RESOLVIDA', 'REJEITADA') AND OLD.status NOT IN ('RESOLVIDA', 'REJEITADA') THEN
        UPDATE ordens_servico
           SET status = 'CANCELADA', motivo_encerramento = 'Ocorrência encerrada pela gestão.'
         WHERE ocorrencia_id = NEW.id AND status IN ('ATRIBUIDA', 'EM_EXECUCAO');
    END IF;
    RETURN NULL;
END $$ LANGUAGE plpgsql;

CREATE TRIGGER ocorrencias_encerra_os
    AFTER UPDATE OF status ON ocorrencias
    FOR EACH ROW EXECUTE FUNCTION encerrar_os_da_ocorrencia();

-- Fotos da execução (antes/depois). Ficam no banco para funcionar em
-- hospedagem sem disco persistente (Render gratuito); limite de 2 MB cada.
CREATE TABLE os_fotos (
    id        BIGSERIAL PRIMARY KEY,
    os_id     BIGINT NOT NULL REFERENCES ordens_servico (id) ON DELETE CASCADE,
    tipo      VARCHAR(6)  NOT NULL CHECK (tipo IN ('ANTES', 'DEPOIS')),
    mime      VARCHAR(20) NOT NULL CHECK (mime IN ('image/jpeg', 'image/png', 'image/webp')),
    conteudo  BYTEA NOT NULL CHECK (octet_length(conteudo) BETWEEN 1 AND 2097152),
    autor_id  BIGINT NOT NULL REFERENCES usuarios (id),
    criado_em TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX os_fotos_os_ix ON os_fotos (os_id);

-- ---------------------------------------------------------------------
-- 8. AUDITORIA DAS DECISÕES DE GESTÃO (somente inserção)
-- Tudo que mexe no ranking ou em contas fica registrado: quem, quando, por quê.
-- ---------------------------------------------------------------------
CREATE TABLE auditoria (
    id              BIGSERIAL PRIMARY KEY,
    ocorrencia_id   BIGINT REFERENCES ocorrencias (id),
    usuario_alvo_id BIGINT REFERENCES usuarios (id),
    acao            VARCHAR(30) NOT NULL,
    valor_anterior  TEXT,
    valor_novo      TEXT,
    motivo          VARCHAR(500),
    autor_id        BIGINT NOT NULL REFERENCES usuarios (id),
    criado_em       TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (ocorrencia_id IS NOT NULL OR usuario_alvo_id IS NOT NULL)
);
CREATE INDEX auditoria_ocorrencia_ix ON auditoria (ocorrencia_id, criado_em) WHERE ocorrencia_id IS NOT NULL;
CREATE INDEX auditoria_usuario_ix    ON auditoria (usuario_alvo_id, criado_em) WHERE usuario_alvo_id IS NOT NULL;

CREATE FUNCTION auditoria_somente_insercao() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'A auditoria não pode ser alterada' USING ERRCODE = 'check_violation';
END $$ LANGUAGE plpgsql;

CREATE TRIGGER auditoria_imutavel
    BEFORE UPDATE OR DELETE ON auditoria
    FOR EACH ROW EXECUTE FUNCTION auditoria_somente_insercao();

-- ---------------------------------------------------------------------
-- 9. PULSO (painel em tempo real)
-- Toda escrita relevante avança uma SEQUENCE. O painel pergunta "qual a
-- versão?" (leitura de um único número) e só refaz as consultas pesadas
-- quando ela muda. Sequence não bloqueia: várias escritas ao mesmo tempo
-- não esperam umas pelas outras, ao contrário de um UPDATE numa linha contadora.
-- ---------------------------------------------------------------------
CREATE SEQUENCE pulso_seq;

CREATE FUNCTION pulsar() RETURNS trigger AS $$
BEGIN
    PERFORM nextval('pulso_seq');
    RETURN NULL;
END $$ LANGUAGE plpgsql;

CREATE TRIGGER ocorrencias_pulso    AFTER INSERT OR UPDATE OR DELETE ON ocorrencias    FOR EACH STATEMENT EXECUTE FUNCTION pulsar();
CREATE TRIGGER apoios_pulso         AFTER INSERT OR UPDATE OR DELETE ON apoios         FOR EACH STATEMENT EXECUTE FUNCTION pulsar();
CREATE TRIGGER denuncias_pulso      AFTER INSERT OR UPDATE OR DELETE ON denuncias      FOR EACH STATEMENT EXECUTE FUNCTION pulsar();
CREATE TRIGGER ordens_servico_pulso AFTER INSERT OR UPDATE OR DELETE ON ordens_servico FOR EACH STATEMENT EXECUTE FUNCTION pulsar();
CREATE TRIGGER equipe_membros_pulso AFTER INSERT OR UPDATE OR DELETE ON equipe_membros FOR EACH STATEMENT EXECUTE FUNCTION pulsar();
