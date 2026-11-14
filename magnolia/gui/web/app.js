// Lógica da tela da Magnólia.
// Fala com o Python pelo servidor local (server.py): api.<método>(...) vira POST /api/<método>,
// e os eventos ao vivo (voz, estado, lembretes) chegam em window.onMagnolia().

const $ = (sel) => document.querySelector(sel);
let api = null;          // a "ponte" com o Python
let session = null;      // dados da pessoa logada
let voiceOn = false;

const STATES = {
  parada: "",
  dormindo: "Diga “Ei, Magnólia”",
  ouvindo: "Estou ouvindo",
  pensando: "Um instante",
  falando: "",
};

// ── Início ───────────────────────────────────────────────────────────
const TOKEN = new URLSearchParams(location.search).get("t");

// Cria um objeto em que api.qualquerCoisa(a, b) faz POST /api/qualquerCoisa com [a, b]
function serverApi() {
  return new Proxy({}, {
    get: (_, method) => async (...args) => {
      const r = await fetch(`/api/${method}`, {
        method: "POST", headers: { "X-Token": TOKEN, "Content-Type": "application/json" },
        body: JSON.stringify(args),
      });
      return r.json();
    },
  });
}

function listenEvents() {
  const events = new EventSource(`/eventos?t=${TOKEN}`);
  events.onmessage = (e) => window.onMagnolia(JSON.parse(e.data));
}

if (location.protocol.startsWith("http") && TOKEN) {
  start(serverApi());
  listenEvents();
} else {
  start(demoApi());  // index.html aberto direto do disco: demonstração só para ver o visual
}

async function start(bridge) {
  if (api) return;
  api = bridge;
  const users = await api.list_accounts();
  $("#userList").innerHTML = users.map((u) => `<option value="${u}">`).join("");
  if (users.length === 0) showForm("register");
  else if (users.length === 1) {
    $("#loginForm [name=usuario]").value = users[0];
    $("#loginForm [name=senha]").focus();
  }
}

// ── Entrar / criar conta ─────────────────────────────────────────────
function showForm(which) {
  $("#loginForm").hidden = which !== "login";
  $("#registerForm").hidden = which !== "register";
  document.querySelector(`#${which}Form input`).focus();
}
document.querySelectorAll("[data-go]").forEach((b) => b.addEventListener("click", () => showForm(b.dataset.go)));

function formData(form) {
  return Object.fromEntries(new FormData(form).entries());
}

$("#loginForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = formData(e.target);
  enter(await api.login(f.usuario, f.senha), e.target);
});

$("#registerForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  enter(await api.create_account(formData(e.target)), e.target);
});

function enter(result, form) {
  if (!result.ok) {
    form.querySelector(".error").textContent = result.erro;
    return;
  }
  form.reset();
  session = result;
  $("#auth").hidden = true;
  $("#hud").hidden = false;
  $("#userName").textContent = session.nome;
  $("#log").innerHTML = `<li class="empty">Olá, ${escapeHtml(session.nome)}. Ligue a voz ou escreva aqui embaixo.</li>`;
  renderGoogle();
  setState("parada");
  refreshPanels();
}

// ── Conversa ─────────────────────────────────────────────────────────
function addMessage(kind, text) {
  const log = $("#log");
  log.querySelector(".empty")?.remove();
  const li = document.createElement("li");
  li.className = kind;
  li.textContent = text;
  log.append(li);
  log.scrollTop = log.scrollHeight;
}

$("#chatForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const input = $("#chatInput");
  const text = input.value.trim();
  if (!text) return;
  input.value = "";
  addMessage("me", text);
  if (!voiceOn) setState("pensando");
  const result = await api.ask(text);
  if (!voiceOn) setState("parada");
  if (!result.ok) addMessage("erro", result.erro);
  else if (result.resposta) addMessage("her", result.resposta);
});

// ── Voz ──────────────────────────────────────────────────────────────
$("#voiceToggle").addEventListener("click", async () => {
  if (voiceOn) {
    await api.stop_voice();
  } else {
    voiceOn = true;
    await api.start_voice();
  }
  renderVoiceButton();
});

function renderVoiceButton() {
  const b = $("#voiceToggle");
  b.classList.toggle("on", voiceOn);
  b.textContent = voiceOn ? "Desligar voz" : "Ligar voz";
}

function setState(state) {
  $("#core").dataset.state = state;
  $("#stateText").textContent = STATES[state] ?? "";
  if (state === "parada") voiceOn = false;
  if (state !== "falando" && state !== "ouvindo") setLevel(0);
  renderVoiceButton();
}

function setLevel(value) {
  document.documentElement.style.setProperty("--level", value);
}

// Eventos que chegam do Python
window.onMagnolia = (ev) => {
  switch (ev.tipo) {
    case "estado": setState(ev.estado); break;
    case "nivel": setLevel(ev.valor); break;
    case "texto": addMessage(ev.quem === "Você" ? "me" : "her", ev.texto); break;
    case "ferramenta": addMessage("tool", `usando ${ev.nome.replaceAll("_", " ")}`); break;
    case "lembrete": toast(`Lembrete: ${ev.texto}`); refreshPanels(); break;
    case "aviso": toast(ev.texto); break;
    case "erro": addMessage("erro", ev.texto); break;
  }
};

// ── Painéis da esquerda ──────────────────────────────────────────────
async function refreshPanels() {
  if (!session) return;
  const s = await api.status();
  for (const key of ["cpu", "ram", "bateria"]) {
    const g = document.querySelector(`.gauge[data-key="${key}"]`);
    const value = s[key];
    g.querySelector("b").textContent = value == null ? "–" : `${Math.round(value)}%`;
    g.querySelector(".fill").style.strokeDashoffset = 163.4 * (1 - (value ?? 0) / 100);
    g.classList.toggle("alert", key === "bateria" ? value != null && value < 20 : value > 85);
  }
  renderDocuments(s.documentos);
  $("#reminders").innerHTML = s.lembretes.length
    ? s.lembretes.map((r) => `<li><time>${r.quando}</time><span>${escapeHtml(r.texto)}</span></li>`).join("")
    : `<li class="empty">Nada marcado. Peça: “me lembra de beber água em 30 minutos”.</li>`;
}
setInterval(refreshPanels, 4000);

function renderDocuments(docs) {
  $("#documents").innerHTML = docs.length
    ? docs.map((d) => `<li><span title="${escapeHtml(d)}">${escapeHtml(d)}</span>
        <button data-remove="${escapeHtml(d)}" title="Remover ${escapeHtml(d)}" aria-label="Remover ${escapeHtml(d)}">×</button></li>`).join("")
    : `<li class="empty">Anexe PDFs ou documentos do Word, como seu cronograma, para ela consultar.</li>`;
}

$("#attachButton").addEventListener("click", () => $("#fileInput").click());

$("#fileInput").addEventListener("change", async (e) => {
  const added = [], errors = [];
  for (const file of e.target.files) {
    toast(`Lendo ${file.name}...`);
    const r = await uploadFile(file);
    added.push(...(r.anexados ?? []));
    errors.push(...(r.erros ?? (r.erro ? [r.erro] : [])));
    if (r.documentos) renderDocuments(r.documentos);
  }
  e.target.value = "";
  if (added.length) toast(`Anexado: ${added.join(", ")}`);
  if (errors.length) toast(errors.join(" · "));
});

async function uploadFile(file) {
  if (!TOKEN) return api.attach_documents([file.name]);  // demonstração
  const r = await fetch(`/anexar?nome=${encodeURIComponent(file.name)}`, {
    method: "POST", headers: { "X-Token": TOKEN }, body: file,
  });
  return r.json();
}

$("#documents").addEventListener("click", async (e) => {
  const name = e.target.dataset?.remove;
  if (name) renderDocuments(await api.remove_document(name));
});

function renderGoogle() {
  const on = session.google;
  $("#googleStatus").textContent = on
    ? "Conectado: Agenda, Planilhas, Docs, Drive e Gmail."
    : "Não conectado. Conecte nas configurações para usar Agenda, Planilhas, Docs e Gmail.";
  $("#googleSettingsText").textContent = on ? "Conta Google conectada" : "Conta Google não conectada";
  $("#googleButton").textContent = on ? "Desconectar" : "Conectar Google";
}

// ── Relógio ──────────────────────────────────────────────────────────
function tick() {
  const now = new Date();
  $("#clock").textContent = now.toLocaleDateString("pt-BR", { weekday: "long", day: "numeric", month: "long" })
    + ", " + now.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}
tick();
setInterval(tick, 10000);

// ── Configurações ────────────────────────────────────────────────────
$("#openSettings").addEventListener("click", () => {
  const c = session.config;
  const f = $("#settingsForm");
  $("#voices").innerHTML = Object.entries(session.vozes).map(([name, desc]) => `
    <label><input type="radio" name="voz" value="${name}" ${c.voz === name ? "checked" : ""}>
    <span>${name}<em>${desc}</em></span></label>`).join("");
  f.ei_magnolia.checked = c.ei_magnolia ?? true;
  f.fone.checked = c.fone ?? false;
  f.cidade.value = c.cidade ?? "";
  f.chave.value = "";
  renderGoogle();
  $("#settings").showModal();
});

$("#closeSettings").addEventListener("click", () => $("#settings").close());

$("#settingsForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = e.target;
  session = await api.save_settings({
    voz: f.voz.value, cidade: f.cidade.value, chave: f.chave.value,
    ei_magnolia: f.ei_magnolia.checked, fone: f.fone.checked,
  });
  $("#settings").close();
  setState("parada");
  toast("Configurações salvas");
});

$("#googleButton").addEventListener("click", async () => {
  if (session.google) {
    session.google = (await api.google_disconnect()).google;
  } else {
    toast("Abrindo o navegador para você entrar na conta Google...");
    const r = await api.google_connect();
    session.google = r.google;
    toast(r.mensagem);
  }
  renderGoogle();
});

$("#logout").addEventListener("click", async () => {
  await api.logout();
  $("#settings").close();
  session = null;
  $("#hud").hidden = true;
  $("#auth").hidden = false;
  showForm("login");
});

// ── Utilidades ───────────────────────────────────────────────────────
let toastTimer;
function toast(text) {
  const t = $("#toast");
  t.textContent = text;
  t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (t.hidden = true), 4500);
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// Demonstração para abrir o index.html no navegador e ver o visual, sem Python.
function demoApi() {
  const cfg = { voz: "Kore", cidade: "Campo Grande", ei_magnolia: true, fone: false };
  const vozes = { Kore: "firme e confiante", Aoede: "leve e tranquila", Leda: "jovem", Zephyr: "animada", Sulafat: "acolhedora", Despina: "suave" };
  const info = { ok: true, nome: "Amanda", usuario: "amanda", config: cfg, google: true, vozes };
  let docs = ["Cronograma 2º semestre"];
  return {
    list_accounts: async () => ["amanda"],
    login: async () => info,
    create_account: async () => info,
    logout: async () => true,
    save_settings: async (f) => ({ ...info, config: { ...cfg, ...f } }),
    ask: async (t) => ({ ok: true, resposta: `(demonstração) Você disse: ${t}` }),
    start_voice: async () => { setTimeout(() => window.onMagnolia({ tipo: "estado", estado: "dormindo" }), 100); },
    stop_voice: async () => { window.onMagnolia({ tipo: "estado", estado: "parada" }); },
    status: async () => ({ cpu: 23, ram: 61, bateria: 84, documentos: docs, lembretes: [{ quando: "13/11 19:30", texto: "Revisar o portfólio" }] }),
    attach_documents: async () => { docs = [...docs, "Apostila Direito Civil"]; return { anexados: ["Apostila Direito Civil"], erros: [], documentos: docs }; },
    remove_document: async (d) => (docs = docs.filter((x) => x !== d)),
    google_connect: async () => ({ mensagem: "Conta Google conectada.", google: true }),
    google_disconnect: async () => ({ google: false }),
  };
}
