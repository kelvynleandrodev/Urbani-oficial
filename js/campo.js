/* ==========================================================
   campo.js · App da equipe de campo
   Abas: A fazer · Mapa · Encerradas
   O colaborador vê as ordens de serviço (OS) da própria equipe,
   inicia, registra foto e conclui. Cada passo muda o status da
   ocorrência e aparece na linha do tempo do cidadão.
   Depende de: api.js, comum.js
   ========================================================== */

/* ---------- 1. ESTADO ---------- */
let usuario = null;
let ordens = [];              // OS ativas da equipe
let posicao = null;           // última posição conhecida do aparelho
let abaAtual = "fazer";
let concluindo = null;        // OS aberta no diálogo de conclusão

/* ---------- 2. ABAS ---------- */
function abrirAba(nome) {
  abaAtual = nome;
  $$(".panel").forEach((p) => p.classList.toggle("active", p.id === "tab-" + nome));
  $$(".abas-campo button").forEach((b) => b.classList.toggle("active", b.dataset.tab === nome));
  window.scrollTo({ top: 0 });
  if (nome === "mapa") desenharMapa();
  if (nome === "encerradas") carregarEncerradas();
}
$$(".abas-campo button").forEach((b) => b.addEventListener("click", () => abrirAba(b.dataset.tab)));
$("#btn-sair").addEventListener("click", () => { Api.sair(); location.replace("index.html"); });

/* ---------- 3. CARTÕES ---------- */
function osHTML(o) {
  const ativa = o.status === "ATRIBUIDA" || o.status === "EM_EXECUCAO";
  const rota = `https://www.google.com/maps/dir/?api=1&destination=${o.latitude},${o.longitude}`;
  return `
  <article class="os" data-id="${o.id}" data-status="${o.status}" data-urgencia="${o.urgencia}">
    <div class="chips">
      <span class="chip ${o.urgencia}">Urgência ${URGENCIA[o.urgencia].toLowerCase()}</span>
      ${ativa ? `<span class="chip ${o.atrasada ? "ATRASADA" : "NO_PRAZO"}">${prazo(o.prazo_em)}</span>` : `<span class="chip">${ROTULO_OS[o.status]}</span>`}
      ${o.status === "EM_EXECUCAO" ? '<span class="chip VENCENDO">Em execução</span>' : ""}
      <span class="numero">OS nº ${o.id}</span>
    </div>
    <h3>${esc(o.titulo)}</h3>
    <p class="meta">${esc(o.categoria_nome)} · ${esc(o.endereco_referencia)}${o.distancia_m != null ? ` · <b>${distancia(o.distancia_m)} de você</b>` : ""}</p>
    <p class="desc">${esc(o.descricao)}</p>
    ${o.instrucoes ? `<p class="instr"><b>Instruções do gestor:</b> ${esc(o.instrucoes)}</p>` : ""}
    ${o.responsavel_nome && ativa ? `<p class="meta">Com ${o.responsavel_id === usuario.id ? "você" : esc(o.responsavel_nome)} · ▲ ${o.apoios_validos} apoio(s) de moradores${o.fotos ? ` · ${o.fotos} foto(s)` : ""}</p>` : ""}
    ${o.relatorio ? `<p class="instr"><b>Relato:</b> ${esc(o.relatorio)}</p>` : ""}
    ${o.motivo_encerramento ? `<p class="instr"><b>Motivo:</b> ${esc(o.motivo_encerramento)}</p>` : ""}
    ${!ativa ? `<p class="meta">Encerrada em ${dataHora(o.encerrada_em)}</p>` : `
    <div class="os-acoes">
      <a href="${rota}" target="_blank" rel="noopener">Traçar rota</a>
      ${o.status === "ATRIBUIDA" ? '<button type="button" class="principal" data-acao="iniciar">Iniciar serviço</button>' : `
      <button type="button" data-acao="foto-antes">Foto do antes</button>
      <button type="button" class="principal" data-acao="concluir">Concluir</button>`}
      <button type="button" class="perigo" data-acao="devolver">Não consigo executar</button>
    </div>`}
  </article>`;
}

/* ---------- 4. CARREGAMENTO ---------- */
async function carregar() {
  try {
    const r = await Api.campo.ordens(posicao ? { latitude: posicao.latitude, longitude: posicao.longitude } : {});
    ordens = r.itens;
    $("#c-equipe").textContent = r.equipe ? `Equipe ${r.equipe.nome}` : "Sem equipe";
    const n = (f) => ordens.filter(f).length;
    $("#c-resumo").innerHTML = [
      [n((o) => o.status === "ATRIBUIDA"), "A iniciar"], [n((o) => o.status === "EM_EXECUCAO"), "Em execução"], [n((o) => o.atrasada), "Atrasadas"],
    ].map(([v, t]) => `<div class="stat"><b>${v}</b><span>${t}</span></div>`).join("");
    const c = $("#c-n"); c.textContent = ordens.length; c.hidden = !ordens.length;
    $("#lista-fazer").innerHTML = !r.equipe
      ? '<p class="vazio">Você ainda não está em uma equipe. Peça ao gestor para incluir você.</p>'
      : ordens.length ? ordens.map(osHTML).join("") : '<p class="vazio">Nenhuma ordem de serviço para a sua equipe agora.</p>';
    if (abaAtual === "mapa") desenharMapa();
  } catch (err) { toast(err.message); }
}

async function carregarEncerradas() {
  try {
    const r = await Api.campo.ordens({ situacao: "encerradas" });
    $("#lista-encerradas").innerHTML = r.itens.length ? r.itens.map(osHTML).join("") : '<p class="vazio">Nenhuma ordem de serviço encerrada ainda.</p>';
  } catch (err) { $("#lista-encerradas").innerHTML = `<p class="vazio">${esc(err.message)}</p>`; }
}

/* Posição do aparelho: serve para ordenar por distância e como prova de presença na conclusão */
async function atualizarPosicao() {
  $("#c-gps").textContent = "Obtendo a sua localização…";
  posicao = await ondeEstou();
  $("#c-gps").textContent = posicao
    ? `Localização ativa (precisão de ~${Math.round(posicao.precisao)} m).`
    : "Sem localização: as distâncias não aparecem e a conclusão irá para conferência do gestor.";
  if (posicao) carregar();
}

/* ---------- 5. MAPA ---------- */
let mapa = null, marcadores = null, eu = null;
function desenharMapa() {
  if (!window.L) { $("#mapa-campo").innerHTML = '<p class="sem-mapa">Mapa indisponível sem internet. Use o botão “Traçar rota” na lista.</p>'; return; }
  if (!mapa) {
    mapa = L.map("mapa-campo").setView([-23.5614, -46.6559], 13);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19, attribution: '&copy; colaboradores do <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    }).addTo(mapa);
    marcadores = L.layerGroup().addTo(mapa);
    mapa.on("popupopen", (e) => {
      const btn = e.popup.getElement().querySelector("[data-ver]");
      if (btn) btn.addEventListener("click", () => {
        abrirAba("fazer");
        const alvo = $(`.os[data-id="${btn.dataset.ver}"]`);
        if (alvo) { $$(".os.destaque").forEach((x) => x.classList.remove("destaque")); alvo.classList.add("destaque"); alvo.scrollIntoView({ behavior: "smooth", block: "center" }); }
      });
    });
  }
  mapa.invalidateSize();
  marcadores.clearLayers();
  const cor = { ALTA: "#E53E3E", MEDIA: "#D69E2E", BAIXA: "#718096" };
  const pontos = ordens.map((o) => {
    L.circleMarker([o.latitude, o.longitude], { radius: 11, fillColor: cor[o.urgencia], fillOpacity: 0.95, color: o.status === "EM_EXECUCAO" ? "#FF5A00" : "#fff", weight: 3 })
      .bindPopup(`<b>${esc(o.titulo)}</b>${esc(o.endereco_referencia)}<br>${prazo(o.prazo_em)}<br><button type="button" data-ver="${o.id}">Ver ordem de serviço</button>`)
      .addTo(marcadores);
    return [o.latitude, o.longitude];
  });
  if (posicao) {
    eu = L.circleMarker([posicao.latitude, posicao.longitude], { radius: 7, fillColor: "#1A1C24", fillOpacity: 1, color: "#fff", weight: 3 }).bindTooltip("Você").addTo(marcadores);
    pontos.push([posicao.latitude, posicao.longitude]);
  }
  if (pontos.length) mapa.fitBounds(L.latLngBounds(pontos).pad(0.2), { maxZoom: 16 });
}

/* ---------- 6. AÇÕES NAS ORDENS ---------- */
let osDaFoto = null;
document.addEventListener("click", async (e) => {
  const btn = e.target.closest("[data-acao]");
  if (!btn) return;
  const id = Number(btn.closest(".os").dataset.id), os = ordens.find((o) => o.id === id);
  const acao = btn.dataset.acao;

  if (acao === "iniciar") {
    const r = await comBotao(btn, () => Api.campo.iniciar(id));
    if (r) { toast("Serviço iniciado. O morador foi avisado de que a equipe está no local."); carregar(); }

  } else if (acao === "devolver") {
    const motivo = await pedirTexto({ titulo: "Devolver a ordem de serviço ao gestor?", rotulo: "O que impediu a execução", confirmar: "Devolver" });
    if (!motivo) return;
    const r = await comBotao(btn, () => Api.campo.devolver(id, motivo));
    if (r) { toast("Ordem de serviço devolvida ao gestor."); carregar(); }

  } else if (acao === "foto-antes") {
    osDaFoto = id;
    $("#foto-antes").click();

  } else if (acao === "concluir") {
    concluindo = os;
    $("#form-concluir").reset();
    $("#k-erro").textContent = "";
    $("#k-titulo").textContent = `OS nº ${os.id} · ${os.titulo}`;
    $("#k-gps").textContent = "Conferindo a sua localização…";
    $("#dlg-concluir").showModal();
    posicao = (await ondeEstou()) || posicao;
    $("#k-gps").textContent = posicao
      ? "Localização registrada junto com a conclusão."
      : "Sem GPS: a conclusão será enviada e ficará marcada para conferência do gestor.";
  }
});

$("#foto-antes").addEventListener("change", async (e) => {
  const arquivo = e.target.files[0];
  e.target.value = "";
  if (!arquivo || !osDaFoto) return;
  try {
    await Api.campo.anexarFoto(osDaFoto, "ANTES", await comprimirFoto(arquivo));
    toast("Foto do antes anexada.");
    carregar();
  } catch (err) { toast(err.message); }
});

$("#k-cancelar").addEventListener("click", () => $("#dlg-concluir").close());
$("#form-concluir").addEventListener("submit", async (e) => {
  e.preventDefault();
  const btn = e.target.querySelector("[type=submit]"), erro = $("#k-erro");
  const relatorio = $("#k-relatorio").value.trim();
  if (relatorio.length < 10) { erro.textContent = "Descreva o serviço executado (mínimo de 10 caracteres)."; return; }
  btn.disabled = true;
  try {
    const arquivo = $("#k-foto").files[0];
    if (arquivo) await Api.campo.anexarFoto(concluindo.id, "DEPOIS", await comprimirFoto(arquivo));   // a foto vai antes: OS concluída não aceita anexo
    await Api.campo.concluir(concluindo.id, { relatorio, latitude: posicao?.latitude ?? null, longitude: posicao?.longitude ?? null });
    $("#dlg-concluir").close();
    toast("Serviço concluído. O morador já vê a ocorrência como resolvida.");
    carregar();
  } catch (err) { erro.textContent = err.message; } finally { btn.disabled = false; }
});

/* ---------- 7. INICIALIZAÇÃO ---------- */
(async () => {
  usuario = await exigirSessao(["COLABORADOR"]);
  if (!usuario) return;
  $("#c-nome").textContent = usuario.nome;
  $("#tela-app").hidden = false;
  await carregar();
  atualizarPosicao();
  /* Nova OS despachada pelo gestor aparece sozinha, sem recarregar a página */
  observarPulso(async () => { if (!$("#dlg-concluir").open) { await carregar(); if (abaAtual === "encerradas") carregarEncerradas(); } });
})();
