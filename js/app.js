/* ==========================================================
   URBANI · app.js · Dashboard (JavaScript Vanilla, sem bibliotecas)
   Depende de db.js; é iniciado por auth.js após o login.
   ========================================================== */

/* Anúncios mockados (Prefeitura / negócios locais) */
const ANUNCIOS = [
  { titulo: "Cata-Treco agendado na sua região", texto: "Descarte móveis e entulho gratuitamente. Veja as datas do seu bairro.", link: "#", anunciante: "Prefeitura" },
  { titulo: "Padaria Pão Quente: 10% off", texto: "Mostre o app Urbani no balcão e ganhe desconto no café da manhã.", link: "#", anunciante: "Negócio local" }
];

/* ---------- 2. ESTADO ---------- */
let usuario = null;                              // usuário logado (definido em iniciarApp)
const ROTULO = { ABERTA: "Aberta", EM_ANALISE: "Em análise", EM_ANDAMENTO: "Em andamento", RESOLVIDA: "Resolvida", REJEITADA: "Rejeitada" };
let ocorrencias = [];
let apoios = { 1: 12, 2: 7, 3: 5, 4: 21, 5: 9, 6: 1 };  // contagem de apoios (mock)
const meusApoios = new Set();                    // ids que o usuário apoiou

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

/* Escapa texto digitado pelo usuário antes de usar em innerHTML */
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const autor = (id) => (Banco.usuarios().find((u) => u.id === id) || {}).nome || "Anônimo";
const categoria = (id) => (Banco.base.categorias.find((c) => c.id === id) || {}).nome || "Outros";
const data = (iso) => new Date(iso).toLocaleDateString("pt-BR");

/* ---------- 3. NAVEGAÇÃO POR ABAS (SPA) ---------- */
function abrirAba(nome) {
  $$(".panel").forEach((p) => p.classList.toggle("active", p.id === "tab-" + nome));
  $$(".nav-btn").forEach((b) => b.classList.toggle("active", b.dataset.tab === nome));
  window.scrollTo({ top: 0 });
}
$$(".nav-btn[data-tab]").forEach((b) => b.addEventListener("click", () => abrirAba(b.dataset.tab)));

/* ---------- 4. RENDERIZAÇÃO ---------- */
/* Card de ocorrência: título, autor, endereço, descrição, status e ações */
function cardHTML(o) {
  const apoiou = meusApoios.has(o.id);
  return `
  <article class="card" data-id="${o.id}" data-status="${o.status}">
    <span class="badge ${o.status}">${ROTULO[o.status]}</span>
    <h3>${esc(o.titulo)}</h3>
    <p class="meta"><b>${esc(autor(o.usuario_id))}</b> · ${esc(o.endereco_referencia)}</p>
    <p class="desc">${esc(o.descricao)}</p>
    <div class="detalhes">Categoria: ${esc(categoria(o.categoria_id))}<br>Registrada em ${data(o.criado_em)}</div>
    <div class="acoes">
      <button class="btn-apoiar ${apoiou ? "ativo" : ""}" data-acao="apoiar">${apoiou ? "Apoiado" : "Apoiar"} (${apoios[o.id] || 0})</button>
      <button class="btn-denunciar" data-acao="denunciar">Denunciar</button>
      <button class="btn-mais" data-acao="mais">Ver mais</button>
    </div>
  </article>`;
}

/* Card de anúncio com tag discreta "Patrocinado" */
function adHTML(a) {
  return `
  <aside class="ad">
    <span class="ad-tag">Patrocinado · ${esc(a.anunciante)}</span>
    <h4>${esc(a.titulo)}</h4>
    <p>${esc(a.texto)}</p>
    <a href="${a.link}">Saiba mais</a>
  </aside>`;
}

/* Preenche um feed e intercala o anúncio depois do 2º card */
function renderLista(destino, lista, comAnuncio) {
  const el = $(destino);
  if (!lista.length) { el.innerHTML = '<p class="vazio">Nenhuma solicitação encontrada.</p>'; return; }
  el.innerHTML = lista.map((o, i) => cardHTML(o) + (comAnuncio && i === 1 ? adHTML(ANUNCIOS[1]) : "")).join("");
}

/* Indicadores (tiles) */
function renderStats(destino, lista) {
  const n = (...st) => lista.filter((o) => st.includes(o.status)).length;
  $(destino).innerHTML = [
    [lista.length, "Total"], [n("ABERTA"), "Abertas"],
    [n("EM_ANALISE", "EM_ANDAMENTO"), "Em curso"], [n("RESOLVIDA"), "Concluídas"]
  ].map(([v, t]) => `<div class="stat"><b>${v}</b><span>${t}</span></div>`).join("");
}

/* Comunidade: aplica filtros e ordenação */
function renderComunidade() {
  const cat = $("#flt-categoria").value, st = $("#flt-status").value, ord = $("#flt-ordem").value;
  let lista = ocorrencias.filter((o) => (!cat || o.categoria_id == cat) && (!st || o.status === st));
  lista.sort((a, b) => ord === "apoiadas" ? (apoios[b.id] || 0) - (apoios[a.id] || 0) : new Date(b.criado_em) - new Date(a.criado_em));
  renderLista("#feed-comunidade", lista, true);
}

/* Mapa: converte latitude/longitude em posição % dentro do placeholder */
function renderMapa() {
  const lats = ocorrencias.map((o) => o.localizacao.latitude), lngs = ocorrencias.map((o) => o.localizacao.longitude);
  const [minLa, maxLa, minLo, maxLo] = [Math.min(...lats), Math.max(...lats), Math.min(...lngs), Math.max(...lngs)];
  const pos = (v, min, max) => 10 + ((v - min) / ((max - min) || 1)) * 80;   // margem de 10%
  $("#mapa").innerHTML = ocorrencias.map((o) =>
    `<button class="pin ${o.status}" data-id="${o.id}" title="${esc(o.titulo)}" aria-label="${esc(o.titulo)}"
      style="left:${pos(o.localizacao.longitude, minLo, maxLo)}%;top:${100 - pos(o.localizacao.latitude, minLa, maxLa)}%"></button>`
  ).join("");
}

/* Atualiza todas as telas após qualquer mudança nos dados */
function renderTudo() {
  const recentes = [...ocorrencias].sort((a, b) => new Date(b.criado_em) - new Date(a.criado_em));
  const minhas = recentes.filter((o) => o.usuario_id === usuario.id);
  renderStats("#stats-geral", ocorrencias);
  renderLista("#feed-recentes", recentes.slice(0, 3), false);
  renderStats("#stats-comunidade", ocorrencias);
  renderComunidade();
  renderStats("#stats-minhas", minhas);
  renderLista("#feed-minhas", minhas, false);
  renderMapa();
}

/* ---------- 5. INTERAÇÕES (delegação de eventos) ---------- */
function toast(msg) {
  const t = $("#toast"); t.textContent = msg; t.classList.add("show");
  clearTimeout(toast.id); toast.id = setTimeout(() => t.classList.remove("show"), 2600);
}

document.addEventListener("click", (e) => {
  // Botões dos cards
  const btn = e.target.closest("[data-acao]");
  if (btn) {
    const card = btn.closest(".card"), id = Number(card.dataset.id);
    if (btn.dataset.acao === "apoiar") {
      meusApoios.has(id) ? (meusApoios.delete(id), apoios[id]--) : (meusApoios.add(id), apoios[id] = (apoios[id] || 0) + 1);
      renderTudo();
    } else if (btn.dataset.acao === "denunciar") {
      if (confirm("Denunciar esta solicitação como inadequada?")) toast("Denúncia enviada para análise da prefeitura.");
    } else {
      card.classList.toggle("expandido");
      btn.textContent = card.classList.contains("expandido") ? "Ver menos" : "Ver mais";
    }
    return;
  }
  // Marcadores do mapa: abre a Comunidade e destaca o card
  const pin = e.target.closest(".pin");
  if (pin) {
    abrirAba("comunidade");
    $$(".card.destaque").forEach((c) => c.classList.remove("destaque"));
    const alvo = $(`#feed-comunidade .card[data-id="${pin.dataset.id}"]`);
    if (alvo) { alvo.classList.add("destaque"); alvo.scrollIntoView({ behavior: "smooth", block: "center" }); }
  }
});

["#flt-categoria", "#flt-status", "#flt-ordem"].forEach((s) => $(s).addEventListener("change", renderComunidade));

/* Formulário: valida e cria uma ocorrência (salva no localStorage, sem back-end) */
$("#form-nova").addEventListener("submit", (e) => {
  e.preventDefault();
  const v = (id) => $(id).value.trim();
  if (!v("#f-titulo") || !v("#f-descricao") || !v("#f-endereco")) {
    $("#form-erro").textContent = "Preencha título, descrição e endereço para enviar.";
    return;
  }
  $("#form-erro").textContent = "";
  const nova = {
    id: Date.now(), usuario_id: usuario.id, categoria_id: Number($("#f-categoria").value),
    titulo: v("#f-titulo"), descricao: v("#f-descricao"), status: "ABERTA",
    // Sem geocodificação: posição aproximada perto do centro de SP (placeholder)
    localizacao: { latitude: -23.55 - Math.random() * 0.04, longitude: -46.64 - Math.random() * 0.02 },
    endereco_referencia: v("#f-endereco"), criado_em: new Date().toISOString()
  };
  ocorrencias.push(nova); Banco.salvarOcorrencia(nova);
  e.target.reset();
  renderTudo();
  toast("Ocorrência registrada!");
  abrirAba("minhas");
});

/* ---------- 6. PERFIL INCOMPLETO (alerta + modal) ---------- */
function atualizarAlertaPerfil() {
  const pendente = !usuario.cidade || !usuario.bairro;
  $("#alerta-perfil").hidden = !pendente;   // faixa na tela Geral
  $("#avatar-badge").hidden = !pendente;    // símbolo de alerta no avatar
}
const modalPerfil = $("#modal-perfil");
function abrirPerfil() {
  $("#p-cidade").value = usuario.cidade || ""; $("#p-bairro").value = usuario.bairro || "";
  $("#p-erro").textContent = ""; modalPerfil.showModal();
}
$("#avatar").addEventListener("click", abrirPerfil);
$("#btn-completar").addEventListener("click", abrirPerfil);
$("#p-cancelar").addEventListener("click", () => modalPerfil.close());
$("#form-perfil").addEventListener("submit", (e) => {
  e.preventDefault();
  const c = $("#p-cidade").value.trim(), b = $("#p-bairro").value.trim();
  if (!c || !b) { $("#p-erro").textContent = "Informe cidade e bairro."; return; }
  usuario.cidade = c; usuario.bairro = b;
  Banco.salvarUsuario(usuario);
  atualizarAlertaPerfil(); modalPerfil.close(); toast("Perfil atualizado!");
});

/* ---------- 7. INICIALIZAÇÃO DO DASHBOARD (chamada por auth.js após o login) ---------- */
function iniciarApp(u) {
  usuario = u;
  const base = Banco.base;
  ocorrencias = base.ocorrencias.concat(Banco.ocorrenciasLocais());
  meusApoios.clear();
  $("#nome-usuario").textContent = u.nome.split(" ")[0];
  $("#avatar-letra").textContent = u.nome[0];
  const opts = base.categorias.map((c) => `<option value="${c.id}">${esc(c.nome)}</option>`).join("");
  $("#f-categoria").innerHTML = opts;
  $("#flt-categoria").innerHTML = '<option value="">Todas as categorias</option>' + opts;
  $("#ad-lateral").innerHTML = adHTML(ANUNCIOS[0]);
  atualizarAlertaPerfil();
  abrirAba("geral");
  renderTudo();
}