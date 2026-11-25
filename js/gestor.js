/* ==========================================================
   gestor.js · Painel do gestor (JavaScript puro + Leaflet no mapa)
   Abas: Painel · Fila de prioridade · Mapa · Equipes · Antifraude
   Toda regra de negócio fica na API; aqui só pedimos e mostramos.
   Depende de: api.js, comum.js
   ========================================================== */

/* ---------- 1. ESTADO ---------- */
let usuario = null;
let categorias = [];
let equipes = [];
let abaAtual = "painel";
let filaItens = [];            // itens já carregados na fila (paginação "Carregar mais")
let fichaId = null;            // ocorrência aberta na ficha
const PAGINA_FILA = 50;
const NOME_ABA = { painel: "Painel", fila: "Fila de prioridade", mapa: "Mapa", equipes: "Equipes", fraude: "Antifraude" };
const SLA_ROTULO = { NO_PRAZO: "No prazo", VENCENDO: "Vencendo", SEM_RESPOSTA: "Sem resposta", ATRASADA: "Atrasada", CUMPRIDO: "Prazo cumprido", DESCUMPRIDO: "Fora do prazo" };
const ACAO_ROTULO = { URGENCIA: "Urgência reclassificada", DUPLICATA: "Unificada com a nº", APOIOS_INVALIDADOS: "Apoios invalidados", DENUNCIAS: "Parecer das denúncias" };
const TIPO_ALERTA = { APOIOS_SUSPEITOS: "Manipulação do ranking", DENUNCIAS: "Denúncia", DUPLICATA: "Pedido repetido", APOIO_TROCADO: "Apoio recíproco", AUTOR_REINCIDENTE: "Autor reincidente", CONCLUSAO_FORA_DO_LOCAL: "Execução em campo" };
const MOTIVO_DENUNCIA = { FALSA: "Informação falsa", DUPLICADA: "Duplicada", OFENSIVA: "Conteúdo ofensivo", LOCAL_ERRADO: "Local errado", OUTRO: "Outro" };

const opcoes = (lista, vazio) => (vazio ? `<option value="">${vazio}</option>` : "") + lista.map((x) => `<option value="${x.id}">${esc(x.nome)}</option>`).join("");

/* ---------- 2. NAVEGAÇÃO POR ABAS ---------- */
const CARREGAR = { painel: carregarPainel, fila: () => carregarFila(true), mapa: carregarMapa, equipes: carregarEquipes, fraude: carregarFraude };

function abrirAba(nome) {
  abaAtual = nome;
  $$(".panel").forEach((p) => p.classList.toggle("active", p.id === "tab-" + nome));
  $$(".nav-btn[data-tab]").forEach((b) => b.classList.toggle("active", b.dataset.tab === nome));
  window.scrollTo({ top: 0 });
  CARREGAR[nome]();
}
$$(".nav-btn[data-tab]").forEach((b) => b.addEventListener("click", () => abrirAba(b.dataset.tab)));
$("#btn-sair").addEventListener("click", () => { Api.sair(); location.replace("index.html"); });

/* Mostra o erro dentro do bloco, sem derrubar o resto da tela */
async function tentar(destino, tarefa) {
  try { await tarefa(); } catch (err) { $(destino).innerHTML = `<p class="vazio">${esc(err.message)}</p>`; }
}

/* ---------- 3. PAINEL (KPIs em tempo real) ---------- */
function kpi(valor, rotulo, detalhe = "", critico = false) {
  return `<div class="stat${critico ? " critico" : ""}"><b>${valor}</b><span>${rotulo}</span>${detalhe ? `<small>${detalhe}</small>` : ""}</div>`;
}
const pct = (v) => (v == null ? "–" : `${v}%`);

/* Barras agrupadas por dia em SVG: sem biblioteca de gráfico */
function graficoSerie(serie) {
  const L = 760, A = 220, esq = 30, base = A - 26, topo = 12;
  const max = Math.max(1, ...serie.map((d) => Math.max(d.novas, d.resolvidas)));
  const passo = (L - esq - 6) / serie.length, larg = Math.max(2, Math.min(11, passo / 2 - 1.5));
  const y = (v) => base - (v / max) * (base - topo);
  const cada = Math.ceil(serie.length / 10);                    // no máximo ~10 datas no eixo
  const linhas = [0, Math.ceil(max / 2), max].filter((v, i, a) => a.indexOf(v) === i).map((v) =>
    `<line class="eixo" x1="${esq}" x2="${L}" y1="${y(v)}" y2="${y(v)}"/><text x="${esq - 6}" y="${y(v) + 4}" text-anchor="end">${v}</text>`).join("");
  const barras = serie.map((d, i) => {
    const x = esq + i * passo + passo / 2, dia = new Date(d.dia + "T12:00:00");
    const rot = dia.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" });
    return `<g><title>${rot}: ${d.novas} nova(s), ${d.resolvidas} resolvida(s)</title>
      <rect class="novas" x="${x - larg - 0.75}" y="${y(d.novas)}" width="${larg}" height="${base - y(d.novas)}" rx="2"/>
      <rect class="resolvidas" x="${x + 0.75}" y="${y(d.resolvidas)}" width="${larg}" height="${base - y(d.resolvidas)}" rx="2"/>
      ${i % cada === 0 ? `<text x="${x}" y="${A - 8}" text-anchor="middle">${rot}</text>` : ""}</g>`;
  }).join("");
  const novas = serie.reduce((s, d) => s + d.novas, 0), resolvidas = serie.reduce((s, d) => s + d.resolvidas, 0);
  return `<svg class="serie" viewBox="0 0 ${L} ${A}" role="img" aria-label="No período: ${novas} novas ocorrências e ${resolvidas} resolvidas">${linhas}${barras}</svg>`;
}

async function carregarPainel() {
  await tentar("#kpis", async () => {
    const p = await Api.gestao.painel($("#p-dias").value), r = p.resumo;
    $("#kpis").innerHTML = [
      kpi(r.abertas, "Aguardando triagem", r.sem_resposta ? `${r.sem_resposta} sem resposta no prazo` : "todas dentro do prazo de resposta", r.sem_resposta > 0),
      kpi(r.em_analise + r.em_andamento, "Em atendimento", `${r.em_analise} em análise · ${r.em_andamento} em campo`),
      kpi(r.atrasadas, "Prazo de solução estourado", "ocorrências em aberto", r.atrasadas > 0),
      kpi(duracao(r.resposta_media_h), "Tempo médio de 1ª resposta", `mediana ${duracao(r.resposta_mediana_h)}`),
      kpi(duracao(r.solucao_media_h), "Tempo médio de solução", `mediana ${duracao(r.solucao_mediana_h)}`),
      kpi(pct(r.sla_pct), "Resolvidas dentro do prazo", `${r.no_prazo} de ${r.resolvidas} no período`),
      kpi(pct(r.validacao_pct), "Taxa de validação", `${r.resolvidas} confirmadas · ${r.rejeitadas} rejeitadas`),
      kpi(r.novas, "Novas no período", `${r.resolvidas} resolvidas`),
    ].join("");

    $("#g-serie").innerHTML = graficoSerie(p.serie);

    const maxCat = Math.max(1, ...p.categorias.map((c) => c.ativas));
    $("#g-categorias").innerHTML = `<div class="barras">${p.categorias.map((c) => `
      <div><div class="rotulo"><span><b>${esc(c.nome)}</b> · ${c.ativas} em aberto</span><small>solução em ${duracao(c.solucao_media_h)}</small></div>
      <div class="trilho"><i style="width:${(c.ativas / maxCat) * 100}%"></i></div></div>`).join("")}</div>`;

    $("#g-regioes").innerHTML = p.regioes.length ? `<ol class="regioes">${p.regioes.map((g) => `
      <li><b>${g.ativas}</b><span>Região de ${esc(g.referencia || "local sem referência")}<small>${g.urgentes} de urgência alta</small></span>
      <button type="button" data-ver-mapa="${g.latitude},${g.longitude}">Ver no mapa</button></li>`).join("")}</ol>`
      : '<p class="vazio-bloco">Nenhuma ocorrência em aberto.</p>';

    $("#g-equipes").innerHTML = p.equipes.length ? `<table class="tabela">
      <thead><tr><th>Equipe</th><th class="n">Pessoas</th><th class="n">OS ativas</th><th class="n">Atrasadas</th><th class="n">Concluídas</th><th class="n">Devolvidas</th><th class="n">Tempo médio</th></tr></thead>
      <tbody>${p.equipes.map((e) => `<tr><td><b>${esc(e.nome)}</b></td><td class="n">${e.membros}</td><td class="n">${e.ativas}</td>
        <td class="n">${e.atrasadas ? `<span class="chip alerta">${e.atrasadas}</span>` : 0}</td><td class="n">${e.concluidas}</td><td class="n">${e.devolvidas}</td>
        <td class="n">${duracao(e.execucao_media_h)}</td></tr>`).join("")}</tbody></table>`
      : '<p class="vazio-bloco">Nenhuma equipe cadastrada. Crie a primeira na aba Equipes.</p>';

    $("#g-usuarios").innerHTML = p.usuarios.length ? `<table class="tabela">
      <thead><tr><th>Cidadão</th><th class="n">Registradas</th><th class="n">Confirmadas</th><th class="n">Rejeitadas</th><th class="n">Em aberto</th><th class="n">Validação</th><th class="n">Apoios válidos recebidos</th></tr></thead>
      <tbody>${p.usuarios.map((u) => `<tr class="${u.ativo ? "" : "inativo"}"><td><b>${esc(u.nome)}</b>${u.ativo ? "" : " (suspensa)"}</td><td class="n">${u.registradas}</td>
        <td class="n">${u.confirmadas}</td><td class="n">${u.rejeitadas}</td><td class="n">${u.em_aberto}</td><td class="n">${pct(u.validacao_pct)}</td><td class="n">${u.apoios_recebidos}</td></tr>`).join("")}</tbody></table>`
      : '<p class="vazio-bloco">Nenhuma ocorrência registrada no período.</p>';

    $("#atualizado").textContent = new Date().toLocaleTimeString("pt-BR");
    const vivo = $("#ao-vivo"); vivo.classList.remove("pulso"); void vivo.offsetWidth; vivo.classList.add("pulso");
  });
}
$("#p-dias").addEventListener("change", carregarPainel);

/* ---------- 4. FILA DE PRIORIDADE ---------- */
function textoSla(o) {
  if (o.sla === "ATRASADA" || o.sla === "VENCENDO" || o.sla === "NO_PRAZO") return prazo(o.prazo_solucao_em);
  if (o.sla === "SEM_RESPOSTA") return `sem resposta há ${duracao((Date.now() - new Date(o.criado_em)) / 36e5)}`;
  return SLA_ROTULO[o.sla];
}

function linhaHTML(o) {
  const diferenca = o.apoios_total - o.apoios_validos;
  return `
  <button type="button" class="linha" data-abrir="${o.id}" data-urgencia="${o.urgencia}">
    <span class="pos">${o.posicao}º</span>
    <span class="principal"><span class="titulo">${esc(o.titulo)}</span>
      <span class="meta">nº ${o.id} · ${esc(o.categoria_nome)} · ${esc(o.endereco_referencia)}${o.denuncias_pendentes ? ` · ⚑ ${o.denuncias_pendentes} denúncia(s)` : ""}</span></span>
    <span class="chip urg ${o.urgencia}">${URGENCIA[o.urgencia]}</span>
    <span class="apoios${diferenca ? " suspeito" : ""}" title="${o.apoios_validos} apoios válidos de ${o.apoios_total} registrados">▲ ${o.apoios_validos}${diferenca ? ` <small>de ${o.apoios_total}</small>` : ""}</span>
    <span class="chip sla ${o.sla}">${textoSla(o)}</span>
    <span class="badge ${o.status}">${ROTULO[o.status]}</span>
    <span class="equipe">${o.equipe_nome ? `${esc(o.equipe_nome)} · ${ROTULO_OS[o.os_status]}` : "<em>Sem equipe</em>"}</span>
  </button>`;
}

async function carregarFila(doInicio) {
  const quantos = doInicio ? Math.max(PAGINA_FILA, filaItens.length) : PAGINA_FILA;   // ao atualizar, mantém o que já estava aberto
  const filtros = {
    situacao: $("#f-situacao").value, status: $("#f-status").value, categoria_id: $("#f-categoria").value,
    urgencia: $("#f-urgencia").value, atrasadas: $("#f-atrasadas").checked || "", sem_os: $("#f-sem-os").checked || "",
    limite: Math.min(200, quantos), deslocamento: doInicio ? 0 : filaItens.length,
  };
  await tentar("#fila", async () => {
    const r = await Api.gestao.fila(filtros);
    filaItens = doInicio ? r.itens : filaItens.concat(r.itens);
    $("#fila").innerHTML = filaItens.length ? filaItens.map(linhaHTML).join("") : '<p class="vazio">Nenhuma ocorrência com esses filtros.</p>';
    $("#fila-total").textContent = `${r.total} ocorrência(s) · mostrando ${filaItens.length}`;
    $("#fila-mais").hidden = filaItens.length >= r.total;
  });
}
["#f-situacao", "#f-status", "#f-categoria", "#f-urgencia", "#f-atrasadas", "#f-sem-os"].forEach((s) =>
  $(s).addEventListener("change", () => { filaItens = []; carregarFila(true); }));
$("#fila-mais").addEventListener("click", () => carregarFila(false));

/* ---------- 5. MAPA (Leaflet + OpenStreetMap, com camadas) ---------- */
let mapa = null, pontosMapa = [], celulasMapa = [], enquadrado = false;
const grupos = {};                                             // camada → L.layerGroup
const COR = { ABERTA: "#E53E3E", EM_ANALISE: "#D69E2E", EM_ANDAMENTO: "#FF5A00", RESOLVIDA: "#38A169", REJEITADA: "#718096" };
const RAIO = { ALTA: 11, MEDIA: 8, BAIXA: 6 };

function iniciarMapa() {
  if (mapa) { mapa.invalidateSize(); return true; }
  if (!window.L) {
    $("#mapa-gestao").innerHTML = '<p class="sem-mapa">Não foi possível carregar o mapa (biblioteca Leaflet indisponível). Verifique a conexão com a internet.</p>';
    return false;
  }
  mapa = L.map("mapa-gestao").setView([-23.5614, -46.6559], 13);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19, attribution: '&copy; colaboradores do <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
  }).addTo(mapa);
  $$("#camadas .camada").forEach((b) => { grupos[b.dataset.camada] = L.layerGroup(); if (b.classList.contains("ativo")) grupos[b.dataset.camada].addTo(mapa); });
  mapa.on("popupopen", (e) => {
    const btn = e.popup.getElement().querySelector("[data-abrir]");
    if (btn) btn.addEventListener("click", () => abrirFicha(Number(btn.dataset.abrir)));
  });
  return true;
}

function desenharMapa() {
  Object.values(grupos).forEach((g) => g.clearLayers());
  const soAtrasadas = $("#m-atrasadas").checked;
  pontosMapa.forEach((p) => {
    if (soAtrasadas && !p.atrasada) return;
    const camada = COR[p.status] && ["RESOLVIDA", "REJEITADA"].includes(p.status) ? "ENCERRADAS" : p.status;
    L.circleMarker([p.latitude, p.longitude], {
      radius: RAIO[p.urgencia], fillColor: COR[p.status], fillOpacity: 0.9,
      color: p.atrasada ? "#1A1C24" : "#fff", weight: p.atrasada ? 3 : 2,
    }).bindPopup(`<b>${esc(p.titulo)}</b>${esc(p.categoria_nome)} · ${ROTULO[p.status]} · urgência ${URGENCIA[p.urgencia].toLowerCase()}<br>
        ${esc(p.endereco_referencia)}<br>▲ ${p.apoios_validos} apoio(s) válido(s)${p.equipe_nome ? ` · ${esc(p.equipe_nome)}` : ""}${p.atrasada ? "<br><b>Prazo estourado</b>" : ""}
        <br><button type="button" data-abrir="${p.id}">Abrir ficha</button>`).addTo(grupos[camada]);
  });
  // Densidade: um círculo por célula de ~550 m, mais forte onde há mais ocorrências em aberto
  const max = Math.max(1, ...celulasMapa.map((c) => c.ativas));
  celulasMapa.forEach((c) => L.circle([c.latitude, c.longitude], {
    radius: 300, stroke: false, fillColor: "#FF5A00", fillOpacity: 0.15 + 0.45 * (c.ativas / max),
  }).bindTooltip(`${c.ativas} em aberto nesta região`).addTo(grupos.DENSIDADE));
  if (!enquadrado && pontosMapa.length) {
    mapa.fitBounds(L.latLngBounds(pontosMapa.map((p) => [p.latitude, p.longitude])).pad(0.1));
    enquadrado = true;
  }
}

async function carregarMapa() {
  if (!iniciarMapa()) return;
  try {
    const r = await Api.gestao.mapa();
    pontosMapa = r.pontos; celulasMapa = r.celulas;
    desenharMapa();
  } catch (err) { toast(err.message); }
}
$$("#camadas .camada").forEach((b) => b.addEventListener("click", () => {
  const ligado = b.classList.toggle("ativo");
  b.setAttribute("aria-pressed", ligado);
  if (mapa) ligado ? grupos[b.dataset.camada].addTo(mapa) : grupos[b.dataset.camada].remove();
}));
$("#m-atrasadas").addEventListener("change", () => { if (mapa) desenharMapa(); });

/* ---------- 6. EQUIPES ---------- */
async function carregarEquipes() {
  await tentar("#equipes", async () => {
    let colaboradores;
    [equipes, colaboradores] = await Promise.all([Api.gestao.equipes(), Api.gestao.usuarios("COLABORADOR")]);
    $("#equipes").innerHTML = equipes.length ? equipes.map((e) => `
      <article class="bloco equipe-card">
        <h3>${esc(e.nome)}</h3>
        <p class="meta">${esc(e.categoria_nome || "Geral")} · ${e.os_ativas} ordem(ns) de serviço ativa(s)</p>
        <ul>${e.membros.length ? e.membros.map((m) => `<li><span>${esc(m.nome)}</span>
          <button type="button" class="btn-mini" data-remover="${m.id}" data-equipe="${e.id}">Tirar da equipe</button></li>`).join("")
          : '<li class="meta">Nenhum colaborador nesta equipe.</li>'}</ul>
      </article>`).join("") : '<p class="vazio">Nenhuma equipe cadastrada ainda.</p>';

    const ativas = equipes.filter((e) => e.ativa);
    $("#colaboradores").innerHTML = colaboradores.length ? `<table class="tabela">
      <thead><tr><th>Nome</th><th>E-mail</th><th>Equipe</th><th>Conta</th></tr></thead>
      <tbody>${colaboradores.map((c) => `<tr class="${c.ativo ? "" : "inativo"}"><td><b>${esc(c.nome)}</b></td><td>${esc(c.email)}</td>
        <td>${c.ativo ? `<select data-mover="${c.id}" aria-label="Equipe de ${esc(c.nome)}">
              <option value="">Sem equipe</option>${ativas.map((e) => `<option value="${e.id}"${e.id === c.equipe_id ? " selected" : ""}>${esc(e.nome)}</option>`).join("")}</select>` : "–"}</td>
        <td><button type="button" class="btn-mini${c.ativo ? " perigo" : ""}" data-conta="${c.id}" data-ativo="${c.ativo}" data-nome="${esc(c.nome)}">${c.ativo ? "Suspender" : "Reativar"}</button></td></tr>`).join("")}</tbody></table>`
      : '<p class="vazio-bloco">Nenhum colaborador cadastrado.</p>';
    $("#s-equipe").innerHTML = opcoes(ativas, "Definir depois");
  });
}

$("#form-equipe").addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    await Api.gestao.criarEquipe($("#e-nome").value, Number($("#e-categoria").value) || null);
    e.target.reset(); $("#e-erro").textContent = ""; toast("Equipe criada.");
    carregarEquipes();
  } catch (err) { $("#e-erro").textContent = err.message; }
});

$("#s-cpf").addEventListener("input", (e) => {
  e.target.value = e.target.value.replace(/\D/g, "").slice(0, 11)
    .replace(/(\d{3})(\d)/, "$1.$2").replace(/(\d{3})(\d)/, "$1.$2").replace(/(\d{3})(\d{1,2})$/, "$1-$2");
});
$("#form-colab").addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    const novo = await Api.gestao.criarServidor({
      nome: $("#s-nome").value.trim(), cpf: $("#s-cpf").value, data_nascimento: $("#s-nasc").value || null,
      email: $("#s-email").value.trim(), senha: $("#s-senha").value, perfil: $("#s-perfil").value,
      equipe_id: Number($("#s-equipe").value) || null,
    });
    e.target.reset(); $("#s-erro").textContent = ""; toast(`Conta de ${novo.nome} criada.`);
    carregarEquipes();
  } catch (err) { $("#s-erro").textContent = err.message; }
});

/* Suspender / reativar conta (usado em Equipes, Antifraude e na ficha) */
async function mudarConta(id, nome, ativar, btn) {
  const motivo = await pedirTexto({
    titulo: ativar ? `Reativar a conta de ${nome}?` : `Suspender a conta de ${nome}?`,
    rotulo: ativar ? "Motivo da reativação" : "Motivo (a conta perde o acesso e os apoios dela saem do ranking)",
    confirmar: ativar ? "Reativar conta" : "Suspender conta",
  });
  if (!motivo) return false;
  const r = await comBotao(btn, () => Api.gestao.situacaoConta(id, ativar, motivo));
  if (r) toast(ativar ? "Conta reativada." : "Conta suspensa.");
  return !!r;
}

/* ---------- 7. ANTIFRAUDE ---------- */
async function carregarFraude() {
  try {
    const r = await Api.gestao.fraude();
    const n = $("#fraude-n"); n.textContent = r.total; n.hidden = !r.total;
    if (abaAtual !== "fraude") return;
    $("#alertas").innerHTML = r.alertas.length ? r.alertas.map((a) => `
      <article class="alerta-card ${a.gravidade}">
        <span class="tipo">${TIPO_ALERTA[a.tipo]} · gravidade ${URGENCIA[a.gravidade].toLowerCase()}</span>
        <h3>${esc(a.titulo)}</h3>
        <p>${esc(a.detalhe)}</p>
        <div class="acoes-alerta">
          ${a.ocorrencia_id ? `<button type="button" class="btn-mini" data-abrir="${a.ocorrencia_id}">Abrir ficha da ocorrência</button>` : ""}
          ${a.usuario_id ? `<button type="button" class="btn-mini perigo" data-conta="${a.usuario_id}" data-ativo="true" data-nome="${esc(a.usuario_nome)}">Suspender conta</button>` : ""}
        </div>
      </article>`).join("") : '<p class="vazio">Nenhum padrão suspeito no momento.</p>';
  } catch (err) { if (abaAtual === "fraude") $("#alertas").innerHTML = `<p class="vazio">${esc(err.message)}</p>`; }
}

/* ---------- 8. FICHA DA OCORRÊNCIA (decisão) ---------- */
const ficha = $("#ficha");

function linhaDoTempo(itens) {
  return `<ol class="tempo">${itens.map((h) => `<li><b>${ROTULO[h.status_novo]}</b> · ${dataHora(h.alterado_em)} · ${esc(h.autor_nome)}${h.observacao ? `<br><small>${esc(h.observacao)}</small>` : ""}</li>`).join("")}</ol>`;
}

function osHTML(os) {
  const avisos = [];
  if (os.fora_do_local) avisos.push(`<span class="chip alerta">Concluída a ${distancia(os.distancia_conclusao_m)} do local</span>`);
  if (os.sem_gps) avisos.push('<span class="chip VENCENDO">Concluída sem GPS</span>');
  if (os.status === "CONCLUIDA" && !os.fotos.length) avisos.push('<span class="chip">Sem foto</span>');
  return `<div class="os-item">
    <div class="chips"><b>OS nº ${os.id}</b><span class="chip">${ROTULO_OS[os.status]}</span>${avisos.join("")}</div>
    <span>${esc(os.equipe_nome)}${os.responsavel_nome ? ` · ${esc(os.responsavel_nome)}` : ""} · criada em ${dataHora(os.criado_em)} · prazo ${dataHora(os.prazo_em)}</span>
    ${os.instrucoes ? `<span><b>Instruções:</b> ${esc(os.instrucoes)}</span>` : ""}
    ${os.relatorio ? `<span><b>Relato da equipe:</b> ${esc(os.relatorio)}</span>` : ""}
    ${os.motivo_encerramento ? `<span><b>Motivo:</b> ${esc(os.motivo_encerramento)}</span>` : ""}
    ${os.fotos.length ? `<div class="miniaturas">${os.fotos.map((f) => `<figure><img data-foto="${f.id}" alt="Foto ${f.tipo === "ANTES" ? "antes" : "depois"} do serviço"><figcaption>${f.tipo === "ANTES" ? "Antes" : "Depois"}</figcaption></figure>`).join("")}</div>` : ""}
  </div>`;
}

function fichaHTML(o) {
  const aberta = ["ABERTA", "EM_ANALISE", "EM_ANDAMENTO"].includes(o.status);
  const equipesAtivas = equipes.filter((e) => e.ativa);
  const sugerida = equipesAtivas.find((e) => e.categoria_id === o.categoria_id);     // equipe da especialidade
  const a = o.apoios;

  const despacho = !aberta ? "" : o.os_id ? `
    <div class="acao"><h4>Ordem de serviço ativa</h4>
      <span>OS nº ${o.os_id} · ${esc(o.equipe_nome)} · ${ROTULO_OS[o.os_status]}<br><small>${prazo(o.os_prazo_em)}</small></span>
      <div class="botoes"><button type="button" class="btn-acao perigo" data-f="cancelar-os" data-os="${o.os_id}">Cancelar OS…</button></div>
    </div>` : `
    <form class="acao" data-f="despachar"><h4>Despachar para uma equipe</h4>
      ${equipesAtivas.length ? `
      <label>Equipe<select name="equipe" required>${equipesAtivas.map((e) => `<option value="${e.id}"${sugerida && sugerida.id === e.id ? " selected" : ""}>${esc(e.nome)} (${e.os_ativas} ativa${e.os_ativas === 1 ? "" : "s"})</option>`).join("")}</select></label>
      <label>Instruções para a equipe<textarea name="instrucoes" rows="2" maxlength="1000" placeholder="Opcional"></textarea></label>
      <small>Prazo: o da urgência (${dataHora(o.prazo_solucao_em)})${new Date(o.prazo_solucao_em) < Date.now() ? ", já vencido: a equipe terá 24 h" : ""}.</small>
      <div class="botoes"><button class="btn-acao principal" type="submit">Atribuir ordem de serviço</button></div>`
      : "<span>Cadastre uma equipe na aba Equipes para despachar.</span>"}
    </form>`;

  const triagem = !aberta ? "" : `
    <div class="acao"><h4>Triagem</h4>
      <label>Urgência<select data-urgencia>${["ALTA", "MEDIA", "BAIXA"].map((u) => `<option value="${u}"${u === o.urgencia ? " selected" : ""}>${URGENCIA[u]}</option>`).join("")}</select></label>
      <div class="botoes">
        <button type="button" class="btn-acao" data-f="reclassificar">Reclassificar…</button>
        ${o.status === "ABERTA" ? '<button type="button" class="btn-acao" data-f="status" data-status="EM_ANALISE">Colocar em análise</button>' : ""}
        ${o.status === "EM_ANDAMENTO" && !o.os_id ? '<button type="button" class="btn-acao" data-f="status" data-status="RESOLVIDA">Marcar como resolvida…</button>' : ""}
        ${o.status !== "EM_ANDAMENTO" ? '<button type="button" class="btn-acao perigo" data-f="status" data-status="REJEITADA">Rejeitar…</button>' : ""}
      </div>
    </div>`;

  return `<div class="ficha-corpo">
    <header><h2><small>nº ${o.id}</small> ${esc(o.titulo)}</h2><button type="button" class="fechar" data-f="fechar" aria-label="Fechar">×</button></header>
    <div class="chips">
      <span class="badge ${o.status}">${ROTULO[o.status]}</span>
      <span class="chip ${o.urgencia}">Urgência ${URGENCIA[o.urgencia].toLowerCase()}${o.urgencia_revisada ? " (revisada)" : " (informada pelo cidadão)"}</span>
      <span class="chip ${o.sla}">${textoSla(o)}</span>
      <span class="chip">${esc(o.categoria_nome)}</span>
      ${o.duplicada_de ? `<button type="button" class="link-btn" data-abrir="${o.duplicada_de}">Duplicata da nº ${o.duplicada_de}</button>` : ""}
    </div>
    <p class="desc">${esc(o.descricao)}</p>
    <p class="meta">${esc(o.endereco_referencia)} · <a href="https://www.openstreetmap.org/?mlat=${o.latitude}&mlon=${o.longitude}#map=18/${o.latitude}/${o.longitude}" target="_blank" rel="noopener">abrir no mapa</a><br>
      Registrada em ${dataHora(o.criado_em)} por <b>${esc(o.autor.nome)}</b> (${o.autor.ocorrencias} ocorrência(s), ${o.autor.rejeitadas} rejeitada(s))
      ${o.autor.ativo ? `<button type="button" class="link-btn" data-conta="${o.autor.id}" data-ativo="true" data-nome="${esc(o.autor.nome)}">Suspender conta</button>` : '<span class="chip alerta">Conta suspensa</span>'}</p>

    ${aberta ? `<div class="duas">${despacho}${triagem}</div>` : ""}

    <section><h3>Validação social</h3>
      <span><b>${a.validos}</b> apoio(s) contam no ranking, de <b>${a.total}</b> registrado(s).
        ${a.em_carencia ? ` ${a.em_carencia} de contas ainda em carência.` : ""}${a.de_contas_suspensas ? ` ${a.de_contas_suspensas} de contas suspensas.` : ""}${a.invalidados ? ` ${a.invalidados} invalidado(s) pela gestão.` : ""}</span>
      ${a.suspeitos ? `<div class="botoes"><span class="chip alerta">${a.suspeitos} apoio(s) de contas recém-criadas</span>
        <button type="button" class="btn-acao perigo" data-f="invalidar">Invalidar esses apoios…</button></div>` : ""}
    </section>

    ${o.denuncias.length ? `<section><h3>Denúncias</h3>
      <ul class="lista-simples">${o.denuncias.map((d) => `<li><span><b>${MOTIVO_DENUNCIA[d.motivo]}</b> · ${esc(d.autor_nome)} · ${data(d.criado_em)}${d.detalhe ? `<br><small>${esc(d.detalhe)}</small>` : ""}</span>
        <span class="chip${d.situacao === "PENDENTE" ? " VENCENDO" : ""}">${d.situacao === "PENDENTE" ? "Aguardando parecer" : d.situacao === "PROCEDENTE" ? "Procedente" : "Improcedente"}</span></li>`).join("")}</ul>
      ${o.denuncias_pendentes ? `<div class="botoes"><button type="button" class="btn-acao" data-f="denuncias" data-procedente="false">Improcedentes: arquivar</button>
        <button type="button" class="btn-acao" data-f="denuncias" data-procedente="true">Procedentes</button></div>` : ""}
    </section>` : ""}

    ${o.possiveis_duplicatas.length && aberta ? `<section><h3>Possíveis duplicatas (mesma categoria, bem perto)</h3>
      <ul class="lista-simples">${o.possiveis_duplicatas.map((d) => `<li><span><button type="button" class="link-btn" data-abrir="${d.id}">nº ${d.id}</button> ${esc(d.titulo)}
        <br><small>a ${d.distancia_m} m · ${esc(d.autor_nome)} · ${ROTULO[d.status]} · ▲ ${d.apoios_validos}</small></span>
        <button type="button" class="btn-mini" data-f="unificar" data-principal="${d.id}">Unificar esta na nº ${d.id}</button></li>`).join("")}</ul>
    </section>` : ""}

    ${o.ordens.length ? `<section><h3>Ordens de serviço</h3>${o.ordens.map(osHTML).join("")}</section>` : ""}

    <section><h3>Linha do tempo (o que o cidadão vê)</h3>${linhaDoTempo(o.historico)}</section>

    ${o.auditoria.length ? `<section><h3>Auditoria das decisões</h3>
      <ol class="tempo">${o.auditoria.map((x) => `<li><b>${ACAO_ROTULO[x.acao] || x.acao}</b>${x.valor_anterior ? ` ${esc(URGENCIA[x.valor_anterior] || x.valor_anterior)} →` : ""} ${esc(URGENCIA[x.valor_novo] || x.valor_novo || "")}
        · ${dataHora(x.criado_em)} · ${esc(x.autor_nome)}${x.motivo ? `<br><small>${esc(x.motivo)}</small>` : ""}</li>`).join("")}</ol></section>` : ""}
  </div>`;
}

function mostrarFicha(o) {
  fichaId = o.id;
  ficha.innerHTML = fichaHTML(o);
  carregarFotos(ficha);
  if (!ficha.open) ficha.showModal();
  $(".ficha-corpo", ficha).scrollTop = 0;
}

async function abrirFicha(id) {
  try {
    if (!equipes.length) equipes = await Api.gestao.equipes();
    mostrarFicha(await Api.gestao.ficha(id));
  } catch (err) { toast(err.message); }
}

/* Depois de qualquer decisão: redesenha a ficha e atualiza a aba que está por trás */
function aposDecisao(fichaNova, mensagem) {
  if (mensagem) toast(mensagem);
  if (fichaNova) mostrarFicha(fichaNova);
  CARREGAR[abaAtual]();
  if (abaAtual !== "fraude") carregarFraude();
}

ficha.addEventListener("submit", async (e) => {
  const form = e.target.closest("[data-f='despachar']");
  if (!form) return;
  e.preventDefault();
  const r = await comBotao(form.querySelector("[type=submit]"), () => Api.gestao.despachar(fichaId, {
    equipe_id: Number(form.equipe.value), instrucoes: form.instrucoes.value.trim() || null,
  }));
  if (r) { equipes = []; aposDecisao(r, `Ordem de serviço nº ${r.os_id} atribuída à equipe ${r.equipe_nome}.`); }
});

ficha.addEventListener("click", async (e) => {
  const btn = e.target.closest("[data-f]");
  if (!btn || btn.tagName === "FORM") return;
  const f = btn.dataset.f;
  if (f === "fechar") return ficha.close();

  if (f === "status") {
    const novo = btn.dataset.status;
    let obs = `Alterado por ${usuario.nome}.`;
    if (novo !== "EM_ANALISE") {
      obs = await pedirTexto({
        titulo: novo === "REJEITADA" ? "Rejeitar a ocorrência?" : "Marcar como resolvida?",
        rotulo: novo === "REJEITADA" ? "Motivo (o cidadão verá este texto)" : "O que foi feito (o cidadão verá este texto)",
        confirmar: novo === "REJEITADA" ? "Rejeitar" : "Marcar como resolvida",
      });
      if (!obs) return;
    }
    const ok = await comBotao(btn, () => Api.alterarStatus(fichaId, novo, obs));
    if (ok) aposDecisao(await Api.gestao.ficha(fichaId), `Status alterado para ${ROTULO[novo]}.`);

  } else if (f === "reclassificar") {
    const nova = $("[data-urgencia]", ficha).value;
    const motivo = await pedirTexto({ titulo: `Reclassificar a urgência para ${URGENCIA[nova].toLowerCase()}?`, rotulo: "Motivo (fica na auditoria)", confirmar: "Reclassificar" });
    if (!motivo) return;
    const r = await comBotao(btn, () => Api.gestao.reclassificar(fichaId, nova, motivo));
    if (r) aposDecisao(r, "Urgência reclassificada.");

  } else if (f === "cancelar-os") {
    const motivo = await pedirTexto({ titulo: "Cancelar a ordem de serviço?", rotulo: "Motivo (a equipe e o cidadão verão)", confirmar: "Cancelar OS" });
    if (!motivo) return;
    const r = await comBotao(btn, () => Api.gestao.cancelarOS(btn.dataset.os, motivo));
    if (r) { equipes = []; aposDecisao(r, "Ordem de serviço cancelada."); }

  } else if (f === "invalidar") {
    const motivo = await pedirTexto({ titulo: "Invalidar os apoios de contas recém-criadas?", rotulo: "Motivo (fica na auditoria)", confirmar: "Invalidar apoios" });
    if (!motivo) return;
    const r = await comBotao(btn, () => Api.gestao.invalidarApoios(fichaId, motivo));
    if (r) aposDecisao(r.ocorrencia, `${r.invalidados} apoio(s) saíram do ranking.`);

  } else if (f === "denuncias") {
    const procedente = btn.dataset.procedente === "true";
    const r = await comBotao(btn, () => Api.gestao.analisarDenuncias(fichaId, procedente));
    if (r) aposDecisao(r.ocorrencia, procedente ? "Denúncias procedentes. Decida agora o destino da ocorrência." : "Denúncias arquivadas.");

  } else if (f === "unificar") {
    const principal = Number(btn.dataset.principal);
    if (!confirm(`Encerrar a nº ${fichaId} como duplicata e levar os apoios dela para a nº ${principal}?`)) return;
    const r = await comBotao(btn, () => Api.gestao.unificar(fichaId, principal));
    if (r) aposDecisao(r, `Unificada. Agora você está na ficha da nº ${principal}.`);
  }
});

/* ---------- 9. CLIQUES GERAIS (delegação) ---------- */
document.addEventListener("click", async (e) => {
  const abrir = e.target.closest("[data-abrir]");
  if (abrir) return abrirFicha(Number(abrir.dataset.abrir));

  const verMapa = e.target.closest("[data-ver-mapa]");
  if (verMapa) {
    const [lat, lng] = verMapa.dataset.verMapa.split(",").map(Number);
    abrirAba("mapa");
    if (mapa) { enquadrado = true; mapa.setView([lat, lng], 16); }
    return;
  }

  const conta = e.target.closest("[data-conta]");
  if (conta) {
    const mudou = await mudarConta(Number(conta.dataset.conta), conta.dataset.nome, conta.dataset.ativo !== "true", conta);
    if (mudou) {
      if (ficha.open && fichaId) aposDecisao(await Api.gestao.ficha(fichaId)); else CARREGAR[abaAtual]();
    }
    return;
  }

  const remover = e.target.closest("[data-remover]");
  if (remover) {
    await comBotao(remover, () => Api.gestao.removerMembro(remover.dataset.equipe, remover.dataset.remover));
    carregarEquipes();
  }
});

document.addEventListener("change", async (e) => {
  const mover = e.target.closest("[data-mover]");
  if (!mover) return;
  const id = Number(mover.dataset.mover), destino = Number(mover.value);
  try {
    if (destino) await Api.gestao.incluirMembro(destino, id);
    else { const atual = equipes.find((eq) => eq.membros.some((m) => m.id === id)); if (atual) await Api.gestao.removerMembro(atual.id, id); }
    toast("Equipe atualizada.");
  } catch (err) { toast(err.message); }
  carregarEquipes();
});

/* ---------- 10. INICIALIZAÇÃO ---------- */
(async () => {
  usuario = await exigirSessao(["GESTOR", "ADMIN"]);
  if (!usuario) return;
  $("#nome-usuario").textContent = usuario.nome.split(" ")[0];
  $("#perfil-usuario").textContent = usuario.perfil === "ADMIN" ? "Administração" : "Gestão";
  $("#avatar-letra").textContent = usuario.nome[0];
  if (usuario.perfil === "ADMIN") $("#s-perfil").insertAdjacentHTML("beforeend", '<option value="GESTOR">Gestor</option>');
  $("#tela-app").hidden = false;
  try {
    categorias = await Api.categorias();
    $("#f-categoria").innerHTML = opcoes(categorias, "Todas as categorias");
    $("#e-categoria").innerHTML = opcoes(categorias, "Geral (todas as categorias)");
  } catch (err) { toast(err.message); }
  abrirAba("painel");
  carregarFraude();
  /* Tempo real: quando qualquer dado muda no banco, a aba aberta se atualiza sozinha.
     A ficha aberta não é redesenhada para não atrapalhar quem está decidindo. */
  observarPulso(() => CARREGAR[abaAtual]());
  /* Rede de segurança: os prazos andam com o relógio mesmo sem ninguém escrever no banco.
     O contador do antifraude também se atualiza aqui (as consultas dele são as mais pesadas,
     então não rodam a cada mudança, só a cada minuto). */
  setInterval(() => {
    if (document.hidden || ficha.open) return;
    CARREGAR[abaAtual]();
    if (abaAtual !== "fraude") carregarFraude();
  }, 60000);
})();
