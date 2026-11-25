-- =====================================================================
-- 004_dados_demo_gestao.sql · Dados de demonstração (FICTÍCIOS) da gestão
-- Colaboradores, equipes, ordens de serviço e um mês de ocorrências com
-- datas RELATIVAS a hoje, para o painel sempre ter movimento.
-- Senha de todos: urbani123. Não use dados reais de pessoas neste arquivo.
-- =====================================================================

-- ------------------------- Usuários -------------------------
INSERT INTO usuarios (nome, cpf, email, senha_hash, data_nascimento, cidade, bairro, perfil, criado_em)
SELECT v.nome, v.cpf, v.email,
       '$argon2id$v=19$m=65536,t=3,p=4$U2Lzff6opMy2oREeRAANIA$3c8Gba8k/4HSdVH0SMA23asMUg+h0iX3Yo4tIACumO8',
       v.nasc::date, 'São Paulo', v.bairro, v.perfil, now() - interval '70 days'
  FROM (VALUES
   ('Juliana Prado',   '70010020039', 'juliana.prado@exemplo.com',         '1992-04-18', 'Bela Vista',   'CIDADAO'),
   ('Rafael Tanaka',   '70010811915', 'rafael.tanaka@exemplo.com',         '1987-09-02', 'Liberdade',    'CIDADAO'),
   ('Beatriz Nunes',   '70011603852', 'beatriz.nunes@exemplo.com',         '1999-12-11', 'Pinheiros',    'CIDADAO'),
   ('Diego Martins',   '70012395773', 'diego.martins@exemplo.com',         '1994-06-27', 'Vila Mariana', 'CIDADAO'),
   ('João Pereira',    '70013187600', 'joao.pereira@urbani.exemplo.com',   '1984-02-09', 'Sé',           'COLABORADOR'),
   ('Marcos Silva',    '70013979540', 'marcos.silva@urbani.exemplo.com',   '1979-08-21', 'Sé',           'COLABORADOR'),
   ('Ana Ribeiro',     '70014771411', 'ana.ribeiro@urbani.exemplo.com',    '1991-10-03', 'Sé',           'COLABORADOR'),
   ('Luciana Costa',   '70015563359', 'luciana.costa@urbani.exemplo.com',  '1989-05-15', 'Sé',           'COLABORADOR')
  ) AS v (nome, cpf, email, nasc, bairro, perfil);

-- ------------------------- Equipes -------------------------
INSERT INTO equipes (nome, categoria_id)
SELECT v.nome, c.id FROM (VALUES
   ('Pavimentação',       'Buraco na via'),
   ('Iluminação Pública', 'Iluminação pública'),
   ('Arborização',        'Poda de árvore')) AS v (nome, categoria)
  JOIN categorias c ON c.nome = v.categoria;

INSERT INTO equipe_membros (usuario_id, equipe_id)
SELECT u.id, e.id FROM (VALUES
   ('joao.pereira@urbani.exemplo.com',  'Pavimentação'),
   ('marcos.silva@urbani.exemplo.com',  'Pavimentação'),
   ('ana.ribeiro@urbani.exemplo.com',   'Iluminação Pública'),
   ('luciana.costa@urbani.exemplo.com', 'Arborização')) AS v (email, equipe)
  JOIN usuarios u ON u.email = v.email
  JOIN equipes  e ON e.nome  = v.equipe;

-- ------------------------- Ocorrências do último mês -------------------------
-- dias = há quantos dias foi registrada; resp_h = horas até a 1ª resposta;
-- fim_h = horas até encerrar (RESOLVIDA / REJEITADA). ST_MakePoint(longitude, latitude).
CREATE TEMP TABLE demo_oc (
    autor TEXT, categoria TEXT, titulo TEXT, descricao TEXT, urgencia TEXT, status TEXT,
    lng FLOAT8, lat FLOAT8, endereco TEXT, dias NUMERIC, resp_h NUMERIC, fim_h NUMERIC
) ON COMMIT DROP;

INSERT INTO demo_oc VALUES
 ('juliana.prado@exemplo.com', 'Buraco na via',      'Buraco em frente ao ponto de ônibus',    'Ônibus desviam para a contramão para escapar do buraco.',            'ALTA',  'RESOLVIDA',    -46.6468, -23.5582, 'Rua Treze de Maio, 900',          27,   2,   30),
 ('rafael.tanaka@exemplo.com', 'Iluminação pública', 'Três postes apagados em sequência',      'Quarteirão inteiro no escuro, comércio fechando mais cedo.',         'ALTA',  'RESOLVIDA',    -46.6352, -23.5551, 'Rua Galvão Bueno, 200',           25,   3,   41),
 ('beatriz.nunes@exemplo.com', 'Poda de árvore',     'Galhos cobrindo o semáforo',             'Motoristas não enxergam o sinal vermelho na esquina.',               'ALTA',  'RESOLVIDA',    -46.6812, -23.5633, 'Rua dos Pinheiros, 450',          24,   5,   60),
 ('diego.martins@exemplo.com', 'Buraco na via',      'Asfalto afundando perto da escola',      'Afundamento cresce a cada chuva, bem na faixa de pedestres.',        'MEDIA', 'RESOLVIDA',    -46.6361, -23.5872, 'Rua Domingos de Morais, 1500',    22,  20,   96),
 ('juliana.prado@exemplo.com', 'Iluminação pública', 'Luminária acesa durante o dia',          'Poste aceso 24 horas há mais de uma semana.',                        'BAIXA', 'RESOLVIDA',    -46.6502, -23.5540, 'Rua Rui Barbosa, 300',            21,  40,  200),
 ('rafael.tanaka@exemplo.com', 'Poda de árvore',     'Árvore caída bloqueando a calçada',      'Tronco atravessado, pedestres andando pela rua.',                    'ALTA',  'RESOLVIDA',    -46.6331, -23.5607, 'Rua da Glória, 600',              19,   1,   22),
 ('beatriz.nunes@exemplo.com', 'Buraco na via',      'Tampa de bueiro solta',                  'Tampa faz barulho e ameaça soltar quando passa caminhão.',           'ALTA',  'RESOLVIDA',    -46.6843, -23.5669, 'Rua Teodoro Sampaio, 1200',       17,   6,   70),
 ('diego.martins@exemplo.com', 'Iluminação pública', 'Praça totalmente escura',                'Nenhuma luminária da praça funciona.',                               'MEDIA', 'RESOLVIDA',    -46.6389, -23.5841, 'Largo Ana Rosa',                  16,  18,  110),
 ('juliana.prado@exemplo.com', 'Buraco na via',      'Remendo que cedeu de novo',              'O reparo feito no mês passado já abriu outra vez.',                  'MEDIA', 'RESOLVIDA',    -46.6441, -23.5601, 'Rua Santo Antônio, 700',          14,  30,  140),
 ('rafael.tanaka@exemplo.com', 'Poda de árvore',     'Raízes levantando a calçada',            'Pedido de avaliação: idosos tropeçam no desnível.',                  'BAIXA', 'REJEITADA',    -46.6344, -23.5578, 'Rua Tomás Gonzaga, 80',           13,  26,   26),
 ('beatriz.nunes@exemplo.com', 'Iluminação pública', 'Poste piscando a noite toda',            'Luz intermitente atrapalha os moradores.',                           'BAIXA', 'RESOLVIDA',    -46.6790, -23.5611, 'Rua Cardeal Arcoverde, 900',      12,  50,  230),
 ('diego.martins@exemplo.com', 'Buraco na via',      'Cratera na ciclovia',                    'Ciclistas desviam para a pista dos carros.',                         'ALTA',  'RESOLVIDA',    -46.6402, -23.5890, 'Rua Vergueiro, 2700',             10,   3,   44),
 ('juliana.prado@exemplo.com', 'Poda de árvore',     'Galho pendurado sobre o parquinho',      'Galho quebrado preso apenas pela casca, acima dos brinquedos.',      'ALTA',  'EM_ANDAMENTO', -46.6479, -23.5559, 'Praça Dom Orione',                 3,   2, NULL),
 ('rafael.tanaka@exemplo.com', 'Buraco na via',      'Buraco na saída do metrô',               'Fluxo intenso de pedestres, já houve queda.',                        'ALTA',  'EM_ANDAMENTO', -46.6358, -23.5550, 'Praça da Liberdade',               1.4, 3, NULL),
 ('beatriz.nunes@exemplo.com', 'Iluminação pública', 'Passarela sem luz',                      'Passarela de pedestres totalmente escura à noite.',                  'ALTA',  'EM_ANALISE',   -46.6850, -23.5601, 'Av. Rebouças, altura do nº 3000', 2.5,  5, NULL),
 ('diego.martins@exemplo.com', 'Buraco na via',      'Vala aberta sem sinalização',            'Obra abandonada deixou vala aberta na faixa da esquerda.',           'ALTA',  'EM_ANALISE',   -46.6375, -23.5861, 'Rua Joaquim Távora, 500',          6,  10, NULL),
 ('juliana.prado@exemplo.com', 'Iluminação pública', 'Poste inclinado após batida',            'Poste torto depois de colisão, fios baixos.',                        'MEDIA', 'EM_ANALISE',   -46.6455, -23.5628, 'Rua Major Diogo, 350',             4,  22, NULL),
 ('rafael.tanaka@exemplo.com', 'Poda de árvore',     'Árvore seca com risco de queda',         'Árvore sem folhas há meses, tronco oco.',                            'MEDIA', 'ABERTA',       -46.6322, -23.5589, 'Rua Conselheiro Furtado, 900',     1.2, NULL, NULL),
 ('beatriz.nunes@exemplo.com', 'Buraco na via',      'Buraco na faixa de ônibus',              'Ônibus freiam bruscamente para desviar.',                            'ALTA',  'ABERTA',       -46.6828, -23.5650, 'Rua Henrique Schaumann, 400',      0.4, NULL, NULL),
 ('diego.martins@exemplo.com', 'Iluminação pública', 'Rua inteira sem iluminação',             'Apagão em todos os postes da rua desde ontem.',                      'ALTA',  'ABERTA',       -46.6411, -23.5822, 'Rua Humberto I, 200',              0.3, NULL, NULL),
 ('juliana.prado@exemplo.com', 'Poda de árvore',     'Galhos encostando na rede elétrica',     'Faíscas quando venta forte.',                                        'MEDIA', 'ABERTA',       -46.6493, -23.5571, 'Rua Conselheiro Ramalho, 600',     7,  NULL, NULL),
 ('rafael.tanaka@exemplo.com', 'Buraco na via',      'Paralelepípedos soltos',                 'Pedras soltas na travessia de pedestres.',                           'BAIXA', 'ABERTA',       -46.6340, -23.5563, 'Rua dos Estudantes, 100',          0.8, NULL, NULL),
 ('beatriz.nunes@exemplo.com', 'Iluminação pública', 'Guia rebaixada sem luz',                 'Pedido de reforço de iluminação em frente ao posto de saúde.',       'BAIXA', 'ABERTA',       -46.6801, -23.5622, 'Rua Mateus Grou, 250',             1.5, NULL, NULL),
 -- Duas pessoas registrando o mesmo problema (possível duplicata para o gestor unificar)
 ('diego.martins@exemplo.com', 'Buraco na via',      'Buraco enorme na faixa de ônibus',       'Mesmo buraco da Henrique Schaumann, está aumentando.',               'MEDIA', 'ABERTA',       -46.6830, -23.5651, 'Rua Henrique Schaumann, 410',      0.2, NULL, NULL);

DO $$
DECLARE
    r        RECORD;
    v_id     BIGINT;
    v_criado TIMESTAMPTZ;
    v_resp   TIMESTAMPTZ;
    v_fim    TIMESTAMPTZ;
    v_gestor BIGINT := (SELECT id FROM usuarios WHERE perfil IN ('GESTOR', 'ADMIN') ORDER BY (perfil = 'GESTOR') DESC, id LIMIT 1);
    v_equipe INTEGER;
    v_colab  BIGINT;
    v_os     BIGINT;
BEGIN
    FOR r IN SELECT d.*, u.id AS autor_id, c.id AS categoria_id
               FROM demo_oc d JOIN usuarios u ON u.email = d.autor JOIN categorias c ON c.nome = d.categoria
              ORDER BY d.dias DESC LOOP
        v_criado := now() - make_interval(secs => (r.dias * 86400)::float8);
        v_resp   := v_criado + make_interval(secs => (r.resp_h * 3600)::float8);
        v_fim    := v_criado + make_interval(secs => (r.fim_h  * 3600)::float8);
        SELECT id INTO v_equipe FROM equipes WHERE categoria_id = r.categoria_id LIMIT 1;
        SELECT usuario_id INTO v_colab FROM equipe_membros WHERE equipe_id = v_equipe ORDER BY usuario_id LIMIT 1;

        INSERT INTO ocorrencias (usuario_id, categoria_id, titulo, descricao, urgencia, status, localizacao,
                                 endereco_referencia, criado_em, atualizado_em, primeira_resposta_em, encerrado_em)
        VALUES (r.autor_id, r.categoria_id, r.titulo, r.descricao, r.urgencia, r.status,
                ST_SetSRID(ST_MakePoint(r.lng, r.lat), 4326), r.endereco,
                v_criado, COALESCE(v_fim, v_resp, v_criado), v_resp, v_fim)
        RETURNING id INTO v_id;

        INSERT INTO historico_status (ocorrencia_id, status_anterior, status_novo, observacao, autor_id, alterado_em)
        VALUES (v_id, NULL, 'ABERTA', 'Ocorrência registrada pelo cidadão.', r.autor_id, v_criado);

        IF r.status = 'REJEITADA' THEN
            INSERT INTO historico_status (ocorrencia_id, status_anterior, status_novo, observacao, autor_id, alterado_em)
            VALUES (v_id, 'ABERTA', 'REJEITADA', 'Vistoria não constatou risco; serviço fora do escopo da zeladoria.', v_gestor, v_fim);
        ELSIF r.status <> 'ABERTA' THEN
            INSERT INTO ordens_servico (ocorrencia_id, equipe_id, responsavel_id, status, instrucoes, prazo_em,
                                        criado_por, criado_em, iniciada_em, encerrada_em, relatorio,
                                        local_conclusao, distancia_conclusao_m)
            VALUES (v_id, v_equipe,
                    CASE WHEN r.status <> 'EM_ANALISE' THEN v_colab END,
                    CASE r.status WHEN 'EM_ANALISE' THEN 'ATRIBUIDA' WHEN 'EM_ANDAMENTO' THEN 'EM_EXECUCAO' ELSE 'CONCLUIDA' END,
                    'Verificar no local e executar o reparo. Sinalizar a área durante o serviço.',
                    v_criado + (SELECT make_interval(hours => prazo_solucao_h) FROM sla_urgencia WHERE urgencia = r.urgencia),
                    v_gestor, v_resp,
                    CASE WHEN r.status <> 'EM_ANALISE' THEN v_resp + interval '2 hours' END,
                    v_fim,
                    CASE WHEN r.status = 'RESOLVIDA' THEN 'Serviço executado e área liberada.' END,
                    CASE WHEN r.status = 'RESOLVIDA' THEN ST_SetSRID(ST_MakePoint(r.lng + 0.0001, r.lat), 4326) END,
                    CASE WHEN r.status = 'RESOLVIDA' THEN 10 END)
            RETURNING id INTO v_os;

            INSERT INTO historico_status (ocorrencia_id, status_anterior, status_novo, observacao, autor_id, alterado_em)
            VALUES (v_id, 'ABERTA', 'EM_ANALISE', format('Ordem de serviço nº %s atribuída à equipe.', v_os), v_gestor, v_resp);
            IF r.status IN ('EM_ANDAMENTO', 'RESOLVIDA') THEN
                INSERT INTO historico_status (ocorrencia_id, status_anterior, status_novo, observacao, autor_id, alterado_em)
                VALUES (v_id, 'EM_ANALISE', 'EM_ANDAMENTO', 'Equipe em campo.', v_colab, v_resp + interval '2 hours');
            END IF;
            IF r.status = 'RESOLVIDA' THEN
                INSERT INTO historico_status (ocorrencia_id, status_anterior, status_novo, observacao, autor_id, alterado_em)
                VALUES (v_id, 'EM_ANDAMENTO', 'RESOLVIDA', 'Serviço concluído: serviço executado e área liberada.', v_colab, v_fim);
            END IF;
        END IF;
    END LOOP;
END $$;

-- OS para as ocorrências de demonstração antigas que já estavam em curso
INSERT INTO ordens_servico (ocorrencia_id, equipe_id, responsavel_id, status, instrucoes, prazo_em, criado_por, criado_em, iniciada_em)
SELECT o.id, e.id,
       CASE WHEN o.status = 'EM_ANDAMENTO' THEN (SELECT usuario_id FROM equipe_membros m WHERE m.equipe_id = e.id LIMIT 1) END,
       CASE WHEN o.status = 'EM_ANDAMENTO' THEN 'EM_EXECUCAO' ELSE 'ATRIBUIDA' END,
       'Atender conforme vistoria agendada.', now() + interval '2 days',
       (SELECT id FROM usuarios WHERE perfil IN ('GESTOR', 'ADMIN') ORDER BY (perfil = 'GESTOR') DESC, id LIMIT 1),
       o.atualizado_em,
       CASE WHEN o.status = 'EM_ANDAMENTO' THEN o.atualizado_em END
  FROM ocorrencias o JOIN equipes e ON e.categoria_id = o.categoria_id
 WHERE o.id IN (2, 3) AND o.status IN ('EM_ANALISE', 'EM_ANDAMENTO')
   AND NOT EXISTS (SELECT 1 FROM ordens_servico x WHERE x.ocorrencia_id = o.id);

-- ------------------------- Apoios legítimos -------------------------
-- Cada cidadão de demonstração apoia ocorrências em aberto de outras pessoas,
-- algumas horas depois do registro.
INSERT INTO apoios (usuario_id, ocorrencia_id, criado_em)
SELECT u.id, o.id, o.criado_em + make_interval(mins => (40 + (u.id * 37 + o.id * 11) % 300)::int)
  FROM ocorrencias o
  JOIN usuarios u ON u.perfil = 'CIDADAO' AND u.id <> o.usuario_id
                 AND u.email IN ('juliana.prado@exemplo.com', 'rafael.tanaka@exemplo.com',
                                 'beatriz.nunes@exemplo.com', 'diego.martins@exemplo.com',
                                 'carlos.lima@exemplo.com', 'mariana.souza@exemplo.com')
 WHERE o.status IN ('ABERTA', 'EM_ANALISE', 'EM_ANDAMENTO')
   AND o.titulo IN (SELECT titulo FROM demo_oc)
   AND (u.id + o.id) % 3 <> 0
   AND o.criado_em + make_interval(mins => (40 + (u.id * 37 + o.id * 11) % 300)::int) < now()
ON CONFLICT DO NOTHING;

-- ------------------------- Cenário de fraude para a demonstração -------------------------
-- Seis contas criadas em sequência apoiam, em menos de 5 minutos, uma
-- ocorrência de urgência baixa para tentar empurrá-la ao topo do ranking.
-- O banco registra os apoios (apoios_total = 6), mas nenhum conta no
-- ranking (apoios_validos = 0), e o painel antifraude aponta a rajada.
INSERT INTO usuarios (nome, cpf, email, senha_hash, data_nascimento, perfil, criado_em)
SELECT 'Conta Recente ' || n,
       (ARRAY['70016355296','70017147123','70017939062','70018730981','70019522819','70020314736'])[n],
       'conta.recente' || n || '@exemplo.com',
       '$argon2id$v=19$m=65536,t=3,p=4$U2Lzff6opMy2oREeRAANIA$3c8Gba8k/4HSdVH0SMA23asMUg+h0iX3Yo4tIACumO8',
       '1990-01-01', 'CIDADAO', now() - interval '3 hours' + make_interval(mins => n)
  FROM generate_series(1, 6) AS n;

INSERT INTO apoios (usuario_id, ocorrencia_id, criado_em)
SELECT u.id, o.id, now() - interval '2 hours' + make_interval(secs => 40 * row_number() OVER (ORDER BY u.id))
  FROM usuarios u, ocorrencias o
 WHERE u.email LIKE 'conta.recente%@exemplo.com' AND o.titulo = 'Paralelepípedos soltos';

-- Denúncias de demonstração
INSERT INTO denuncias (ocorrencia_id, usuario_id, motivo, detalhe)
SELECT o.id, u.id, v.motivo, v.detalhe
  FROM (VALUES
   ('Paralelepípedos soltos',           'juliana.prado@exemplo.com', 'FALSA',     'Passei no local hoje e o calçamento está normal.'),
   ('Paralelepípedos soltos',           'diego.martins@exemplo.com', 'FALSA',     'Parece pedido combinado para furar a fila.'),
   ('Buraco enorme na faixa de ônibus', 'rafael.tanaka@exemplo.com', 'DUPLICADA', 'Já existe outra solicitação para o mesmo buraco.')
  ) AS v (titulo, email, motivo, detalhe)
  JOIN ocorrencias o ON o.titulo = v.titulo
  JOIN usuarios   u ON u.email  = v.email;
