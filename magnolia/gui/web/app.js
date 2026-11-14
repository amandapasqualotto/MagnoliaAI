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
  renderLibrary(s.biblioteca);
  $("#reminders").innerHTML = s.lembretes.length
    ? s.lembretes.map((r) => `<li><time>${r.quando}</time><span>${escapeHtml(r.texto)}</span></li>`).join("")
    : `<li class="empty">Nada marcado. Peça: “me lembra de beber água em 30 minutos”.</li>`;
}
setInterval(refreshPanels, 4000);

// ── Biblioteca e comandos ────────────────────────────────────────────
const KIND = { arquivo: "arquivo", pagina: "página", noticias: "notícias" };

function renderLibrary(lib) {
  const box = $("#library");
  if (!lib.itens.length) {
    box.innerHTML = `<p class="empty">Coloque aqui arquivos, links e sites de notícias para ela consultar.</p>`;
  } else {
    // Agrupa por coleção (um item pode aparecer em mais de uma)
    const groups = {};
    for (const item of lib.itens) {
      for (const c of item.colecoes.length ? item.colecoes : ["sem coleção"]) (groups[c] ??= []).push(item);
    }
    const order = Object.keys(groups).sort((a, b) => (a === "sem coleção") - (b === "sem coleção") || a.localeCompare(b));
    box.innerHTML = order.map((c) => `<div><h3>${escapeHtml(c)}</h3><ul class="list docs">${groups[c].map((i) => `
      <li><span title="${escapeHtml(i.origem)}">${escapeHtml(i.titulo)}<span class="kind">${KIND[i.tipo]}</span></span>
      <button data-remove-item="${i.id}" title="Remover ${escapeHtml(i.titulo)}" aria-label="Remover ${escapeHtml(i.titulo)}">×</button></li>`).join("")}
      </ul></div>`).join("");
  }
  $("#collectionList").innerHTML = lib.colecoes.map((c) => `<option value="${escapeHtml(c)}">`).join("");
  $("#commands").innerHTML = lib.comandos.length
    ? lib.comandos.map((c) => `<li><span title="${escapeHtml(c.instrucao)}">“${escapeHtml(c.nome)}”</span>
        <button data-remove-command="${escapeHtml(c.nome)}" aria-label="Apagar comando ${escapeHtml(c.nome)}">×</button></li>`).join("")
    : `<li class="empty">Crie no chat: “cria um comando resumo do dia que traz as notícias da coleção notícias”.</li>`;
}

$("#library").addEventListener("click", async (e) => {
  const id = e.target.dataset?.removeItem;
  if (id) renderLibrary(await api.remove_item(id));
});
$("#commands").addEventListener("click", async (e) => {
  const name = e.target.dataset?.removeCommand;
  if (name) renderLibrary(await api.remove_command(name));
});

$("#openAdd").addEventListener("click", () => {
  $("#linkForm").reset();
  $("#linkForm .error").textContent = "";
  $("#addDialog").showModal();
});
$("#closeAdd").addEventListener("click", () => $("#addDialog").close());
$("#pickFiles").addEventListener("click", () => $("#fileInput").click());

$("#fileInput").addEventListener("change", async (e) => {
  await addFiles(e.target.files);
  e.target.value = "";
});

async function addFiles(files) {
  const collections = $("#addCollections").value;
  const added = [], errors = [];
  for (const file of files) {
    toast(`Lendo ${file.name}...`);
    const r = await uploadFile(file, collections);
    added.push(...(r.adicionados ?? []));
    errors.push(...(r.erros ?? (r.erro ? [r.erro] : [])));
    if (r.biblioteca) renderLibrary(r.biblioteca);
  }
  if (added.length) { toast(`Adicionado: ${added.join(", ")}`); $("#addDialog").close(); }
  if (errors.length) toast(errors.join(" · "));
}

async function addLinks(text, kind = "auto") {
  toast("Lendo os links...");
  const r = await api.add_link(text, $("#addCollections").value, kind);
  if (!r.ok) return r;
  renderLibrary(r.biblioteca);
  $("#addDialog").close();
  toast(`Adicionado: ${r.itens.map((i) => i.titulo).join(", ")}` + (r.erros.length ? ` · Falhou: ${r.erros.join(" · ")}` : ""));
  return r;
}

// ── Arrastar e soltar (em qualquer lugar da janela) ──────────────────
function droppedLinks(dt) {
  const raw = dt.getData("text/uri-list") || dt.getData("text/plain") || "";
  return raw.split(/\s+/).filter((l) => /^https?:\/\//.test(l)).join("\n");
}

let dragDepth = 0;
window.addEventListener("dragenter", (e) => {
  if (!session) return;
  e.preventDefault();
  dragDepth++;
  $("#dropOverlay").hidden = false;
  $("#dropzone").classList.add("over");
});
window.addEventListener("dragover", (e) => e.preventDefault());
window.addEventListener("dragleave", () => {
  if (--dragDepth <= 0) { dragDepth = 0; $("#dropOverlay").hidden = true; $("#dropzone").classList.remove("over"); }
});
window.addEventListener("drop", async (e) => {
  e.preventDefault();
  dragDepth = 0;
  $("#dropOverlay").hidden = true;
  $("#dropzone").classList.remove("over");
  if (!session) return;
  if (e.dataTransfer.files.length) return addFiles(e.dataTransfer.files);
  const links = droppedLinks(e.dataTransfer);
  if (links) {
    const r = await addLinks(links);
    if (!r.ok) toast(r.erro);
  }
});

async function uploadFile(file, collections) {
  if (!TOKEN) return api.add_files([file.name], collections);  // demonstração
  const r = await fetch(`/anexar?nome=${encodeURIComponent(file.name)}&colecoes=${encodeURIComponent(collections)}`, {
    method: "POST", headers: { "X-Token": TOKEN }, body: file,
  });
  return r.json();
}

$("#linkForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = e.target;
  const button = $("#addLinkButton");
  button.disabled = true;
  button.textContent = "Lendo os links...";
  const r = await addLinks(f.url.value, f.tipo.value);
  button.disabled = false;
  button.textContent = "Adicionar links";
  if (!r.ok) f.querySelector(".error").textContent = r.erro;
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
  const lib = {
    itens: [
      { id: "1", tipo: "arquivo", titulo: "Cronograma 2º semestre", origem: "cronograma.pdf", colecoes: ["faculdade"] },
      { id: "2", tipo: "pagina", titulo: "Apostila de Direito Civil", origem: "docs.google.com", colecoes: ["direito", "faculdade"] },
      { id: "3", tipo: "noticias", titulo: "g1.globo.com", origem: "https://g1.globo.com", colecoes: ["notícias"] },
      { id: "4", tipo: "noticias", titulo: "migalhas.com.br", origem: "https://migalhas.com.br", colecoes: ["direito", "notícias"] },
    ],
    comandos: [{ nome: "resumo jurídico", instrucao: "Busque as novidades da coleção direito e resuma em 5 tópicos.", colecoes: ["direito"] }],
    colecoes: ["direito", "faculdade", "notícias"],
  };
  return {
    list_accounts: async () => ["amanda"],
    login: async () => info,
    create_account: async () => info,
    logout: async () => true,
    save_settings: async (f) => ({ ...info, config: { ...cfg, ...f } }),
    ask: async (t) => ({ ok: true, resposta: `(demonstração) Você disse: ${t}` }),
    start_voice: async () => { setTimeout(() => window.onMagnolia({ tipo: "estado", estado: "dormindo" }), 100); },
    stop_voice: async () => { window.onMagnolia({ tipo: "estado", estado: "parada" }); },
    status: async () => ({ cpu: 23, ram: 61, bateria: 84, biblioteca: lib, lembretes: [{ quando: "13/11 19:30", texto: "Revisar o portfólio" }] }),
    add_files: async () => ({ adicionados: [], erros: [], biblioteca: lib }),
    add_link: async () => ({ ok: false, erro: "(demonstração: abra pela Magnólia para adicionar links)" }),
    remove_item: async (id) => { lib.itens = lib.itens.filter((i) => i.id !== id); return lib; },
    remove_command: async (n) => { lib.comandos = lib.comandos.filter((c) => c.nome !== n); return lib; },
    google_connect: async () => ({ mensagem: "Conta Google conectada.", google: true }),
    google_disconnect: async () => ({ google: false }),
  };
}
