-- =====================================================================
-- 002_dados_demo.sql · Dados de demonstração (FICTÍCIOS)
-- Origem: ArquivoDoJSON da Sprint 0 + campos acrescentados no front-end.
-- Senha de todos os usuários: urbani123 (hash Argon2id gerado pela API).
-- Não use dados reais de pessoas neste arquivo.
-- =====================================================================

INSERT INTO usuarios (id, nome, cpf, email, senha_hash, data_nascimento, cidade, bairro, perfil, criado_em) VALUES
 (1, 'Mariana Souza',  '12345678909', 'mariana.souza@exemplo.com',                '$argon2id$v=19$m=65536,t=3,p=4$U2Lzff6opMy2oREeRAANIA$3c8Gba8k/4HSdVH0SMA23asMUg+h0iX3Yo4tIACumO8', '1995-03-14', NULL,        NULL,         'CIDADAO', '2026-09-10T10:00:00-03:00'),
 (2, 'Carlos Lima',    '98765432100', 'carlos.lima@exemplo.com',                  '$argon2id$v=19$m=65536,t=3,p=4$bRayjAW221UiDuF3WGgcvg$9cTGWJqdmUIZTzPzLJ7OWYgDPY5AC0jnZUPZHWMPc1g', '1990-07-22', 'São Paulo', 'Consolação', 'CIDADAO', '2026-09-12T14:30:00-03:00'),
 (3, 'Fernanda Alves', '24681357928', 'fernanda.alves@prefeitura.exemplo.gov.br', '$argon2id$v=19$m=65536,t=3,p=4$mP84qZpm0wkbyV02bvNfuA$1R1nPLiu+XuNeAYmlRRAy+aq1LiVT4cgsJ2ONgosu94', '1988-11-05', 'São Paulo', 'Sé',         'GESTOR',  '2026-09-01T08:00:00-03:00'),
 (4, 'Admin Urbani',   '13579246828', 'admin@urbani.exemplo.com',                 '$argon2id$v=19$m=65536,t=3,p=4$7JWmav2yrh85+zrc3pAShg$M8FCnD7aXfeNSgzzoRZRl2CJ4EFsj8C8d9EasUwCffc', '1985-01-30', 'São Paulo', 'Centro',     'ADMIN',   '2026-09-01T08:00:00-03:00');
SELECT setval('usuarios_id_seq', (SELECT max(id) FROM usuarios));

INSERT INTO categorias (id, nome, descricao) VALUES
 (1, 'Buraco na via',      'Buracos, crateras e afundamentos no pavimento'),
 (2, 'Iluminação pública', 'Postes apagados, luminárias queimadas ou piscando'),
 (3, 'Poda de árvore',     'Árvores com galhos em risco, sobre fiação ou obstruindo a via');
SELECT setval('categorias_id_seq', (SELECT max(id) FROM categorias));

-- ST_MakePoint(longitude, latitude): a ordem é X, Y
INSERT INTO ocorrencias (id, usuario_id, categoria_id, titulo, descricao, urgencia, status, localizacao, endereco_referencia, criado_em, atualizado_em) VALUES
 (1, 1, 1, 'Buraco profundo na faixa da direita', 'Buraco de aproximadamente 40 cm de diâmetro que já causou desvio brusco de veículos.', 'ALTA',  'ABERTA',       ST_SetSRID(ST_MakePoint(-46.6559, -23.5614), 4326), 'Av. Paulista, próximo ao nº 1000',   '2026-10-02T09:15:00-03:00', '2026-10-02T09:15:00-03:00'),
 (2, 2, 2, 'Poste apagado há uma semana',         'Trecho inteiro da calçada sem iluminação à noite.',                                      'MEDIA', 'EM_ANALISE',   ST_SetSRID(ST_MakePoint(-46.6388, -23.5489), 4326), 'Rua Augusta, altura do nº 500',      '2026-10-03T19:40:00-03:00', '2026-10-04T08:20:00-03:00'),
 (3, 1, 3, 'Galho ameaçando a fiação',            'Galho grosso encostando nos fios de energia, com risco de queda.',                       'ALTA',  'EM_ANDAMENTO', ST_SetSRID(ST_MakePoint(-46.6417, -23.5703), 4326), 'Rua Vergueiro, em frente ao nº 800', '2026-10-04T07:50:00-03:00', '2026-10-07T10:10:00-03:00'),
 (4, 2, 1, 'Cratera após chuva forte',            'Asfalto cedeu após a chuva e abriu uma cratera na pista.',                               'ALTA',  'RESOLVIDA',    ST_SetSRID(ST_MakePoint(-46.6395, -23.5329), 4326), 'Rua da Consolação, nº 1200',         '2026-09-20T11:00:00-03:00', '2026-09-28T16:30:00-03:00'),
 (5, 1, 2, 'Luminária piscando na praça',         'Luminária central da praça pisca de forma intermitente desde o fim de semana.',          'BAIXA', 'RESOLVIDA',    ST_SetSRID(ST_MakePoint(-46.6576, -23.5874), 4326), 'Praça na Rua Pedroso Alvarenga',     '2026-09-25T20:10:00-03:00', '2026-10-01T15:00:00-03:00'),
 (6, 2, 3, 'Árvore com risco de queda',           'Árvore inclinada sobre a calçada após ventania.',                                        'MEDIA', 'REJEITADA',    ST_SetSRID(ST_MakePoint(-46.6333, -23.5505), 4326), 'Largo São Francisco',                '2026-10-05T13:25:00-03:00', '2026-10-06T09:00:00-03:00');
SELECT setval('ocorrencias_id_seq', (SELECT max(id) FROM ocorrencias));

INSERT INTO historico_status (ocorrencia_id, status_anterior, status_novo, observacao, autor_id, alterado_em) VALUES
 (1, NULL,           'ABERTA',       'Ocorrência registrada pelo cidadão.', 1, '2026-10-02T09:15:00-03:00'),
 (2, NULL,           'ABERTA',       'Ocorrência registrada pelo cidadão.', 2, '2026-10-03T19:40:00-03:00'),
 (2, 'ABERTA',       'EM_ANALISE',   'Encaminhado à equipe de iluminação.', 3, '2026-10-04T08:20:00-03:00'),
 (3, NULL,           'ABERTA',       'Ocorrência registrada pelo cidadão.', 1, '2026-10-04T07:50:00-03:00'),
 (3, 'ABERTA',       'EM_ANALISE',   'Vistoria agendada.',                  3, '2026-10-05T09:00:00-03:00'),
 (3, 'EM_ANALISE',   'EM_ANDAMENTO', 'Equipe de poda designada.',           3, '2026-10-07T10:10:00-03:00'),
 (4, NULL,           'ABERTA',       'Ocorrência registrada pelo cidadão.', 2, '2026-09-20T11:00:00-03:00'),
 (4, 'ABERTA',       'EM_ANALISE',   'Avaliação do pavimento.',             3, '2026-09-21T09:30:00-03:00'),
 (4, 'EM_ANALISE',   'EM_ANDAMENTO', 'Equipe de recapeamento em campo.',    3, '2026-09-26T08:00:00-03:00'),
 (4, 'EM_ANDAMENTO', 'RESOLVIDA',    'Reparo concluído.',                   3, '2026-09-28T16:30:00-03:00'),
 (5, NULL,           'ABERTA',       'Ocorrência registrada pelo cidadão.', 1, '2026-09-25T20:10:00-03:00'),
 (5, 'ABERTA',       'EM_ANDAMENTO', 'Troca de luminária programada.',      3, '2026-09-29T10:00:00-03:00'),
 (5, 'EM_ANDAMENTO', 'RESOLVIDA',    'Luminária substituída.',              3, '2026-10-01T15:00:00-03:00'),
 (6, NULL,           'ABERTA',       'Ocorrência registrada pelo cidadão.', 2, '2026-10-05T13:25:00-03:00'),
 (6, 'ABERTA',       'REJEITADA',    'Vistoria não constatou risco; árvore avaliada como estável.', 3, '2026-10-06T09:00:00-03:00');

-- Apoios entre os cidadãos de demonstração (o trigger atualiza apoios_total)
INSERT INTO apoios (usuario_id, ocorrencia_id) VALUES (2, 1), (2, 3), (1, 2);
