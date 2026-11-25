/* ==========================================================
   api.js · Cliente da API do Urbani (substitui o antigo db.js)
   Todas as regras de negócio ficam no back-end; aqui só
   enviamos pedidos HTTP e devolvemos as respostas.
   ========================================================== */

/* Endereço da API:
   - publicado (Render): a API e o site estão no mesmo endereço → "/api";
   - desenvolvimento com Live Server (porta 5500): a API roda na porta 8000.
   Para apontar outro servidor, defina window.URBANI_API antes de carregar este arquivo. */
const API_URL = window.URBANI_API || (location.port === "5500" || location.protocol === "file:"
  ? `http://${location.hostname || "localhost"}:8000/api`
  : "/api");

const Api = (() => {
  const CHAVE = "urbani_token";          // sessionStorage: some ao fechar a aba
  let token = null;
  try { token = sessionStorage.getItem(CHAVE); } catch { /* navegador sem storage */ }

  function guardarToken(t) {
    token = t;
    try { t ? sessionStorage.setItem(CHAVE, t) : sessionStorage.removeItem(CHAVE); } catch { /* ignora */ }
  }

  /* Faz a requisição e transforma erros HTTP em exceções com a mensagem da API */
  async function req(metodo, caminho, corpo) {
    const opcoes = { method: metodo, headers: {} };
    if (token) opcoes.headers.Authorization = `Bearer ${token}`;
    if (corpo !== undefined) {
      opcoes.headers["Content-Type"] = "application/json";
      opcoes.body = JSON.stringify(corpo);
    }
    let r;
    try {
      r = await fetch(API_URL + caminho, opcoes);
    } catch {
      throw new Error("Não foi possível conectar ao servidor. Verifique se a API está rodando.");
    }
    if (r.status === 204) return null;
    const dados = await r.json().catch(() => ({}));
    if (!r.ok) {
      const erro = new Error(dados.detail || `Erro ${r.status}`);
      erro.status = r.status;
      // Token vencido ou inválido: avisa o app para voltar ao login
      if (r.status === 401 && token && typeof aoExpirarSessao === "function") aoExpirarSessao();
      throw erro;
    }
    return dados;
  }

  /* Baixa um arquivo protegido (foto) e devolve um endereço local para usar em <img> */
  async function baixar(caminho) {
    const r = await fetch(API_URL + caminho, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
    if (!r.ok) throw new Error(`Erro ${r.status}`);
    return URL.createObjectURL(await r.blob());
  }

  const qs = (p) => {
    const s = new URLSearchParams(Object.entries(p).filter(([, v]) => v !== "" && v != null));
    return s.toString() ? "?" + s : "";
  };

  return {
    temSessao: () => !!token,
    sair: () => guardarToken(null),

    // Usuários
    cadastrar: (dados) => req("POST", "/cadastro", dados),
    async entrar(identificador, senha) {
      const r = await req("POST", "/login", { identificador, senha });
      guardarToken(r.token);
      return r.usuario;
    },
    eu: () => req("GET", "/usuarios/me"),
    completarPerfil: (cidade, bairro) => req("PATCH", "/usuarios/me", { cidade, bairro }),

    // Categorias e ocorrências
    categorias: () => req("GET", "/categorias"),
    ocorrencias: (filtros = {}) => req("GET", "/ocorrencias" + qs(filtros)),
    criarOcorrencia: (dados) => req("POST", "/ocorrencias", dados),
    alterarStatus: (id, status, observacao) => req("PATCH", `/ocorrencias/${id}`, { status, observacao }),
    historico: (id) => req("GET", `/ocorrencias/${id}/historico`),
    apoiar: (id) => req("POST", `/ocorrencias/${id}/apoios`),
    retirarApoio: (id) => req("DELETE", `/ocorrencias/${id}/apoios`),
    denunciar: (id, motivo, detalhe) => req("POST", `/ocorrencias/${id}/denuncias`, { motivo, detalhe }),
    fotos: (id) => req("GET", `/ocorrencias/${id}/fotos`),
    fotoUrl: (fotoId) => baixar(`/fotos/${fotoId}`),

    // Versão dos dados: muda a cada escrita. Usada para atualizar as telas "ao vivo"
    pulso: () => req("GET", "/pulso"),

    // Gestor (gestor.html)
    gestao: {
      fila: (filtros = {}) => req("GET", "/gestao/fila" + qs(filtros)),
      ficha: (id) => req("GET", `/gestao/ocorrencias/${id}`),
      painel: (dias) => req("GET", "/gestao/painel" + qs({ dias })),
      mapa: () => req("GET", "/gestao/mapa"),
      fraude: () => req("GET", "/gestao/fraude"),
      reclassificar: (id, urgencia, motivo) => req("PATCH", `/gestao/ocorrencias/${id}/urgencia`, { urgencia, motivo }),
      unificar: (id, principal_id) => req("POST", `/gestao/ocorrencias/${id}/duplicata`, { principal_id }),
      invalidarApoios: (id, motivo) => req("POST", `/gestao/ocorrencias/${id}/apoios/invalidar-suspeitos`, { motivo }),
      analisarDenuncias: (id, procedente) => req("POST", `/gestao/ocorrencias/${id}/denuncias/analisar`, { procedente }),
      despachar: (id, dados) => req("POST", `/gestao/ocorrencias/${id}/ordens`, dados),
      cancelarOS: (osId, motivo) => req("POST", `/gestao/ordens/${osId}/cancelar`, { motivo }),
      equipes: () => req("GET", "/gestao/equipes"),
      criarEquipe: (nome, categoria_id) => req("POST", "/gestao/equipes", { nome, categoria_id }),
      incluirMembro: (equipeId, usuario_id) => req("POST", `/gestao/equipes/${equipeId}/membros`, { usuario_id }),
      removerMembro: (equipeId, usuarioId) => req("DELETE", `/gestao/equipes/${equipeId}/membros/${usuarioId}`),
      usuarios: (perfil) => req("GET", "/gestao/usuarios" + qs({ perfil })),
      criarServidor: (dados) => req("POST", "/gestao/usuarios", dados),
      situacaoConta: (id, ativo, motivo) => req("PATCH", `/gestao/usuarios/${id}`, { ativo, motivo }),
    },

    // Equipe de campo (campo.html)
    campo: {
      ordens: (filtros = {}) => req("GET", "/campo/ordens" + qs(filtros)),
      ordem: (id) => req("GET", `/campo/ordens/${id}`),
      iniciar: (id) => req("POST", `/campo/ordens/${id}/iniciar`),
      concluir: (id, dados) => req("POST", `/campo/ordens/${id}/concluir`, dados),
      devolver: (id, motivo) => req("POST", `/campo/ordens/${id}/devolver`, { motivo }),
      anexarFoto: (id, tipo, imagem) => req("POST", `/campo/ordens/${id}/fotos`, { tipo, imagem }),
    },
  };
})();
