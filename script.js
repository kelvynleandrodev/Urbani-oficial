/* ==========================================================
   URBANI · script.js (JavaScript Vanilla, sem bibliotecas)
   ========================================================== */

/* ---------- 1. BASE DE DADOS MOCKADA ----------
   Espelha o ArquivoDoJSON do Sprint 0 (usuarios, categorias, ocorrencias).
   Fica embutida aqui para funcionar abrindo o index.html direto (file://).
   Quando o back-end existir, troque lerBase() por um fetch('/api/...'). */
const BASE = {
  usuarios: [
    { id: 1, nome: "Mariana Souza", perfil: "CIDADAO" },
    { id: 2, nome: "Carlos Lima", perfil: "CIDADAO" },
    { id: 3, nome: "Fernanda Alves", perfil: "GESTOR" }
  ],
  categorias: [
    { id: 1, nome: "Buraco na via" },
    { id: 2, nome: "Iluminação pública" },
    { id: 3, nome: "Poda de árvore" }
  ],
  ocorrencias: [
    { id: 1, usuario_id: 1, categoria_id: 1, titulo: "Buraco profundo na faixa da direita",
      descricao: "Buraco de aproximadamente 40 cm de diâmetro que já causou desvio brusco de veículos.",
      status: "ABERTA", localizacao: { latitude: -23.5614, longitude: -46.6559 },
      endereco_referencia: "Av. Paulista, próximo ao nº 1000", criado_em: "2026-10-02T09:15:00-03:00" },
    { id: 2, usuario_id: 2, categoria_id: 2, titulo: "Poste apagado há uma semana",
      descricao: "Trecho inteiro da calçada sem iluminação à noite.",
      status: "EM_ANALISE", localizacao: { latitude: -23.5489, longitude: -46.6388 },
      endereco_referencia: "Rua Augusta, altura do nº 500", criado_em: "2026-10-03T19:40:00-03:00" },
    { id: 3, usuario_id: 1, categoria_id: 3, titulo: "Galho ameaçando a fiação",
      descricao: "Galho grosso encostando nos fios de energia, com risco de queda.",
      status: "EM_ANDAMENTO", localizacao: { latitude: -23.5703, longitude: -46.6417 },
      endereco_referencia: "Rua Vergueiro, em frente ao nº 800", criado_em: "2026-10-04T07:50:00-03:00" },
    { id: 4, usuario_id: 2, categoria_id: 1, titulo: "Cratera após chuva forte",
      descricao: "Asfalto cedeu após a chuva e abriu uma cratera na pista.",
      status: "RESOLVIDA", localizacao: { latitude: -23.5329, longitude: -46.6395 },
      endereco_referencia: "Rua da Consolação, nº 1200", criado_em: "2026-09-20T11:00:00-03:00" },
    { id: 5, usuario_id: 1, categoria_id: 2, titulo: "Luminária piscando na praça",
      descricao: "Luminária central da praça pisca de forma intermitente desde o fim de semana.",
      status: "RESOLVIDA", localizacao: { latitude: -23.5874, longitude: -46.6576 },
      endereco_referencia: "Praça na Rua Pedroso Alvarenga", criado_em: "2026-09-25T20:10:00-03:00" },
    { id: 6, usuario_id: 2, categoria_id: 3, titulo: "Árvore com risco de queda",
      descricao: "Árvore inclinada sobre a calçada após ventania.",
      status: "REJEITADA", localizacao: { latitude: -23.5505, longitude: -46.6333 },
      endereco_referencia: "Largo São Francisco", criado_em: "2026-10-05T13:25:00-03:00" }
  ]
};

/* Anúncios mockados (Prefeitura / negócios locais) */
const ANUNCIOS = [
  { titulo: "Cata-Treco agendado na sua região", texto: "Descarte móveis e entulho gratuitamente. Veja as datas do seu bairro.", link: "#", anunciante: "Prefeitura" },
  { titulo: "Padaria Pão Quente: 10% off", texto: "Mostre o app Urbani no balcão e ganhe desconto no café da manhã.", link: "#", anunciante: "Negócio local" }
];

/* ---------- 2. ESTADO ---------- */
const USUARIO_ATUAL = 1;                         // simula o cidadão logado (Mariana)
const ROTULO = { ABERTA: "Aberta", EM_ANALISE: "Em análise", EM_ANDAMENTO: "Em andamento", RESOLVIDA: "Resolvida", REJEITADA: "Rejeitada" };
let ocorrencias = [];
let apoios = { 1: 12, 2: 7, 3: 5, 4: 21, 5: 9, 6: 1 };  // contagem de apoios (mock)
const meusApoios = new Set();                    // ids que o usuário apoiou

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

/* Escapa texto digitado pelo usuário antes de usar em innerHTML */
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const autor = (id) => (BASE.usuarios.find((u) => u.id === id) || {}).nome || "Anônimo";
const categoria = (id) => (BASE.categorias.find((c) => c.id === id) || {}).nome || "Outros";
const data = (iso) => new Date(iso).toLocaleDateString("pt-BR");

/* Simula a leitura assíncrona da base (troque por fetch no futuro) */
function lerBase() {
  return new Promise((ok) => setTimeout(() => ok(BASE), 150));
}

/* ---------- 3. NAVEGAÇÃO POR ABAS (SPA) ---------- */
function abrirAba(nome) {
  $$(".panel").forEach((p) => p.classList.toggle("active", p.id === "tab-" + nome));
  $$(".nav-btn").forEach((b) => b.classList.toggle("active", b.dataset.tab === nome));
  window.scrollTo({ top: 0 });
}
$$(".nav-btn").forEach((b) => b.addEventListener("click", () => abrirAba(b.dataset.tab)));

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
  const minhas = recentes.filter((o) => o.usuario_id === USUARIO_ATUAL);
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

/* Formulário: valida e cria uma ocorrência (em memória, sem back-end) */
$("#form-nova").addEventListener("submit", (e) => {
  e.preventDefault();
  const v = (id) => $(id).value.trim();
  if (!v("#f-titulo") || !v("#f-descricao") || !v("#f-endereco")) {
    $("#form-erro").textContent = "Preencha título, descrição e endereço para enviar.";
    return;
  }
  $("#form-erro").textContent = "";
  ocorrencias.push({
    id: Date.now(), usuario_id: USUARIO_ATUAL, categoria_id: Number($("#f-categoria").value),
    titulo: v("#f-titulo"), descricao: v("#f-descricao"), status: "ABERTA",
    // Sem geocodificação: posição aproximada perto do centro de SP (placeholder)
    localizacao: { latitude: -23.55 - Math.random() * 0.04, longitude: -46.64 - Math.random() * 0.02 },
    endereco_referencia: v("#f-endereco"), criado_em: new Date().toISOString()
  });
  e.target.reset();
  renderTudo();
  toast("Ocorrência registrada!");
  abrirAba("minhas");
});

/* ---------- 6. INICIALIZAÇÃO ---------- */
lerBase().then((base) => {
  ocorrencias = base.ocorrencias.map((o) => ({ ...o }));
  const user = base.usuarios.find((u) => u.id === USUARIO_ATUAL);
  $("#nome-usuario").textContent = user.nome.split(" ")[0];
  $("#avatar").textContent = user.nome[0];
  // Categorias nos selects (formulário e filtro)
  const opts = base.categorias.map((c) => `<option value="${c.id}">${esc(c.nome)}</option>`).join("");
  $("#f-categoria").innerHTML = opts;
  $("#flt-categoria").insertAdjacentHTML("beforeend", opts);
  // Anúncio fixo abaixo do mapa
  $("#ad-lateral").innerHTML = adHTML(ANUNCIOS[0]);
  renderTudo();
});
