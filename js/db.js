/* ==========================================================
   db.js · Banco provisório
   - Leitura: db.json (via fetch). Se o fetch falhar (ex.: abrindo o
     index.html direto, file://), usa DB_EMBUTIDO (db-embutido.js).
   - Escrita: um front-end não grava em arquivo; novos dados vão
     para o localStorage e são somados ao db.json na leitura.
   ========================================================== */
const Banco = (() => {
  const K_USERS = "urbani_usuarios_locais";   // usuários novos ou alterados
  const K_OCORR = "urbani_ocorrencias_locais";
  let base = null;
  const memoria = {};                         // espelho caso o localStorage esteja bloqueado

  const ler = (k) => { try { return JSON.parse(localStorage.getItem(k)) || []; } catch { return memoria[k] || []; } };
  const gravar = (k, v) => { memoria[k] = v; try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* segue em memória */ } };

  async function carregar() {
    try {
      const r = await fetch("db.json");
      if (!r.ok) throw new Error("db.json indisponível");
      base = await r.json();
    } catch { base = DB_EMBUTIDO; }
    return base;
  }

  /* db.json + locais (um usuário local com o mesmo id substitui o do JSON) */
  function usuarios() {
    const locais = ler(K_USERS);
    const mesclados = base.usuarios.map((u) => locais.find((l) => l.id === u.id) || u);
    return mesclados.concat(locais.filter((l) => !base.usuarios.some((u) => u.id === l.id)));
  }
  function salvarUsuario(u) { gravar(K_USERS, ler(K_USERS).filter((l) => l.id !== u.id).concat(u)); }

  const ocorrenciasLocais = () => ler(K_OCORR);
  const salvarOcorrencia = (o) => gravar(K_OCORR, ler(K_OCORR).concat(o));

  return { carregar, usuarios, salvarUsuario, ocorrenciasLocais, salvarOcorrencia, get base() { return base; } };
})();