const state = {
  mode: "login",
  accessToken: localStorage.getItem("pmca_access"),
  refreshToken: localStorage.getItem("pmca_refresh"),
  apiKey: null,
  readings: [],
};

const $ = (selector) => document.querySelector(selector);
const authView = $("#auth-view");
const dashboardView = $("#dashboard-view");
const formatNumber = (value) => Number(value || 0).toLocaleString("pt-BR", {minimumFractionDigits: 2, maximumFractionDigits: 2});

function parseUtc(value) {
  if (!value) return null;
  const text = String(value);
  return new Date(/(?:Z|[+-]\d{2}:\d{2})$/.test(text) ? text : `${text}Z`);
}

function formatElapsed(seconds) {
  if (seconds == null) return "Nunca";
  if (seconds < 10) return "Agora";
  if (seconds < 60) return `Há ${seconds} s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `Há ${minutes} min`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `Há ${hours} h`;
  return `Há ${Math.floor(hours / 24)} d`;
}

function renderDeviceStatus(summary) {
  const device = summary.dispositivo || {};
  const status = device.status || "aguardando";
  const labels = {
    online: "Online",
    offline: "Offline",
    aguardando: "Aguardando",
    nao_configurado: "Não configurado",
  };
  const messages = {
    online: "O ESP32 está ligado e enviando dados normalmente.",
    offline: `Sem contato ${formatElapsed(device.segundos_desde_comunicacao).toLowerCase()}. Confira a energia e o Wi-Fi do local.`,
    aguardando: "A chave existe, mas o ESP32 ainda não enviou a primeira leitura.",
    nao_configurado: "Gere uma API key e configure o ESP32 para começar.",
  };
  const waterLabels = {
    fluxo_detectado: "Água passando",
    sem_fluxo: "Sem fluxo agora",
    desconhecido: "Indisponível",
    sem_dados: "Sem dados",
  };

  const badge = $("#device-status");
  badge.className = `device-status ${status.replace("nao_configurado", "not-configured")}`;
  badge.querySelector("span").textContent = labels[status] || "Aguardando";
  $("#device-name").textContent = device.nome || "Meu medidor";
  $("#device-status-message").textContent = messages[status] || messages.aguardando;
  $("#today-readings").textContent = Number(summary.leituras_hoje || 0).toLocaleString("pt-BR");
  $("#water-state").textContent = waterLabels[device.situacao_agua] || "Sem dados";

  const lastSeen = $("#device-last-seen");
  lastSeen.textContent = formatElapsed(device.segundos_desde_comunicacao);
  const lastSeenDate = parseUtc(device.ultima_comunicacao);
  lastSeen.title = lastSeenDate ? lastSeenDate.toLocaleString("pt-BR") : "Nenhuma comunicação recebida";

  const alert = $("#device-alert");
  if (device.possivel_vazamento) {
    alert.textContent = `Possível vazamento: há fluxo contínuo há ${device.fluxo_continuo_minutos} min. Verifique torneiras, válvulas e tubulações.`;
    alert.className = "device-alert danger";
  } else if (status === "offline") {
    alert.textContent = "O painel continua mostrando o histórico salvo. Novas leituras aparecerão quando o aparelho reconectar.";
    alert.className = "device-alert warning";
  } else if (status === "aguardando" || status === "nao_configurado") {
    alert.textContent = status === "aguardando" ? "Finalize a configuração do Wi-Fi e da API key no portal do ESP32." : "O dispositivo ainda não está vinculado a esta conta.";
    alert.className = "device-alert info";
  } else {
    alert.className = "device-alert hidden";
    alert.textContent = "";
  }
}

async function request(path, options = {}, allowRefresh = true) {
  const headers = {"Content-Type": "application/json", ...(options.headers || {})};
  if (state.accessToken && !headers.Authorization) headers.Authorization = `Bearer ${state.accessToken}`;
  const response = await fetch(path, {...options, headers});
  if (response.status === 401 && allowRefresh && state.refreshToken) {
    const refreshed = await refreshSession();
    if (refreshed) return request(path, options, false);
  }
  const data = response.status === 204 ? null : await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data?.detail || "Não foi possível concluir a operação.");
  return data;
}

async function refreshSession() {
  try {
    const response = await fetch("/auth/refresh", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({refresh_token: state.refreshToken})});
    if (!response.ok) return false;
    const data = await response.json();
    state.accessToken = data.access_token;
    localStorage.setItem("pmca_access", data.access_token);
    return true;
  } catch { return false; }
}

function saveSession(data) {
  state.accessToken = data.access_token;
  state.refreshToken = data.refresh_token;
  localStorage.setItem("pmca_access", data.access_token);
  localStorage.setItem("pmca_refresh", data.refresh_token);
}

function clearSession() {
  state.accessToken = null; state.refreshToken = null; state.apiKey = null;
  localStorage.removeItem("pmca_access"); localStorage.removeItem("pmca_refresh");
}

function showAuth() { authView.classList.remove("hidden"); dashboardView.classList.add("hidden"); }
function showDashboard(user) {
  authView.classList.add("hidden"); dashboardView.classList.remove("hidden");
  $("#user-name").textContent = user.email.split("@")[0];
  loadDashboard();
}

document.querySelectorAll(".tab").forEach((button) => button.addEventListener("click", () => {
  state.mode = button.dataset.mode;
  document.querySelectorAll(".tab").forEach((tab) => tab.classList.toggle("active", tab === button));
  $("#auth-title").textContent = state.mode === "login" ? "Acesse seu painel" : "Crie seu acesso";
  $("#auth-subtitle").textContent = state.mode === "login" ? "Use seu e-mail e senha para continuar." : "Cadastre-se para começar a monitorar.";
  $("#auth-submit").textContent = state.mode === "login" ? "Entrar" : "Criar conta";
  $("#password").autocomplete = state.mode === "login" ? "current-password" : "new-password";
  $("#auth-error").textContent = "";
}));

$("#auth-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = $("#auth-submit"); const error = $("#auth-error");
  button.disabled = true; error.textContent = "";
  const body = {email: $("#email").value.trim(), password: $("#password").value};
  try {
    if (state.mode === "register") await request("/auth/register", {method: "POST", body: JSON.stringify(body)}, false);
    const data = await request("/auth/login", {method: "POST", body: JSON.stringify(body)}, false);
    saveSession(data); showDashboard(data.user);
  } catch (err) { error.textContent = err.message; }
  finally { button.disabled = false; }
});

async function loadDashboard() {
  try {
    const [summary, readings] = await Promise.all([request("/dashboard/resumo"), request("/dashboard/historico?dias=7")]);
    state.readings = readings;
    $("#total").textContent = `${formatNumber(summary.consumo_total)} L`;
    $("#today-total").textContent = `${formatNumber(summary.consumo_hoje)} L`;
    $("#month-total").textContent = `${formatNumber(summary.consumo_mes)} L`;
    $("#flow").textContent = `${formatNumber(summary.ultimo_fluxo)} L/min`;
    $("#last-update").textContent = summary.timestamp_ultima ? `Atualizado em ${parseUtc(summary.timestamp_ultima).toLocaleString("pt-BR")}` : "Sem leituras";
    $("#reading-count").textContent = `${readings.length} ${readings.length === 1 ? "leitura" : "leituras"}`;
    renderDeviceStatus(summary);
    drawChart(readings);
  } catch (err) {
    if (err.message.includes("Token") || err.message.includes("autentic")) { clearSession(); showAuth(); }
  }
}

function drawChart(readings) {
  const canvas = $("#chart"); const empty = $("#empty-chart");
  if (!readings.length) { empty.classList.remove("hidden"); canvas.classList.add("hidden"); return; }
  empty.classList.add("hidden"); canvas.classList.remove("hidden");
  const ratio = window.devicePixelRatio || 1; const rect = canvas.getBoundingClientRect();
  canvas.width = rect.width * ratio; canvas.height = rect.height * ratio;
  const ctx = canvas.getContext("2d"); ctx.scale(ratio, ratio);
  const width = rect.width, height = rect.height, pad = {t: 20, r: 16, b: 36, l: 48};
  const values = readings.map((item) => Math.max(0, Number(item.calculated_consumption ?? item.consumo_total) || 0));
  // Uma única leitura deve formar uma linha estável, não um triângulo até o
  // rodapé do gráfico. Repita apenas o ponto visual, sem alterar os dados.
  const plotValues = values.length === 1 ? [values[0], values[0]] : values;
  const maxValue = Math.max(...values);
  // Consumo nunca é negativo. Quando todas as leituras são zero, use uma escala
  // visual de 0 a 1 L em vez de produzir marcadores -0,3, -0,5 e -1,0 L.
  const chartMin = 0;
  const chartMax = maxValue > 0 ? maxValue * 1.1 : 1;
  const range = chartMax - chartMin;
  ctx.clearRect(0, 0, width, height); ctx.font = "12px system-ui"; ctx.fillStyle = "#82939d"; ctx.strokeStyle = "#e5edef"; ctx.lineWidth = 1;
  for (let i = 0; i <= 4; i++) { const y = pad.t + ((height - pad.t - pad.b) * i / 4); ctx.beginPath(); ctx.moveTo(pad.l, y); ctx.lineTo(width - pad.r, y); ctx.stroke(); const value = chartMax - range * i / 4; ctx.fillText(`${value.toFixed(1)} L`, 2, y + 4); }
  const point = (value, index) => ({x: pad.l + (width-pad.l-pad.r) * index / Math.max(plotValues.length-1,1), y: pad.t + (height-pad.t-pad.b) * (1-(value-chartMin)/range)});
  const gradient = ctx.createLinearGradient(0,pad.t,0,height-pad.b); gradient.addColorStop(0,"rgba(57,198,203,.32)"); gradient.addColorStop(1,"rgba(57,198,203,0)");
  ctx.beginPath(); plotValues.forEach((v,i) => { const p=point(v,i); i ? ctx.lineTo(p.x,p.y) : ctx.moveTo(p.x,p.y); }); ctx.lineTo(width-pad.r,height-pad.b); ctx.lineTo(pad.l,height-pad.b); ctx.closePath(); ctx.fillStyle=gradient; ctx.fill();
  ctx.beginPath(); plotValues.forEach((v,i) => { const p=point(v,i); i ? ctx.lineTo(p.x,p.y) : ctx.moveTo(p.x,p.y); }); ctx.strokeStyle="#0b819b"; ctx.lineWidth=3; ctx.lineJoin="round"; ctx.stroke();
  const first = parseUtc(readings[0].timestamp); const last = parseUtc(readings[readings.length-1].timestamp); ctx.fillStyle="#82939d"; ctx.fillText(first.toLocaleDateString("pt-BR"),pad.l,height-9); const label=last.toLocaleDateString("pt-BR"); ctx.fillText(label,width-pad.r-ctx.measureText(label).width,height-9);
}

$("#refresh").addEventListener("click", loadDashboard);
$("#logout").addEventListener("click", () => { clearSession(); showAuth(); });
$("#generate-key").addEventListener("click", async () => {
  const message = $("#device-message"); message.textContent = ""; message.classList.remove("error");
  try { const data = await request("/auth/api-key", {method:"POST"}); state.apiKey=data.api_key; $("#api-key").textContent=data.api_key; $("#key-box").classList.remove("hidden"); $("#test-reading").classList.remove("hidden"); message.textContent="Chave criada com sucesso."; await loadDashboard(); }
  catch(err){ message.textContent=err.message; message.classList.add("error"); }
});
$("#copy-key").addEventListener("click", async () => { await navigator.clipboard.writeText(state.apiKey || ""); $("#device-message").textContent="Chave copiada."; });
$("#reading-form").addEventListener("submit", async (event) => {
  event.preventDefault(); const message=$("#device-message");
  try { await request("/api/leitura", {method:"POST", headers:{Authorization:`Bearer ${state.apiKey}`}, body:JSON.stringify({fluxo_litros:Number($("#test-flow").value),consumo_total:Number($("#test-total").value)})}, false); message.textContent="Leitura recebida pelo sistema."; message.classList.remove("error"); await loadDashboard(); }
  catch(err){ message.textContent=err.message; message.classList.add("error"); }
});

window.addEventListener("resize", () => state.readings.length && drawChart(state.readings));
setInterval(() => !dashboardView.classList.contains("hidden") && loadDashboard(), 15000);

(async function start() {
  if (!state.accessToken) return showAuth();
  try { const user = await request("/auth/me"); showDashboard(user); }
  catch { clearSession(); showAuth(); }
})();
