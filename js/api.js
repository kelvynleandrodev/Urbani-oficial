/* ==========================================================
   api.js · Cliente da API do Urbani (substitui o antigo db.js)
   Todas as regras de negócio ficam no back-end; aqui só
   enviamos pedidos HTTP e devolvemos as respostas.
   ========================================================== */

/* Endereço da API. Por padrão, a mesma máquina que serve o front, na porta 8000.
   Para apontar outro servidor, defina window.URBANI_API antes de carregar este arquivo. */
const API_URL = window.URBANI_API || `http://${location.hostname || "localhost"}:8000/api`;

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
  };
})();
