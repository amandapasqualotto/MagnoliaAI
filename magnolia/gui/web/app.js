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
  // Links viram clicáveis (o texto é escapado antes, para nada virar HTML sem querer)
  li.innerHTML = escapeHtml(text).replace(/https?:\/\/[^\s<)"']+/g,
    (url) => `<a href="${url}" class="chat-link">${url.length > 60 ? url.slice(0, 57) + "..." : url}</a>`);
  log.append(li);
  log.scrollTop = log.scrollHeight;
}

// Abre links no navegador padrão, onde a pessoa já está logada (e não dentro da janela da Magnólia)
document.addEventListener("click", (e) => {
  const link = e.target.closest("a[href^='http']");
  if (!link || !api) return;
  e.preventDefault();
  api.open_url(link.href);
});

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
  if (state === "parada" || state === "pensando") setLevel(0);
  renderVoiceButton();
}

// ── Animação da flor com a voz ──────────────────────────────────────
// O Python manda o volume ~15 vezes por segundo; aqui suavizamos a 60 quadros por
// segundo: a flor abre rápido quando alguém fala e fecha devagar no silêncio.
let levelTarget = 0, levelNow = 0;
function setLevel(value) {
  const shaped = Math.min(1, Math.sqrt(Math.max(0, value)) * 1.25);  // fala baixa também mexe
  levelTarget = value === 0 ? 0 : Math.max(levelTarget, shaped);
}
(function animateFlower() {
  levelNow += (levelTarget - levelNow) * (levelTarget > levelNow ? 0.35 : 0.12);
  levelTarget *= 0.9;
  document.documentElement.style.setProperty("--level", levelNow.toFixed(3));
  requestAnimationFrame(animateFlower);
})();

// ── Timers, cronômetro e som ─────────────────────────────────────────
let timerState = { timers: [], cronometro: null };
function renderTimers(state) {
  if (state) timerState = { timers: state.timers ?? [], cronometro: state.cronometro ?? null };
  const fmt = (s) => {
    s = Math.max(0, Math.round(s));
    const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
    return (h ? `${h}:${String(m).padStart(2, "0")}` : m) + ":" + String(sec).padStart(2, "0");
  };
  const now = Date.now() / 1000;
  const items = timerState.timers.map((t) => `
    <li class="${t.tipo}"><span class="name">${t.tipo === "alarme" ? "⏰ " : "⏱ "}${escapeHtml(t.nome)}</span>
    <span class="clock">${fmt(t.fim - now)}</span>
    <button data-cancel-timer="${t.id}" aria-label="Cancelar ${escapeHtml(t.nome)}">Cancelar</button></li>`);
  if (timerState.cronometro) {
    items.push(`<li class="stopwatch"><span class="name">Cronômetro</span>
      <span class="clock">${fmt(now - timerState.cronometro.inicio)}</span>
      <button data-stop-watch aria-label="Parar cronômetro">Parar</button></li>`);
  }
  const html = items.join("");
  if ($("#timers").innerHTML !== html) $("#timers").innerHTML = html;
}
setInterval(() => renderTimers(), 250);

$("#timers").addEventListener("click", async (e) => {
  if (e.target.dataset.cancelTimer) renderTimers(await api.cancel_timer(Number(e.target.dataset.cancelTimer)));
  if ("stopWatch" in e.target.dataset) renderTimers(await api.stop_stopwatch());
});

// Som do alarme (gerado na hora, sem arquivo de áudio): três notas de sino, repetidas
let audio;
// Qualquer clique "destrava" o som da janela (os navegadores exigem um gesto antes de tocar áudio)
document.addEventListener("click", () => { audio ??= new AudioContext(); audio.resume(); });
async function playChime(times = 3) {
  try {
    audio ??= new AudioContext();
    await Promise.race([audio.resume(), new Promise((r) => setTimeout(r, 300))]);
  } catch { /* sem áudio na janela */ }
  if (!audio || audio.state !== "running") {
    api?.beep?.();  // o navegador bloqueou: o Windows toca o alarme
    return;
  }
  const notes = [880, 1108.73, 1318.51];
  for (let r = 0; r < times; r++) {
    notes.forEach((freq, i) => {
      const start = audio.currentTime + r * 1.1 + i * 0.18;
      const osc = audio.createOscillator(), gain = audio.createGain();
      osc.type = "sine";
      osc.frequency.value = freq;
      gain.gain.setValueAtTime(0.0001, start);
      gain.gain.exponentialRampToValueAtTime(0.35, start + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.0001, start + 0.9);
      osc.connect(gain).connect(audio.destination);
      osc.start(start);
      osc.stop(start + 1);
    });
  }
}

function ringFlower() {
  const core = $("#core");
  core.classList.remove("ringing");
  void core.offsetWidth;  // reinicia a animação
  core.classList.add("ringing");
  setTimeout(() => core.classList.remove("ringing"), 3600);
}

// Eventos que chegam do Python
window.onMagnolia = (ev) => {
  switch (ev.tipo) {
    case "estado": setState(ev.estado); break;
    case "nivel": setLevel(ev.valor); break;
    case "texto": addMessage(ev.quem === "Você" ? "me" : "her", ev.texto); break;
    case "ferramenta": addMessage("tool", `usando ${ev.nome.replaceAll("_", " ")}`); break;
    case "alarme": playChime(); ringFlower(); toast(`${ev.categoria === "timer" ? "⏱" : "⏰"} ${ev.texto}`); refreshPanels(); break;
    case "timers": renderTimers(ev); break;
    case "acordou": playChime(1); break;
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
  if (s.timers) renderTimers(s.timers);
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
  f.estilo_voz.value = c.estilo_voz ?? "rapida";
  f.fone.checked = c.fone ?? false;
  f.cidade.value = c.cidade ?? "";
  f.chave.value = "";
  renderSpotify();
  renderGoogle();
  $("#settings").showModal();
});

$("#closeSettings").addEventListener("click", () => $("#settings").close());

$("#settingsForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = e.target;
  session = await api.save_settings({
    voz: f.voz.value, cidade: f.cidade.value, chave: f.chave.value,
    ei_magnolia: f.ei_magnolia.checked, fone: f.fone.checked, estilo_voz: f.estilo_voz.value,
  });
  $("#settings").close();
  setState("parada");
  toast("Configurações salvas");
});

function renderSpotify() {
  const on = session.spotify;
  $("#spotifySettingsText").textContent = on ? "Spotify Premium conectado" : "Spotify Premium não conectado";
  $("#spotifyButton").textContent = on ? "Desconectar" : "Conectar Spotify";
  $("#spotifyClientId").hidden = on;
  $("#spotifyClientId").value = session.config.spotify_client_id ?? "";
}

$("#spotifyButton").addEventListener("click", async () => {
  if (session.spotify) {
    session.spotify = (await api.spotify_disconnect()).spotify;
  } else {
    const clientId = $("#spotifyClientId").value.trim();
    if (!clientId) return toast("Cole o Client ID do seu app do Spotify primeiro.");
    toast("Abrindo o navegador para você autorizar no Spotify...");
    const r = await api.spotify_connect(clientId);
    session.spotify = r.spotify;
    session.config.spotify_client_id = clientId;
    toast(r.mensagem);
  }
  renderSpotify();
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
    status: async () => ({ cpu: 23, ram: 61, bateria: 84, biblioteca: lib, lembretes: [{ quando: "13/11 19:30", texto: "Revisar o portfólio" }],
      timers: { timers: [{ id: 1, nome: "Macarrão", tipo: "timer", fim: Date.now() / 1000 + 512 }], cronometro: null } }),
    cancel_timer: async () => ({ timers: [], cronometro: null }),
    beep: async () => true,
    stop_stopwatch: async () => ({ timers: [], cronometro: null }),
    add_files: async () => ({ adicionados: [], erros: [], biblioteca: lib }),
    add_link: async () => ({ ok: false, erro: "(demonstração: abra pela Magnólia para adicionar links)" }),
    remove_item: async (id) => { lib.itens = lib.itens.filter((i) => i.id !== id); return lib; },
    remove_command: async (n) => { lib.comandos = lib.comandos.filter((c) => c.nome !== n); return lib; },
    google_connect: async () => ({ mensagem: "Conta Google conectada.", google: true }),
    google_disconnect: async () => ({ google: false }),
    spotify_connect: async () => ({ mensagem: "(demonstração)", spotify: false }),
    spotify_disconnect: async () => ({ spotify: false }),
    open_url: async (u) => window.open(u, "_blank"),
  };
}
