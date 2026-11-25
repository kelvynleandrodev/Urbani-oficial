/* ==========================================================
   auth.js · Login, cadastro e sessão
   As validações valem no servidor (CPF, idade, duplicidade);
   aqui ficam só a máscara do CPF e a confirmação de senha.
   Depende de: api.js, app.js ($, $$, toast, iniciarApp)
   ========================================================== */

/* ---------- Utilitários ---------- */
const soDigitos = (s) => String(s).replace(/\D/g, "");
const mascaraCpf = (s) => soDigitos(s).slice(0, 11)
  .replace(/(\d{3})(\d)/, "$1.$2").replace(/(\d{3})(\d)/, "$1.$2").replace(/(\d{3})(\d{1,2})$/, "$1-$2");

/* Desabilita o botão enquanto a API responde (evita clique duplo) */
async function ocupado(form, tarefa) {
  const btn = form.querySelector("[type=submit]");
  btn.disabled = true;
  try { return await tarefa(); } finally { btn.disabled = false; }
}

/* ---------- Alternar Entrar / Criar conta ---------- */
function trocarAuth(qual) {
  ["login", "cadastro"].forEach((n) => { $("#form-" + n).hidden = n !== qual; });
  $$(".auth-tabs button").forEach((b) => b.classList.toggle("active", b.dataset.auth === qual));
  $$("#tela-auth .form-erro").forEach((p) => { p.textContent = ""; });
}
$$(".auth-tabs button").forEach((b) => b.addEventListener("click", () => trocarAuth(b.dataset.auth)));
$("#c-cpf").addEventListener("input", (e) => { e.target.value = mascaraCpf(e.target.value); });

/* ---------- Sessão ---------- */
/* Cada perfil tem a sua tela: gestor e administrador vão para gestor.html e a
   equipe de campo para campo.html. O gestor pode ver a tela do cidadão pelo
   link "Visão do cidadão" (index.html?ver=cidadao). */
const TELA_DO_PERFIL = { COLABORADOR: "campo.html", GESTOR: "gestor.html", ADMIN: "gestor.html" };
const verComoCidadao = new URLSearchParams(location.search).get("ver") === "cidadao";

function mostrarApp(u) {
  const destino = TELA_DO_PERFIL[u.perfil];
  if (destino && !(verComoCidadao && u.perfil !== "COLABORADOR")) { location.replace(destino); return; }
  $("#tela-auth").hidden = true;
  $("#tela-app").hidden = false;
  iniciarApp(u);
}
function sair() {
  Api.sair();
  $("#tela-app").hidden = true;
  $("#tela-auth").hidden = false;
  $$("#tela-auth form").forEach((f) => f.reset());
  trocarAuth("login");
}
/* Chamado pelo api.js quando o token vence durante o uso */
function aoExpirarSessao() {
  sair();
  $("#l-erro").textContent = "Sua sessão expirou. Entre novamente.";
}
$("#btn-sair").addEventListener("click", sair);

/* ---------- Login (e-mail OU CPF) ---------- */
$("#form-login").addEventListener("submit", (e) => {
  e.preventDefault();
  ocupado(e.target, async () => {
    try {
      const u = await Api.entrar($("#l-id").value.trim(), $("#l-senha").value);
      $("#l-erro").textContent = "";
      mostrarApp(u);
    } catch (err) {
      $("#l-erro").textContent = err.message;   // mensagem genérica vem do servidor
    }
  });
});

/* ---------- Cadastro ---------- */
$("#form-cadastro").addEventListener("submit", (e) => {
  e.preventDefault();
  const erro = (m) => { $("#c-erro").textContent = m; };
  if ($("#c-senha").value !== $("#c-confirma").value) return erro("As senhas não conferem.");
  ocupado(e.target, async () => {
    try {
      const u = await Api.cadastrar({
        nome: $("#c-nome").value.trim(),
        cpf: $("#c-cpf").value,
        data_nascimento: $("#c-nasc").value || null,
        email: $("#c-email").value.trim(),
        senha: $("#c-senha").value,
      });
      e.target.reset();
      trocarAuth("login");
      $("#l-id").value = u.email;
      $("#l-senha").focus();
      toast("Conta criada! Faça login para continuar.");
    } catch (err) {
      erro(err.message);    // CPF inválido, menor de 18, CPF/e-mail já usados...
    }
  });
});

/* ---------- Inicialização: se já há sessão na aba, confere com o servidor ---------- */
(async () => {
  if (Api.temSessao()) {
    try { return mostrarApp(await Api.eu()); } catch { Api.sair(); }
  }
  $("#tela-auth").hidden = false;
})();
