/* ==========================================================
   comum.js · Utilitários das telas de GESTÃO e de CAMPO
   (gestor.html e campo.html). A tela do cidadão tem os seus
   próprios em app.js; aqui ficam os que as duas telas novas
   compartilham. Depende de: api.js
   ========================================================== */

const $ = (sel, raiz = document) => raiz.querySelector(sel);
const $$ = (sel, raiz = document) => raiz.querySelectorAll(sel);

/* Escapa texto vindo do usuário antes de usar em innerHTML */
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const ROTULO = { ABERTA: "Aberta", EM_ANALISE: "Em análise", EM_ANDAMENTO: "Em andamento", RESOLVIDA: "Resolvida", REJEITADA: "Rejeitada" };
const URGENCIA = { BAIXA: "Baixa", MEDIA: "Média", ALTA: "Alta" };
const ROTULO_OS = { ATRIBUIDA: "Atribuída", EM_EXECUCAO: "Em execução", CONCLUIDA: "Concluída", DEVOLVIDA: "Devolvida", CANCELADA: "Cancelada" };
const PAGINA = { CIDADAO: "index.html", COLABORADOR: "campo.html", GESTOR: "gestor.html", ADMIN: "gestor.html" };

/* ---------- Datas e durações ---------- */
const data = (iso) => new Date(iso).toLocaleDateString("pt-BR");
const dataHora = (iso) => new Date(iso).toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
const numero = (n, casas = 0) => Number(n).toLocaleString("pt-BR", { minimumFractionDigits: casas, maximumFractionDigits: casas });

/* 0.5 → "30 min" · 7.2 → "7,2 h" · 80 → "3,3 d" */
function duracao(horas) {
  if (horas == null) return "–";
  const h = Math.abs(Number(horas));
  if (h < 1) return `${Math.max(1, Math.round(h * 60))} min`;
  if (h < 48) return `${numero(h, h < 10 ? 1 : 0)} h`;
  return `${numero(h / 24, h < 240 ? 1 : 0)} d`;
}

/* Quanto falta (ou quanto passou) de um prazo: "vence em 5 h" · "atrasada há 2,1 d" */
function prazo(iso) {
  const h = (new Date(iso) - Date.now()) / 36e5;
  return h >= 0 ? `vence em ${duracao(h)}` : `atrasada há ${duracao(h)}`;
}

/* Distância em metros → "350 m" · "2,4 km" */
const distancia = (m) => (m == null ? "" : m < 1000 ? `${Math.round(m / 10) * 10} m` : `${numero(m / 1000, 1)} km`);

/* ---------- Avisos ---------- */
function toast(msg) {
  const t = $("#toast"); t.textContent = msg; t.classList.add("show");
  clearTimeout(toast.id); toast.id = setTimeout(() => t.classList.remove("show"), 3500);
}

/* Desabilita o botão enquanto a API responde (evita clique duplo) e mostra o erro em um toast */
async function comBotao(btn, tarefa) {
  if (btn) btn.disabled = true;
  try { return await tarefa(); } catch (err) { toast(err.message); return undefined; } finally { if (btn) btn.disabled = false; }
}

/* ---------- Sessão ---------- */
/* Chamado pelo api.js quando o token vence: volta para o login */
function aoExpirarSessao() { Api.sair(); location.replace("index.html"); }

/* Garante que há alguém logado com um dos perfis aceitos; senão, manda para a página certa */
async function exigirSessao(perfis) {
  if (!Api.temSessao()) { location.replace("index.html"); return null; }
  let u;
  try { u = await Api.eu(); } catch { Api.sair(); location.replace("index.html"); return null; }
  if (!perfis.includes(u.perfil)) { location.replace(PAGINA[u.perfil] || "index.html"); return null; }
  return u;
}

/* ---------- Tempo real ----------
   Pergunta a versão dos dados a cada poucos segundos (uma leitura de um
   número só) e chama aoMudar() quando ela muda. Com a aba em segundo plano
   não consulta nada; ao voltar, confere na hora. */
function observarPulso(aoMudar, intervaloMs = 5000) {
  let versao = null, ocupado = false;
  async function conferir() {
    if (document.hidden || ocupado || !Api.temSessao()) return;
    ocupado = true;
    try {
      const v = (await Api.pulso()).versao;
      if (versao !== null && v !== versao) await aoMudar();
      versao = v;
    } catch { /* falha de rede: tenta de novo no próximo ciclo */ } finally { ocupado = false; }
  }
  conferir();
  setInterval(conferir, intervaloMs);
  document.addEventListener("visibilitychange", conferir);
}

/* ---------- Caixa de texto obrigatório (motivos) ----------
   Devolve o texto digitado ou null se a pessoa cancelar. */
function pedirTexto({ titulo, rotulo, confirmar = "Confirmar", minimo = 5 }) {
  let dlg = $("#dlg-texto");
  if (!dlg) {
    dlg = document.createElement("dialog");
    dlg.id = "dlg-texto";
    dlg.innerHTML = `<form novalidate>
        <h2></h2>
        <label class="campo"><span></span><textarea rows="3" maxlength="500"></textarea></label>
        <p class="form-erro" role="alert"></p>
        <div class="dialog-acoes"><button class="btn-primary" type="submit"></button><button class="btn-sec" type="button">Cancelar</button></div>
      </form>`;
    document.body.append(dlg);
  }
  $("h2", dlg).textContent = titulo;
  $("label span", dlg).textContent = rotulo;
  $(".btn-primary", dlg).textContent = confirmar;
  $(".form-erro", dlg).textContent = "";
  const campo = $("textarea", dlg);
  campo.value = "";
  return new Promise((resolver) => {
    const fechar = (valor) => { dlg.close(); $("form", dlg).onsubmit = null; resolver(valor); };
    $("form", dlg).onsubmit = (e) => {
      e.preventDefault();
      const texto = campo.value.trim();
      if (texto.length < minimo) { $(".form-erro", dlg).textContent = `Escreva pelo menos ${minimo} caracteres.`; return; }
      fechar(texto);
    };
    $(".btn-sec", dlg).onclick = () => fechar(null);
    dlg.oncancel = (e) => { e.preventDefault(); fechar(null); };
    dlg.showModal();
    campo.focus();
  });
}

/* ---------- Fotos ---------- */
/* Reduz a foto no próprio aparelho (máx. 1280 px, JPEG) antes de enviar: economiza o plano de dados da equipe */
function comprimirFoto(arquivo, lado = 1280, qualidade = 0.8) {
  return new Promise((resolver, rejeitar) => {
    const img = new Image();
    img.onload = () => {
      const escala = Math.min(1, lado / Math.max(img.width, img.height));
      const tela = document.createElement("canvas");
      tela.width = Math.round(img.width * escala); tela.height = Math.round(img.height * escala);
      tela.getContext("2d").drawImage(img, 0, 0, tela.width, tela.height);
      URL.revokeObjectURL(img.src);
      resolver(tela.toDataURL("image/jpeg", qualidade));
    };
    img.onerror = () => rejeitar(new Error("Não foi possível ler a foto."));
    img.src = URL.createObjectURL(arquivo);
  });
}

/* Preenche as miniaturas <img data-foto="id"> (as fotos exigem login, então vêm por fetch) */
function carregarFotos(raiz = document) {
  $$("img[data-foto]", raiz).forEach(async (img) => {
    try { img.src = await Api.fotoUrl(img.dataset.foto); } catch { img.alt = "Foto indisponível"; }
    img.removeAttribute("data-foto");
  });
}

/* Posição do aparelho; devolve null se o GPS falhar ou a pessoa negar */
function ondeEstou(esperaMs = 8000) {
  return new Promise((resolver) => {
    if (!navigator.geolocation) return resolver(null);
    navigator.geolocation.getCurrentPosition(
      (p) => resolver({ latitude: p.coords.latitude, longitude: p.coords.longitude, precisao: p.coords.accuracy }),
      () => resolver(null),
      { enableHighAccuracy: true, timeout: esperaMs, maximumAge: 30000 });
  });
}
