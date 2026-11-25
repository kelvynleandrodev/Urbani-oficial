/* ==========================================================
   URBANI · app.js · Dashboard (JavaScript Vanilla, sem bibliotecas)
   Os dados vêm da API (api.js); é iniciado por auth.js após o login.
   ========================================================== */

/* Anúncios mockados (Prefeitura / negócios locais) */
const ANUNCIOS = [
  { titulo: "Cata-Treco agendado na sua região", texto: "Descarte móveis e entulho gratuitamente. Veja as datas do seu bairro.", link: "#", anunciante: "Prefeitura" },
  { titulo: "Padaria Pão Quente: 10% off", texto: "Mostre o app Urbani no balcão e ganhe desconto no café da manhã.", link: "#", anunciante: "Negócio local" }
];

/* ---------- 1. ESTADO ---------- */
let usuario = null;                 // usuário logado (definido em iniciarApp)
let ocorrencias = [];               // lista geral (Geral, Minhas e mapa)
const ROTULO = { ABERTA: "Aberta", EM_ANALISE: "Em análise", EM_ANDAMENTO: "Em andamento", RESOLVIDA: "Resolvida", REJEITADA: "Rejeitada" };
const URGENCIA = { BAIXA: "Baixa", MEDIA: "Média", ALTA: "Alta" };
/* Próximos status possíveis (só para montar o menu do gestor; quem decide é o servidor) */
const PROXIMOS = { ABERTA: ["EM_ANALISE", "EM_ANDAMENTO", "REJEITADA"], EM_ANALISE: ["EM_ANDAMENTO", "REJEITADA"], EM_ANDAMENTO: ["RESOLVIDA"] };

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

/* Escapa texto digitado pelo usuário antes de usar em innerHTML */
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const data = (iso) => new Date(iso).toLocaleDateString("pt-BR");
const ehGestor = () => usuario && ["GESTOR", "ADMIN"].includes(usuario.perfil);

/* ---------- 2. NAVEGAÇÃO POR ABAS (SPA) ---------- */
function abrirAba(nome) {
  $$(".panel").forEach((p) => p.classList.toggle("active", p.id === "tab-" + nome));
  $$(".nav-btn").forEach((b) => b.classList.toggle("active", b.dataset.tab === nome));
  window.scrollTo({ top: 0 });
  if (nome === "nova") iniciarMapaEscolha();
  if (mapaGeral) setTimeout(() => mapaGeral.invalidateSize(), 50);
}
$$(".nav-btn[data-tab]").forEach((b) => b.addEventListener("click", () => abrirAba(b.dataset.tab)));

/* ---------- 3. RENDERIZAÇÃO ---------- */
/* Card de ocorrência: título, autor, endereço, descrição, status e ações */
function cardHTML(o) {
  const proprio = o.usuario_id === usuario.id;
  const encerrada = ["RESOLVIDA", "REJEITADA"].includes(o.status);
  const gestao = ehGestor() && PROXIMOS[o.status] ? `
      <div class="gestao">
        <select data-novo-status aria-label="Novo status">${PROXIMOS[o.status].map((s) => `<option value="${s}">${ROTULO[s]}</option>`).join("")}</select>
        <button type="button" data-acao="status">Alterar status</button>
      </div>` : "";
  return `
  <article class="card" data-id="${o.id}" data-status="${o.status}">
    <span class="badge ${o.status}">${ROTULO[o.status]}</span>
    <h3>${esc(o.titulo)}</h3>
    <p class="meta"><b>${esc(o.autor_nome)}</b> · ${esc(o.endereco_referencia)}</p>
    <p class="desc">${esc(o.descricao)}</p>
    <div class="detalhes">
      Categoria: ${esc(o.categoria_nome)} · Urgência: ${URGENCIA[o.urgencia]}<br>Registrada em ${data(o.criado_em)}
      <ol class="historico" aria-label="Histórico de status"></ol>
      <div class="fotos-servico" aria-label="Fotos do serviço executado"></div>${gestao}
    </div>
    <div class="acoes">
      <button class="btn-apoiar ${o.apoiado_por_mim ? "ativo" : ""}" data-acao="apoiar"
        ${proprio || encerrada ? `disabled title="${proprio ? "Você não pode apoiar a própria ocorrência" : "Ocorrência encerrada"}"` : ""}>
        ${o.apoiado_por_mim ? "Apoiado" : "Apoiar"} (${o.apoios_total})</button>
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

/* Comunidade: filtros e ordenação são feitos pela API */
async function renderComunidade() {
  const el = $("#feed-comunidade");
  try {
    const r = await Api.ocorrencias({
      categoria_id: $("#flt-categoria").value, status: $("#flt-status").value,
      ordem: $("#flt-ordem").value, limite: 200,
    });
    renderStats("#stats-comunidade", r.itens);
    renderLista("#feed-comunidade", r.itens, true);
  } catch (err) {
    el.innerHTML = `<p class="vazio">${esc(err.message)}</p>`;
  }
}

/* ---------- Mapa real (Leaflet + OpenStreetMap) ---------- */
const COR_STATUS = { ABERTA: "#E53E3E", EM_ANALISE: "#D69E2E", EM_ANDAMENTO: "#D69E2E", RESOLVIDA: "#2F9E6B", REJEITADA: "#718096" };
const CENTRO_PADRAO = [-23.5614, -46.6559];
const TILES = "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png";
const ATRIB = '&copy; colaboradores do <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>';
let mapaGeral = null, camadaPins = null, enquadrouGeral = false;
let mapaEscolha = null, pinEscolha = null;

function renderMapa() {
  const el = $("#mapa");
  if (!window.L) { el.innerHTML = '<p class="sem-mapa">Mapa indisponível (sem acesso à biblioteca Leaflet). Verifique sua conexão.</p>'; return; }
  if (!mapaGeral) {
    mapaGeral = L.map(el, { scrollWheelZoom: false }).setView(CENTRO_PADRAO, 13);
    L.tileLayer(TILES, { maxZoom: 19, attribution: ATRIB }).addTo(mapaGeral);
    camadaPins = L.layerGroup().addTo(mapaGeral);
    mapaGeral.on("popupopen", (e) => {
      const b = e.popup.getElement().querySelector("[data-ver]");
      if (b) b.addEventListener("click", () => {
        mapaGeral.closePopup();
        abrirAba("comunidade");
        $$(".card.destaque").forEach((c) => c.classList.remove("destaque"));
        const alvo = $(`#feed-comunidade .card[data-id="${b.dataset.ver}"]`);
        if (alvo) { alvo.classList.add("destaque"); alvo.scrollIntoView({ behavior: "smooth", block: "center" }); }
      });
    });
  }
  camadaPins.clearLayers();
  const pts = ocorrencias.filter((o) => o.latitude != null && o.longitude != null);
  pts.forEach((o) => L.circleMarker([o.latitude, o.longitude], {
    radius: 9, fillColor: COR_STATUS[o.status] || "#718096", fillOpacity: 0.95, color: "#fff", weight: 2,
  }).bindPopup(`<b>${esc(o.titulo)}</b>${ROTULO[o.status] || o.status}<br><button type="button" data-ver="${o.id}">Ver na Comunidade</button>`)
    .addTo(camadaPins));
  if (!enquadrouGeral && pts.length) {
    mapaGeral.fitBounds(L.latLngBounds(pts.map((o) => [o.latitude, o.longitude])).pad(0.15), { maxZoom: 16 });
    enquadrouGeral = true;
  }
  mapaGeral.invalidateSize();
}

/* Mapa de escolha do local no formulário: um toque define latitude/longitude */
function marcarLocal(lat, lng) {
  $("#f-lat").value = lat.toFixed(6);
  $("#f-lng").value = lng.toFixed(6);
  if (!mapaEscolha) return;
  if (pinEscolha) pinEscolha.setLatLng([lat, lng]);
  else pinEscolha = L.circleMarker([lat, lng], { radius: 11, fillColor: "#FF5A00", fillOpacity: 0.95, color: "#fff", weight: 3 }).addTo(mapaEscolha);
  mapaEscolha.setView([lat, lng], Math.max(mapaEscolha.getZoom(), 16));
}
function iniciarMapaEscolha() {
  const el = $("#mapa-escolha");
  if (!window.L) { el.hidden = true; return; }
  if (!mapaEscolha) {
    mapaEscolha = L.map(el).setView(CENTRO_PADRAO, 13);
    L.tileLayer(TILES, { maxZoom: 19, attribution: ATRIB }).addTo(mapaEscolha);
    mapaEscolha.on("click", (e) => {
      marcarLocal(e.latlng.lat, e.latlng.lng);
      $("#local-aviso").textContent = "Local marcado no mapa. Toque em outro ponto para ajustar.";
    });
    const digitado = () => {
      const la = parseFloat($("#f-lat").value.replace(",", ".")), lo = parseFloat($("#f-lng").value.replace(",", "."));
      if (Number.isFinite(la) && Number.isFinite(lo) && Math.abs(la) <= 90 && Math.abs(lo) <= 180) marcarLocal(la, lo);
    };
    $("#f-lat").addEventListener("change", digitado);
    $("#f-lng").addEventListener("change", digitado);
  }
  setTimeout(() => mapaEscolha.invalidateSize(), 50);
}

/* Busca os dados na API e atualiza todas as telas */
async function recarregar() {
  try {
    ocorrencias = (await Api.ocorrencias({ ordem: "recentes", limite: 200 })).itens;
  } catch (err) {
    toast(err.message);
    return;
  }
  const minhas = ocorrencias.filter((o) => o.usuario_id === usuario.id);
  renderStats("#stats-geral", ocorrencias);
  renderLista("#feed-recentes", ocorrencias.slice(0, 3), false);
  renderStats("#stats-minhas", minhas);
  renderLista("#feed-minhas", minhas, false);
  renderMapa();
  await renderComunidade();
}

/* ---------- 4. INTERAÇÕES (delegação de eventos) ---------- */
function toast(msg) {
  const t = $("#toast"); t.textContent = msg; t.classList.add("show");
  clearTimeout(toast.id); toast.id = setTimeout(() => t.classList.remove("show"), 3000);
}

/* Carrega a linha do tempo de status dentro do card expandido */
async function carregarHistorico(card) {
  const lista = card.querySelector(".historico");
  try {
    const h = await Api.historico(card.dataset.id);
    lista.innerHTML = h.map((x) =>
      `<li><b>${ROTULO[x.status_novo]}</b> · ${data(x.alterado_em)} · ${esc(x.autor_nome)}${x.observacao ? ` · ${esc(x.observacao)}` : ""}</li>`).join("");
  } catch (err) {
    lista.innerHTML = `<li>${esc(err.message)}</li>`;
  }
  carregarFotosDoServico(card);
}

/* Fotos que a equipe de campo anexou à ordem de serviço (antes/depois) */
async function carregarFotosDoServico(card) {
  const area = card.querySelector(".fotos-servico");
  if (!area || area.dataset.carregado) return;
  area.dataset.carregado = "1";
  try {
    const fotos = await Api.fotos(card.dataset.id);
    for (const f of fotos) {
      const fig = document.createElement("figure");
      const img = document.createElement("img");
      img.alt = f.tipo === "ANTES" ? "Foto antes do serviço" : "Foto depois do serviço";
      img.src = await Api.fotoUrl(f.id);
      const leg = document.createElement("figcaption");
      leg.textContent = f.tipo === "ANTES" ? "Antes" : "Depois";
      fig.append(img, leg); area.append(fig);
    }
  } catch { /* sem fotos: a área fica vazia */ }
}

document.addEventListener("click", async (e) => {
  // Botões dos cards
  const btn = e.target.closest("[data-acao]");
  if (btn) {
    const card = btn.closest(".card"), id = Number(card.dataset.id);
    const acao = btn.dataset.acao;
    if (acao === "apoiar") {
      const o = [...ocorrencias].find((x) => x.id === id);
      btn.disabled = true;
      try {
        const jaApoiou = btn.classList.contains("ativo") || (o && o.apoiado_por_mim);
        await (jaApoiou ? Api.retirarApoio(id) : Api.apoiar(id));
        await recarregar();
      } catch (err) { toast(err.message); btn.disabled = false; }
    } else if (acao === "denunciar") {
      abrirDenuncia(id);
    } else if (acao === "status") {
      const novo = card.querySelector("[data-novo-status]").value;
      btn.disabled = true;
      try {
        await Api.alterarStatus(id, novo, `Alterado por ${usuario.nome}.`);
        toast(`Status alterado para ${ROTULO[novo]}.`);
        await recarregar();
      } catch (err) { toast(err.message); btn.disabled = false; }
    } else {
      card.classList.toggle("expandido");
      const aberto = card.classList.contains("expandido");
      btn.textContent = aberto ? "Ver menos" : "Ver mais";
      if (aberto) carregarHistorico(card);
    }
    return;
  }
});

["#flt-categoria", "#flt-status", "#flt-ordem"].forEach((s) => $(s).addEventListener("change", renderComunidade));

/* Localização: usa o GPS/rede do aparelho, com autorização do usuário */
$("#btn-localizar").addEventListener("click", () => {
  const aviso = $("#local-aviso");
  if (!navigator.geolocation) { aviso.textContent = "Seu navegador não informa a localização. Digite as coordenadas."; return; }
  aviso.textContent = "Obtendo localização…";
  navigator.geolocation.getCurrentPosition(
    (p) => {
      marcarLocal(p.coords.latitude, p.coords.longitude);
      aviso.textContent = `Localização obtida (precisão de ~${Math.round(p.coords.accuracy)} m).`;
    },
    () => { aviso.textContent = "Não foi possível obter a localização. Digite as coordenadas."; },
    { enableHighAccuracy: true, timeout: 10000 }
  );
});

/* Formulário: envia a ocorrência para a API (a validação final é do servidor) */
$("#form-nova").addEventListener("submit", async (e) => {
  e.preventDefault();
  const v = (id) => $(id).value.trim();
  const num = (id) => (v(id) === "" ? null : Number(v(id).replace(",", ".")));
  if (num("#f-lat") === null || num("#f-lng") === null) {
    $("#form-erro").textContent = "Informe a localização: use o botão ou digite latitude e longitude.";
    return;
  }
  const btn = e.target.querySelector("[type=submit]");
  btn.disabled = true;
  try {
    await Api.criarOcorrencia({
      categoria_id: Number($("#f-categoria").value), titulo: v("#f-titulo"), descricao: v("#f-descricao"),
      endereco_referencia: v("#f-endereco"), urgencia: $("#f-urgencia").value,
      latitude: num("#f-lat"), longitude: num("#f-lng"),
    });
    $("#form-erro").textContent = "";
    $("#local-aviso").textContent = "";
    e.target.reset();
    if (pinEscolha && mapaEscolha) { mapaEscolha.removeLayer(pinEscolha); pinEscolha = null; }
    toast("Ocorrência registrada!");
    await recarregar();
    abrirAba("minhas");
  } catch (err) {
    $("#form-erro").textContent = err.message;
  } finally {
    btn.disabled = false;
  }
});

/* ---------- 4b. DENÚNCIA (vai para a análise do gestor, aba Antifraude) ---------- */
const modalDenuncia = $("#modal-denuncia");
function abrirDenuncia(id) {
  $("#form-denuncia").reset(); $("#d-erro").textContent = "";
  modalDenuncia.dataset.id = id; modalDenuncia.showModal();
}
$("#d-cancelar").addEventListener("click", () => modalDenuncia.close());
$("#form-denuncia").addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    await Api.denunciar(Number(modalDenuncia.dataset.id), $("#d-motivo").value, $("#d-detalhe").value.trim() || null);
    modalDenuncia.close(); toast("Denúncia enviada para análise da prefeitura.");
  } catch (err) {
    $("#d-erro").textContent = err.message;    // já denunciou, ou é a própria ocorrência
  }
});

/* ---------- 5. PERFIL INCOMPLETO (alerta + modal) ---------- */
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
$("#form-perfil").addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    usuario = await Api.completarPerfil($("#p-cidade").value.trim(), $("#p-bairro").value.trim());
    atualizarAlertaPerfil(); modalPerfil.close(); toast("Perfil atualizado!");
  } catch (err) {
    $("#p-erro").textContent = err.message;
  }
});

/* ---------- 6. INICIALIZAÇÃO DO DASHBOARD (chamada por auth.js após o login) ---------- */
async function iniciarApp(u) {
  usuario = u;
  $("#nome-usuario").textContent = u.nome.split(" ")[0];
  $("#avatar-letra").textContent = u.nome[0];
  $("#ad-lateral").innerHTML = adHTML(ANUNCIOS[0]);
  $("#link-gestao").hidden = !ehGestor();      // gestor vendo a tela do cidadão: atalho de volta
  atualizarAlertaPerfil();
  abrirAba("geral");
  try {
    const opts = (await Api.categorias()).map((c) => `<option value="${c.id}">${esc(c.nome)}</option>`).join("");
    $("#f-categoria").innerHTML = opts;
    $("#flt-categoria").innerHTML = '<option value="">Todas as categorias</option>' + opts;
  } catch (err) { toast(err.message); }
  await recarregar();
}
