/* ==========================================================
   auth.js · Login, cadastro, validações e sessão
   Depende de: db.js, app.js ($, $$, toast, iniciarApp)
   ========================================================== */
const IDADE_MINIMA = 18;            // regra de negócio: só maiores de idade criam conta
const SESSAO = "urbani_sessao";     // sessionStorage: guarda apenas o ID do usuário

/* ---------- Utilitários ---------- */
const soDigitos = (s) => String(s).replace(/\D/g, "");
const mascaraCpf = (s) => soDigitos(s).slice(0, 11)
  .replace(/(\d{3})(\d)/, "$1.$2").replace(/(\d{3})(\d)/, "$1.$2").replace(/(\d{3})(\d{1,2})$/, "$1-$2");

/* SHA-256 com salt (Web Crypto). O back-end real usará bcrypt. */
async function hashSenha(senha, salt) {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(salt + senha));
  return Array.from(new Uint8Array(buf), (b) => b.toString(16).padStart(2, "0")).join("");
}

/* CPF: checa os 2 dígitos verificadores */
function cpfValido(c) {
  c = soDigitos(c);
  if (c.length !== 11 || /^(\d)\1+$/.test(c)) return false;
  for (let t = 9; t < 11; t++) {
    let s = 0;
    for (let i = 0; i < t; i++) s += c[i] * (t + 1 - i);
    if (((s * 10) % 11) % 10 != c[t]) return false;
  }
  return true;
}

/* Idade em anos completos (considera se o aniversário já passou) */
function idade(iso) {
  const n = new Date(iso + "T00:00"), h = new Date();
  let i = h.getFullYear() - n.getFullYear();
  const m = h.getMonth() - n.getMonth();
  if (m < 0 || (m === 0 && h.getDate() < n.getDate())) i--;
  return i;
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
function mostrarApp(u) {
  try { sessionStorage.setItem(SESSAO, u.id); } catch { /* sem persistência de sessão */ }
  $("#tela-auth").hidden = true;
  $("#tela-app").hidden = false;
  iniciarApp(u);
}
function sair() {
  try { sessionStorage.removeItem(SESSAO); } catch { /* ignora */ }
  $("#tela-app").hidden = true;
  $("#tela-auth").hidden = false;
  $$("#tela-auth form").forEach((f) => f.reset());
  trocarAuth("login");
}
$("#btn-sair").addEventListener("click", sair);

/* ---------- Login (e-mail OU CPF) ---------- */
$("#form-login").addEventListener("submit", async (e) => {
  e.preventDefault();
  const id = $("#l-id").value.trim().toLowerCase(), dig = soDigitos(id);
  const u = Banco.usuarios().find((x) => id.includes("@") ? x.email.toLowerCase() === id : dig && soDigitos(x.cpf) === dig);
  const ok = u && u.ativo && (await hashSenha($("#l-senha").value, u.salt)) === u.senha_hash;
  if (!ok) { $("#l-erro").textContent = "E-mail/CPF ou senha incorretos."; return; }  // mensagem genérica de propósito
  mostrarApp(u);
});

/* ---------- Cadastro ---------- */
$("#form-cadastro").addEventListener("submit", async (e) => {
  e.preventDefault();
  const erro = (m) => { $("#c-erro").textContent = m; };
  const v = (s) => $(s).value.trim();
  const nome = v("#c-nome"), cpf = soDigitos(v("#c-cpf")), nasc = $("#c-nasc").value;
  const email = v("#c-email").toLowerCase(), senha = $("#c-senha").value;

  if (nome.split(/\s+/).length < 2) return erro("Informe nome e sobrenome.");
  if (!cpfValido(cpf)) return erro("CPF inválido.");
  if (!nasc || isNaN(new Date(nasc)) || idade(nasc) < 0 || idade(nasc) > 120) return erro("Data de nascimento inválida.");
  // Barreira de idade: recusa ANTES de gravar qualquer dado
  if (idade(nasc) < IDADE_MINIMA) return erro(`É preciso ter ${IDADE_MINIMA} anos ou mais para criar uma conta.`);
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(email)) return erro("E-mail inválido.");
  if (senha.length < 6) return erro("A senha precisa ter no mínimo 6 caracteres.");
  if (senha !== $("#c-confirma").value) return erro("As senhas não conferem.");
  const todos = Banco.usuarios();
  if (todos.some((u) => soDigitos(u.cpf) === cpf)) return erro("Este CPF já está cadastrado.");
  if (todos.some((u) => u.email.toLowerCase() === email)) return erro("Este e-mail já está cadastrado.");

  const salt = Array.from(crypto.getRandomValues(new Uint8Array(8)), (b) => b.toString(16).padStart(2, "0")).join("");
  Banco.salvarUsuario({
    id: Math.max(...todos.map((u) => u.id)) + 1, nome, cpf: mascaraCpf(cpf), data_nascimento: nasc,
    email, salt, senha_hash: await hashSenha(senha, salt), perfil: "CIDADAO", ativo: true,
    cidade: "", bairro: "", criado_em: new Date().toISOString()
  });
  e.target.reset();
  trocarAuth("login");
  $("#l-id").value = email;
  $("#l-senha").focus();
  toast("Conta criada! Faça login para continuar.");
});

/* ---------- Inicialização: carrega o banco e decide a tela ---------- */
Banco.carregar().then(() => {
  let id = 0;
  try { id = Number(sessionStorage.getItem(SESSAO)); } catch { /* sem sessão */ }
  const u = id && Banco.usuarios().find((x) => x.id === id);
  if (u) mostrarApp(u); else $("#tela-auth").hidden = false;
});