#include <DNSServer.h>
#include <HTTPClient.h>
#include <Preferences.h>
#include <WebServer.h>
#include <WiFi.h>

// ---------- HARDWARE ----------
constexpr uint8_t SENSOR_PIN = 27;
constexpr uint8_t LED_STATUS_PIN = 2;
constexpr uint8_t BOTAO_CONFIG_PIN = 0;  // Botao BOOT da maioria dos ESP32.

// Ponto inicial comum para YF-S201. Calibre usando um volume conhecido.
constexpr float PULSOS_POR_LITRO = 450.0F;
constexpr uint32_t DEBOUNCE_PULSO_US = 1000;

// ---------- INTERVALOS ----------
constexpr uint32_t INTERVALO_CALCULO_MS = 1000;
constexpr uint32_t INTERVALO_ENVIO_MS = 10000;
constexpr uint32_t INTERVALO_RECONEXAO_MS = 10000;
constexpr uint32_t LIMITE_CONEXAO_INICIAL_MS = 45000;
constexpr uint32_t INTERVALO_SALVAR_MS = 60000;

// Rede temporaria criada pelo ESP32 durante a configuracao.
constexpr char SENHA_PORTAL[] = "pmca-2026";
constexpr uint16_t DNS_PORT = 53;

portMUX_TYPE pulseMux = portMUX_INITIALIZER_UNLOCKED;
volatile uint32_t pulsosPendentes = 0;
volatile uint32_t ultimoPulsoUs = 0;

Preferences preferences;
DNSServer dnsServer;
WebServer configServer(80);

String wifiSsid;
String wifiPassword;
String pmcaApiUrl;
String pmcaApiKey;
String nomePortal;

float fluxoLitrosMinuto = 0.0F;
float consumoTotalLitros = 0.0F;
float consumoNoUltimoSalvamento = 0.0F;

uint32_t ultimoCalculoMs = 0;
uint32_t ultimoEnvioMs = 0;
uint32_t ultimaReconexaoMs = 0;
uint32_t inicioConexaoMs = 0;
uint32_t ultimoSalvamentoMs = 0;
uint32_t reiniciarEmMs = 0;

bool portalAtivo = false;

void IRAM_ATTR registrarPulso() {
  const uint32_t agoraUs = micros();
  if (agoraUs - ultimoPulsoUs < DEBOUNCE_PULSO_US) {
    return;
  }

  portENTER_CRITICAL_ISR(&pulseMux);
  pulsosPendentes++;
  ultimoPulsoUs = agoraUs;
  portEXIT_CRITICAL_ISR(&pulseMux);
}

String escaparHtml(const String &texto) {
  String resultado = texto;
  resultado.replace("&", "&amp;");
  resultado.replace("\"", "&quot;");
  resultado.replace("<", "&lt;");
  resultado.replace(">", "&gt;");
  return resultado;
}

void carregarConfiguracao() {
  wifiSsid = preferences.getString("wifi_ssid", "");
  wifiPassword = preferences.getString("wifi_pass", "");
  pmcaApiUrl = preferences.getString("api_url", "");
  pmcaApiKey = preferences.getString("api_key", "");
}

bool configuracaoCompleta() {
  return !wifiSsid.isEmpty() && !wifiPassword.isEmpty() &&
         pmcaApiUrl.startsWith("http") && !pmcaApiKey.isEmpty();
}

String paginaConfiguracao(const String &mensagem = "") {
  String pagina;
  pagina.reserve(6000);
  pagina += F(R"HTML(
<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Configurar PMCA</title><style>
*{box-sizing:border-box}body{margin:0;min-height:100vh;display:grid;place-items:center;
font-family:system-ui,sans-serif;color:#102b3b;background:linear-gradient(145deg,#061b2c,#087b91)}
main{width:min(92%,460px);padding:30px;border-radius:22px;background:#fff;box-shadow:0 24px 70px #0018}
.mark{display:grid;place-items:center;width:48px;height:48px;border-radius:15px;background:#45d3d0;font-weight:900}
h1{margin:22px 0 8px;font-size:1.8rem}p{color:#617783;line-height:1.5}.message{padding:10px;border-radius:9px;background:#e5f8f5;color:#087060}
label{display:grid;gap:7px;margin:17px 0;font-size:.82rem;font-weight:750}input{width:100%;padding:13px;border:1px solid #d5e2e6;border-radius:10px;font:inherit}
button{width:100%;padding:13px;border:0;border-radius:10px;background:#0878a0;color:#fff;font:inherit;font-weight:800}
.reset{margin-top:12px;background:#fff;color:#a33;border:1px solid #ecd1d1}.hint{font-size:.76rem}
</style></head><body><main><div class="mark">PM</div><h1>Configurar monitor</h1>
<p>Informe os dados uma vez. Eles ficarão guardados na memória do ESP32.</p>
)HTML");

  if (!mensagem.isEmpty()) {
    pagina += "<p class=\"message\">" + escaparHtml(mensagem) + "</p>";
  }

  pagina += "<form method=\"post\" action=\"/salvar\">";
  pagina += "<label>Nome do Wi-Fi<input name=\"ssid\" maxlength=\"32\" required value=\"";
  pagina += escaparHtml(wifiSsid) + "\"></label>";
  pagina += F("<label>Senha do Wi-Fi<input name=\"wifi_password\" type=\"password\" maxlength=\"63\" placeholder=\"Deixe vazio para manter a atual\"></label>");
  pagina += "<label>Endereço da API<input name=\"api_url\" type=\"url\" required value=\"";
  pagina += escaparHtml(pmcaApiUrl) + "\" placeholder=\"http://192.168.1.10:8000/api/leitura\"></label>";
  pagina += F("<p class=\"hint\">Use o IPv4 do computador seguido de <b>:8000/api/leitura</b>.</p>");
  pagina += F("<label>API key<input name=\"api_key\" type=\"password\" placeholder=\"Deixe vazio para manter a atual\"></label>");
  pagina += F("<button type=\"submit\">Salvar e conectar</button></form>");
  pagina += F("<form method=\"post\" action=\"/apagar\"><button class=\"reset\" type=\"submit\">Apagar configuração</button></form>");
  pagina += F("</main></body></html>");
  return pagina;
}

void agendarReinicio() {
  reiniciarEmMs = millis() + 1500;
}

void salvarConfiguracaoPortal() {
  const String novoSsid = configServer.arg("ssid");
  const String novaSenhaWifi = configServer.arg("wifi_password");
  const String novaUrl = configServer.arg("api_url");
  const String novaApiKey = configServer.arg("api_key");

  if (novoSsid.isEmpty() || !novaUrl.startsWith("http")) {
    configServer.send(400, "text/html; charset=utf-8",
                      paginaConfiguracao("Preencha o Wi-Fi e um endereço válido."));
    return;
  }

  if (novaSenhaWifi.isEmpty() && wifiPassword.isEmpty()) {
    configServer.send(400, "text/html; charset=utf-8",
                      paginaConfiguracao("Informe a senha do Wi-Fi."));
    return;
  }

  if (novaApiKey.isEmpty() && pmcaApiKey.isEmpty()) {
    configServer.send(400, "text/html; charset=utf-8",
                      paginaConfiguracao("Informe a API key gerada no dashboard."));
    return;
  }

  preferences.putString("wifi_ssid", novoSsid);
  preferences.putString("api_url", novaUrl);
  if (!novaSenhaWifi.isEmpty()) {
    preferences.putString("wifi_pass", novaSenhaWifi);
  }
  if (!novaApiKey.isEmpty()) {
    preferences.putString("api_key", novaApiKey);
  }

  configServer.send(200, "text/html; charset=utf-8",
                    paginaConfiguracao("Dados salvos. O ESP32 vai reiniciar e conectar."));
  agendarReinicio();
}

void apagarConfiguracaoPortal() {
  preferences.remove("wifi_ssid");
  preferences.remove("wifi_pass");
  preferences.remove("api_url");
  preferences.remove("api_key");
  configServer.send(200, "text/html; charset=utf-8",
                    paginaConfiguracao("Configuração apagada. O ESP32 vai reiniciar."));
  agendarReinicio();
}

void iniciarPortalConfiguracao() {
  if (portalAtivo) {
    return;
  }

  portalAtivo = true;
  WiFi.disconnect(true);
  WiFi.mode(WIFI_AP);

  const uint64_t chipId = ESP.getEfuseMac();
  char sufixo[7];
  snprintf(sufixo, sizeof(sufixo), "%06llX", chipId & 0xFFFFFF);
  nomePortal = "PMCA-Setup-" + String(sufixo);

  WiFi.softAP(nomePortal.c_str(), SENHA_PORTAL);
  const IPAddress enderecoPortal = WiFi.softAPIP();
  dnsServer.start(DNS_PORT, "*", enderecoPortal);

  configServer.on("/", HTTP_GET, []() {
    configServer.send(200, "text/html; charset=utf-8", paginaConfiguracao());
  });
  configServer.on("/salvar", HTTP_POST, salvarConfiguracaoPortal);
  configServer.on("/apagar", HTTP_POST, apagarConfiguracaoPortal);
  configServer.onNotFound([]() {
    configServer.sendHeader("Location", "http://192.168.4.1/", true);
    configServer.send(302, "text/plain", "");
  });
  configServer.begin();

  Serial.println("\nMODO DE CONFIGURACAO");
  Serial.printf("1. Conecte o celular na rede: %s\n", nomePortal.c_str());
  Serial.printf("2. Senha da rede: %s\n", SENHA_PORTAL);
  Serial.println("3. Abra: http://192.168.4.1");
}

void processarPortal() {
  dnsServer.processNextRequest();
  configServer.handleClient();

  // Pisca rapidamente para indicar o modo de configuração.
  digitalWrite(LED_STATUS_PIN, (millis() / 300) % 2);

  if (reiniciarEmMs != 0 && static_cast<int32_t>(millis() - reiniciarEmMs) >= 0) {
    ESP.restart();
  }
}

void iniciarWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.persistent(false);
  WiFi.begin(wifiSsid.c_str(), wifiPassword.c_str());
  inicioConexaoMs = millis();
  ultimaReconexaoMs = millis();
  Serial.printf("Conectando ao Wi-Fi %s...\n", wifiSsid.c_str());
}

void manterWiFiConectado() {
  if (WiFi.status() == WL_CONNECTED) {
    digitalWrite(LED_STATUS_PIN, HIGH);
    return;
  }

  digitalWrite(LED_STATUS_PIN, LOW);
  const uint32_t agoraMs = millis();

  if (agoraMs - inicioConexaoMs >= LIMITE_CONEXAO_INICIAL_MS) {
    Serial.println("Wi-Fi indisponível. Abrindo configuração.");
    iniciarPortalConfiguracao();
    return;
  }

  if (agoraMs - ultimaReconexaoMs >= INTERVALO_RECONEXAO_MS) {
    Serial.println("Tentando reconectar ao Wi-Fi...");
    WiFi.disconnect();
    WiFi.begin(wifiSsid.c_str(), wifiPassword.c_str());
    ultimaReconexaoMs = agoraMs;
  }
}

uint32_t retirarPulsosPendentes() {
  portENTER_CRITICAL(&pulseMux);
  const uint32_t quantidade = pulsosPendentes;
  pulsosPendentes = 0;
  portEXIT_CRITICAL(&pulseMux);
  return quantidade;
}

void atualizarMedicao() {
  const uint32_t agoraMs = millis();
  const uint32_t tempoDecorridoMs = agoraMs - ultimoCalculoMs;
  if (tempoDecorridoMs < INTERVALO_CALCULO_MS) {
    return;
  }

  const uint32_t pulsos = retirarPulsosPendentes();
  const float litrosNoPeriodo = pulsos / PULSOS_POR_LITRO;
  const float minutosNoPeriodo = tempoDecorridoMs / 60000.0F;

  fluxoLitrosMinuto = litrosNoPeriodo / minutosNoPeriodo;
  consumoTotalLitros += litrosNoPeriodo;
  ultimoCalculoMs = agoraMs;

  Serial.printf("Pulsos: %lu | Vazao: %.3f L/min | Total: %.3f L\n",
                static_cast<unsigned long>(pulsos), fluxoLitrosMinuto,
                consumoTotalLitros);
}

bool enviarLeitura() {
  if (WiFi.status() != WL_CONNECTED) {
    return false;
  }

  WiFiClient client;
  HTTPClient http;
  if (!http.begin(client, pmcaApiUrl)) {
    Serial.println("Não foi possível preparar a conexão com o PMCA.");
    return false;
  }

  http.setConnectTimeout(4000);
  http.setTimeout(5000);
  http.addHeader("Content-Type", "application/json");
  http.addHeader("Authorization", String("Bearer ") + pmcaApiKey);

  char json[128];
  snprintf(json, sizeof(json),
           "{\"fluxo_litros\":%.3f,\"consumo_total\":%.3f}",
           fluxoLitrosMinuto, consumoTotalLitros);

  const int statusHttp =
      http.POST(reinterpret_cast<uint8_t *>(json), strlen(json));

  if (statusHttp >= 200 && statusHttp < 300) {
    Serial.printf("Leitura enviada. HTTP %d\n", statusHttp);
    http.end();
    return true;
  }

  if (statusHttp == 401) {
    Serial.println("API key inválida ou expirada. Abra o modo de configuração.");
  } else if (statusHttp == 403) {
    Serial.println("O usuário ligado à API key está desativado.");
  } else if (statusHttp > 0) {
    Serial.printf("PMCA recusou a leitura. HTTP %d: %s\n", statusHttp,
                  http.getString().c_str());
  } else {
    Serial.printf("Erro de rede: %s\n", http.errorToString(statusHttp).c_str());
  }

  http.end();
  return false;
}

void salvarConsumoSeNecessario() {
  const uint32_t agoraMs = millis();
  const bool passouIntervalo =
      agoraMs - ultimoSalvamentoMs >= INTERVALO_SALVAR_MS;
  const bool consumoMudou =
      consumoTotalLitros - consumoNoUltimoSalvamento >= 0.05F;

  if (!passouIntervalo || !consumoMudou) {
    return;
  }

  preferences.putFloat("consumo", consumoTotalLitros);
  consumoNoUltimoSalvamento = consumoTotalLitros;
  ultimoSalvamentoMs = agoraMs;
}

bool botaoConfiguracaoPressionado() {
  if (digitalRead(BOTAO_CONFIG_PIN) != LOW) {
    return false;
  }

  const uint32_t inicio = millis();
  while (digitalRead(BOTAO_CONFIG_PIN) == LOW) {
    if (millis() - inicio >= 2000) {
      return true;
    }
    delay(10);
  }
  return false;
}

void setup() {
  Serial.begin(115200);
  pinMode(SENSOR_PIN, INPUT_PULLUP);
  pinMode(LED_STATUS_PIN, OUTPUT);
  pinMode(BOTAO_CONFIG_PIN, INPUT_PULLUP);
  digitalWrite(LED_STATUS_PIN, LOW);

  preferences.begin("pmca", false);
  carregarConfiguracao();
  consumoTotalLitros = preferences.getFloat("consumo", 0.0F);
  consumoNoUltimoSalvamento = consumoTotalLitros;

  attachInterrupt(digitalPinToInterrupt(SENSOR_PIN), registrarPulso, FALLING);

  ultimoCalculoMs = millis();
  ultimoEnvioMs = millis();
  ultimoSalvamentoMs = millis();

  Serial.println("\nPMCA iniciado.");
  Serial.printf("Consumo recuperado: %.3f L\n", consumoTotalLitros);

  if (!configuracaoCompleta() || botaoConfiguracaoPressionado()) {
    iniciarPortalConfiguracao();
  } else {
    iniciarWiFi();
  }
}

void loop() {
  atualizarMedicao();
  salvarConsumoSeNecessario();

  if (portalAtivo) {
    processarPortal();
    delay(2);
    return;
  }

  manterWiFiConectado();
  if (portalAtivo) {
    return;
  }

  const uint32_t agoraMs = millis();
  if (agoraMs - ultimoEnvioMs >= INTERVALO_ENVIO_MS) {
    enviarLeitura();
    ultimoEnvioMs = agoraMs;
  }

  delay(5);
}
