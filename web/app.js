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
    $("#flow").textContent = `${formatNumber(summary.ultimo_fluxo)} L/min`;
    $("#average").textContent = `${formatNumber(summary.media_hoje)} L/min`;
    $("#last-update").textContent = summary.timestamp_ultima ? `Atualizado em ${new Date(summary.timestamp_ultima + "Z").toLocaleString("pt-BR")}` : "Sem leituras";
    $("#reading-count").textContent = `${readings.length} ${readings.length === 1 ? "leitura" : "leituras"}`;
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
  const values = readings.map((item) => item.consumo_total); const min = Math.min(...values); const max = Math.max(...values); const range = Math.max(max - min, 1);
  ctx.clearRect(0, 0, width, height); ctx.font = "12px system-ui"; ctx.fillStyle = "#82939d"; ctx.strokeStyle = "#e5edef"; ctx.lineWidth = 1;
  for (let i = 0; i <= 4; i++) { const y = pad.t + ((height - pad.t - pad.b) * i / 4); ctx.beginPath(); ctx.moveTo(pad.l, y); ctx.lineTo(width - pad.r, y); ctx.stroke(); const value = max - range * i / 4; ctx.fillText(`${value.toFixed(1)} L`, 2, y + 4); }
  const point = (value, index) => ({x: pad.l + (width-pad.l-pad.r) * index / Math.max(readings.length-1,1), y: pad.t + (height-pad.t-pad.b) * (1-(value-min)/range)});
  const gradient = ctx.createLinearGradient(0,pad.t,0,height-pad.b); gradient.addColorStop(0,"rgba(57,198,203,.32)"); gradient.addColorStop(1,"rgba(57,198,203,0)");
  ctx.beginPath(); values.forEach((v,i) => { const p=point(v,i); i ? ctx.lineTo(p.x,p.y) : ctx.moveTo(p.x,p.y); }); ctx.lineTo(width-pad.r,height-pad.b); ctx.lineTo(pad.l,height-pad.b); ctx.closePath(); ctx.fillStyle=gradient; ctx.fill();
  ctx.beginPath(); values.forEach((v,i) => { const p=point(v,i); i ? ctx.lineTo(p.x,p.y) : ctx.moveTo(p.x,p.y); }); ctx.strokeStyle="#0b819b"; ctx.lineWidth=3; ctx.lineJoin="round"; ctx.stroke();
  const first = new Date(readings[0].timestamp + "Z"); const last = new Date(readings[readings.length-1].timestamp + "Z"); ctx.fillStyle="#82939d"; ctx.fillText(first.toLocaleDateString("pt-BR"),pad.l,height-9); const label=last.toLocaleDateString("pt-BR"); ctx.fillText(label,width-pad.r-ctx.measureText(label).width,height-9);
}

$("#refresh").addEventListener("click", loadDashboard);
$("#logout").addEventListener("click", () => { clearSession(); showAuth(); });
$("#generate-key").addEventListener("click", async () => {
  const message = $("#device-message"); message.textContent = ""; message.classList.remove("error");
  try { const data = await request("/auth/api-key", {method:"POST"}); state.apiKey=data.api_key; $("#api-key").textContent=data.api_key; $("#key-box").classList.remove("hidden"); $("#test-reading").classList.remove("hidden"); message.textContent="Chave criada com sucesso."; }
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
