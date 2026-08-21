#include <DNSServer.h>
#include <HTTPClient.h>
#include <LittleFS.h>
#include <Preferences.h>
#include <WebServer.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <time.h>

// Certificado público usado para validar o HTTPS do servidor PMCA.
// Ele fica dentro deste arquivo para o sketch funcionar com uma única aba.
static const char PMCA_ROOT_CA[] PROGMEM = R"CERT(
-----BEGIN CERTIFICATE-----
MIIFazCCA1OgAwIBAgIRAIIQz7DSQONZRGPgu2OCiwAwDQYJKoZIhvcNAQELBQAw
TzELMAkGA1UEBhMCVVMxKTAnBgNVBAoTIEludGVybmV0IFNlY3VyaXR5IFJlc2Vh
cmNoIEdyb3VwMRUwEwYDVQQDEwxJU1JHIFJvb3QgWDEwHhcNMTUwNjA0MTEwNDM4
WhcNMzUwNjA0MTEwNDM4WjBPMQswCQYDVQQGEwJVUzEpMCcGA1UEChMgSW50ZXJu
ZXQgU2VjdXJpdHkgUmVzZWFyY2ggR3JvdXAxFTATBgNVBAMTDElTUkcgUm9vdCBY
MTCCAiIwDQYJKoZIhvcNAQEBBQADggIPADCCAgoCggIBAK3oJHP0FDfzm54rVygc
h77ct984kIxuPOZXoHj3dcKi/vVqbvYATyjb3miGbESTtrFj/RQSa78f0uoxmyF+
0TM8ukj13Xnfs7j/EvEhmkvBioZxaUpmZmyPfjxwv60pIgbz5MDmgK7iS4+3mX6U
A5/TR5d8mUgjU+g4rk8Kb4Mu0UlXjIB0ttov0DiNewNwIRt18jA8+o+u3dpjq+sW
T8KOEUt+zwvo/7V3LvSye0rgTBIlDHCNAymg4VMk7BPZ7hm/ELNKjD+Jo2FR3qyH
B5T0Y3HsLuJvW5iB4YlcNHlsdu87kGJ55tukmi8mxdAQ4Q7e2RCOFvu396j3x+UC
B5iPNgiV5+I3lg02dZ77DnKxHZu8A/lJBdiB3QW0KtZB6awBdpUKD9jf1b0SHzUv
KBds0pjBqAlkd25HN7rOrFleaJ1/ctaJxQZBKT5ZPt0m9STJEadao0xAH0ahmbWn
OlFuhjuefXKnEgV4We0+UXgVCwOPjdAvBbI+e0ocS3MFEvzG6uBQE3xDk3SzynTn
jh8BCNAw1FtxNrQHusEwMFxIt4I7mKZ9YIqioymCzLq9gwQbooMDQaHWBfEbwrbw
qHyGO0aoSCqI3Haadr8faqU9GY/rOPNk3sgrDQoo//fb4hVC1CLQJ13hef4Y53CI
rU7m2Ys6xt0nUW7/vGT1M0NPAgMBAAGjQjBAMA4GA1UdDwEB/wQEAwIBBjAPBgNV
HRMBAf8EBTADAQH/MB0GA1UdDgQWBBR5tFnme7bl5AFzgAiIyBpY9umbbjANBgkq
hkiG9w0BAQsFAAOCAgEAVR9YqbyyqFDQDLHYGmkgJykIrGF1XIpu+ILlaS/V9lZL
ubhzEFnTIZd+50xx+7LSYK05qAvqFyFWhfFQDlnrzuBZ6brJFe+GnY+EgPbk6ZGQ
3BebYhtF8GaV0nxvwuo77x/Py9auJ/GpsMiu/X1+mvoiBOv/2X/qkSsisRcOj/KK
NFtY2PwByVS5uCbMiogziUwthDyC3+6WVwW6LLv3xLfHTjuCvjHIInNzktHCgKQ5
ORAzI4JMPJ+GslWYHb4phowim57iaztXOoJwTdwJx4nLCgdNbOhdjsnvzqvHu7Ur
TkXWStAmzOVyyghqpZXjFaH3pO3JLF+l+/+sKAIuvtd7u+Nxe5AW0wdeRlN8NwdC
jNPElpzVmbUq4JUagEiuTDkHzsxHpFKVK7q4+63SM1N95R1NbdWhscdCb+ZAJzVc
oyi3B43njTOQ5yOf+1CceWxG1bQVs5ZufpsMljq4Ui0/1lvh+wjChP4kqKOJ2qxq
4RgqsahDYVvTH9w7jXbyLeiNdd8XM2w9U/t7y0Ff/9yi0GE44Za4rF2LN9d11TPA
mRGunUHBcnWEvgJBQl9nJEiU0Zsnvgc/ubhPgXRR4Xq37Z0j4r7g1SgEEzwxA57d
emyPxgcYxn/eR44/KJ4EBs+lVDR3veyJm+kXQ99b21/+jh5Xos1AnX5iItreGCc=
-----END CERTIFICATE-----
)CERT";

// Alterado uma única vez após o deploy. No uso diário não é preciso digitar URL.
#ifndef PMCA_API_BASE_URL
#define PMCA_API_BASE_URL "https://pmca-monitoramento-agua-production.up.railway.app"
#endif

// Podem ser alterados em Sketch > Exportar binário compilado com flags de build,
// sem precisar procurar valores espalhados pelo código.
#ifndef PMCA_SENSOR_PIN
#define PMCA_SENSOR_PIN 15
#endif

#ifndef PMCA_PULSOS_POR_LITRO
#define PMCA_PULSOS_POR_LITRO 450.0F
#endif

namespace Config {
constexpr uint8_t SENSOR_PIN = PMCA_SENSOR_PIN;
constexpr uint8_t LED_PIN = 2;
constexpr uint8_t CONFIG_PIN = 0;  // Botão BOOT da maioria das placas ESP32.

constexpr float PULSOS_POR_LITRO = PMCA_PULSOS_POR_LITRO;
constexpr uint32_t FILTRO_PULSO_US = 1000;
constexpr uint32_t CALCULO_MS = 1000;
constexpr uint32_t REGISTRO_LEITURA_MS = 10000;
constexpr uint32_t PROCESSAR_FILA_MS = 1000;
constexpr uint32_t STATUS_MS = 5000;
constexpr uint32_t RECONEXAO_MS = 10000;
constexpr uint32_t LIMITE_CONEXAO_MS = 45000;
constexpr uint32_t SALVAR_TOTAL_MS = 60000;
constexpr uint32_t BOTAO_CONFIG_MS = 2000;
constexpr uint16_t MAX_FILA = 500;
constexpr uint16_t DNS_PORT = 53;

constexpr char SENHA_PORTAL[] = "pmca-2026";
constexpr char DIRETORIO_FILA[] = "/fila";
}  // namespace Config

portMUX_TYPE muxPulsos = portMUX_INITIALIZER_UNLOCKED;
volatile uint32_t pulsosPendentes = 0;
volatile uint32_t ultimoPulsoUs = 0;
volatile uint32_t transicoesSensor = 0;
volatile uint8_t ultimoNivelSensor = HIGH;

Preferences preferencias;
DNSServer servidorDns;
WebServer servidorWeb(80);

String wifiSsid;
String wifiSenha;
String apiKey;
String nomePortal;

float vazaoLitrosMin = 0.0F;
float consumoTotal = 0.0F;
float totalSalvo = 0.0F;
uint32_t pulsosUltimoCalculo = 0;

uint32_t ultimoCalculoMs = 0;
uint32_t ultimoRegistroLeituraMs = 0;
uint32_t ultimaTentativaFilaMs = 0;
uint32_t ultimoStatusMs = 0;
uint32_t ultimaReconexaoMs = 0;
uint32_t inicioFalhaWifiMs = 0;
uint32_t ultimoSalvamentoMs = 0;
uint32_t ultimoAvisoSensorMs = 0;
uint32_t reiniciarEmMs = 0;
uint32_t inicioBotaoMs = 0;
uint32_t sequenciaLeitura = 1;
uint32_t idInicializacao = 0;

bool portalAtivo = false;
bool botaoConfigTratado = false;
bool wifiEstavaConectado = false;
bool relogioSolicitado = false;
bool armazenamentoDisponivel = false;

void abrirPortalConfiguracao(const char *motivo);

void IRAM_ATTR registrarPulso() {
  const uint32_t agoraUs = micros();
  const uint8_t nivelAtual = digitalRead(Config::SENSOR_PIN);

  portENTER_CRITICAL_ISR(&muxPulsos);
  transicoesSensor++;
  ultimoNivelSensor = nivelAtual;
  // Uma volta elétrica possui uma borda de descida e uma de subida. Contamos
  // somente a descida para não duplicar o volume medido.
  if (nivelAtual == LOW && agoraUs - ultimoPulsoUs >= Config::FILTRO_PULSO_US) {
    pulsosPendentes++;
    ultimoPulsoUs = agoraUs;
  }
  portEXIT_CRITICAL_ISR(&muxPulsos);
}

uint32_t retirarPulsos() {
  portENTER_CRITICAL(&muxPulsos);
  const uint32_t quantidade = pulsosPendentes;
  pulsosPendentes = 0;
  portEXIT_CRITICAL(&muxPulsos);
  return quantidade;
}

String escaparHtml(String valor) {
  valor.replace("&", "&amp;");
  valor.replace("\"", "&quot;");
  valor.replace("<", "&lt;");
  valor.replace(">", "&gt;");
  return valor;
}

bool possuiConfiguracao() {
  // Senha vazia é válida para redes Wi-Fi abertas.
  return !wifiSsid.isEmpty() && !apiKey.isEmpty();
}

String montarPaginaPortal(const String &mensagem = "") {
  String pagina;
  pagina.reserve(5600);
  pagina += F(R"HTML(<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Configurar PMCA</title><style>*{box-sizing:border-box}body{margin:0;min-height:100vh;display:grid;place-items:center;padding:20px;font-family:system-ui;color:#102b3b;background:linear-gradient(145deg,#061b2c,#087b91)}main{width:min(100%,460px);padding:30px;border-radius:22px;background:#fff;box-shadow:0 24px 70px #0018}.logo{display:grid;place-items:center;width:48px;height:48px;border-radius:15px;background:#45d3d0;font-weight:900}h1{margin:22px 0 8px}p{color:#617783;line-height:1.5}.msg{padding:11px;border-radius:9px;background:#e5f8f5;color:#087060}.erro{background:#fcecec;color:#9b1c1c}label{display:grid;gap:7px;margin:17px 0;font-size:.82rem;font-weight:750}.linha{display:flex;align-items:center;gap:9px}.linha input{width:auto}input{width:100%;padding:13px;border:1px solid #d5e2e6;border-radius:10px;font:inherit}button{width:100%;padding:13px;border:0;border-radius:10px;background:#0878a0;color:#fff;font:inherit;font-weight:800}.apagar{margin-top:12px;background:#fff;color:#a33;border:1px solid #ecd1d1}.hint{font-size:.78rem}</style></head><body><main><div class="logo">PM</div><h1>Configurar o medidor</h1><p>Informe o Wi-Fi deste local e a chave copiada do painel PMCA.</p>)HTML");

  if (!mensagem.isEmpty()) {
    pagina += "<p class=\"msg\">" + escaparHtml(mensagem) + "</p>";
  }

  pagina += "<form method=\"post\" action=\"/salvar\">";
  pagina += "<label>Nome do Wi-Fi<input name=\"ssid\" required maxlength=\"32\" value=\"";
  pagina += escaparHtml(wifiSsid);
  pagina += "\"></label>";
  pagina += F(R"HTML(<label>Senha do Wi-Fi<input type="password" name="senha" maxlength="63" placeholder="Deixe vazio para manter a atual"></label><label class="linha"><input type="checkbox" name="aberta" value="1">Esta rede não possui senha</label><label>API key do dispositivo<input type="password" name="key" autocomplete="off" placeholder="Cole a nova chave ou deixe vazio para manter"></label><p class="hint">Ao gerar outra API key no painel, a chave anterior deixa de funcionar. O endereço do servidor já está gravado no aparelho.</p><button>Salvar e conectar</button></form><form method="post" action="/apagar"><button class="apagar">Apagar Wi-Fi e API key</button></form></main></body></html>)HTML");
  return pagina;
}

void responderPortal() {
  servidorWeb.send(200, "text/html; charset=utf-8", montarPaginaPortal());
}

void redirecionarParaPortal() {
  servidorWeb.sendHeader("Location", "http://192.168.4.1/", true);
  servidorWeb.send(302, "text/plain", "");
}

void salvarConfiguracaoPortal() {
  String novoSsid = servidorWeb.arg("ssid");
  String novaSenha = servidorWeb.arg("senha");
  String novaApiKey = servidorWeb.arg("key");
  novaApiKey.trim();  // Remove espaços ou quebras de linha copiados junto da chave.

  const bool redeAberta = servidorWeb.hasArg("aberta");
  const bool ssidMudou = novoSsid != wifiSsid;

  if (novoSsid.isEmpty()) {
    servidorWeb.send(400, "text/html; charset=utf-8", montarPaginaPortal("Informe o nome do Wi-Fi."));
    return;
  }

  if (ssidMudou && novaSenha.isEmpty() && !redeAberta) {
    servidorWeb.send(400, "text/html; charset=utf-8", montarPaginaPortal("Informe a senha da nova rede ou marque que ela é aberta."));
    return;
  }

  if (novaApiKey.isEmpty() && apiKey.isEmpty()) {
    servidorWeb.send(400, "text/html; charset=utf-8", montarPaginaPortal("Informe a API key criada no painel PMCA."));
    return;
  }

  if (!novaApiKey.isEmpty() && novaApiKey.length() < 20) {
    servidorWeb.send(400, "text/html; charset=utf-8", montarPaginaPortal("A API key parece incompleta. Copie a chave inteira do painel."));
    return;
  }

  wifiSsid = novoSsid;
  preferencias.putString("ssid", wifiSsid);

  if (redeAberta) {
    wifiSenha = "";
    preferencias.putString("senha", wifiSenha);
  } else if (!novaSenha.isEmpty()) {
    wifiSenha = novaSenha;
    preferencias.putString("senha", wifiSenha);
  }

  if (!novaApiKey.isEmpty()) {
    apiKey = novaApiKey;
    preferencias.putString("key", apiKey);
  }

  servidorWeb.send(200, "text/html; charset=utf-8", montarPaginaPortal("Configuração salva. O aparelho vai reiniciar e conectar."));
  reiniciarEmMs = millis() + 1800;
}

void apagarConfiguracaoPortal() {
  preferencias.remove("ssid");
  preferencias.remove("senha");
  preferencias.remove("key");
  wifiSsid = "";
  wifiSenha = "";
  apiKey = "";
  servidorWeb.send(200, "text/html; charset=utf-8", montarPaginaPortal("Wi-Fi e API key apagados. Reiniciando."));
  reiniciarEmMs = millis() + 1800;
}

void abrirPortalConfiguracao(const char *motivo) {
  if (portalAtivo) {
    return;
  }

  portalAtivo = true;
  wifiEstavaConectado = false;
  digitalWrite(Config::LED_PIN, LOW);

  WiFi.disconnect(true);
  delay(100);
  WiFi.mode(WIFI_AP);

  char identificador[7];
  snprintf(
      identificador,
      sizeof(identificador),
      "%06llX",
      static_cast<unsigned long long>(ESP.getEfuseMac() & 0xFFFFFF));
  nomePortal = "PMCA-Setup-" + String(identificador);

  if (!WiFi.softAP(nomePortal.c_str(), Config::SENHA_PORTAL)) {
    Serial.println("ERRO: não foi possível criar a rede de configuração.");
    return;
  }

  servidorDns.start(Config::DNS_PORT, "*", WiFi.softAPIP());
  servidorWeb.on("/", HTTP_GET, responderPortal);
  servidorWeb.on("/salvar", HTTP_POST, salvarConfiguracaoPortal);
  servidorWeb.on("/apagar", HTTP_POST, apagarConfiguracaoPortal);
  servidorWeb.on("/generate_204", HTTP_GET, redirecionarParaPortal);
  servidorWeb.on("/hotspot-detect.html", HTTP_GET, redirecionarParaPortal);
  servidorWeb.on("/connecttest.txt", HTTP_GET, redirecionarParaPortal);
  servidorWeb.on("/ncsi.txt", HTTP_GET, redirecionarParaPortal);
  servidorWeb.onNotFound(redirecionarParaPortal);
  servidorWeb.begin();

  Serial.println();
  Serial.printf("Portal aberto: %s\n", motivo);
  Serial.printf("Rede: %s\n", nomePortal.c_str());
  Serial.printf("Senha: %s\n", Config::SENHA_PORTAL);
  Serial.println("Abra: http://192.168.4.1");
}

void processarPortal() {
  servidorDns.processNextRequest();
  servidorWeb.handleClient();
  digitalWrite(Config::LED_PIN, (millis() / 300) % 2);

  if (reiniciarEmMs != 0 && static_cast<int32_t>(millis() - reiniciarEmMs) >= 0) {
    ESP.restart();
  }
}

void processarBotaoConfiguracao() {
  if (digitalRead(Config::CONFIG_PIN) == LOW) {
    if (inicioBotaoMs == 0) {
      inicioBotaoMs = millis();
    }

    if (!botaoConfigTratado && millis() - inicioBotaoMs >= Config::BOTAO_CONFIG_MS) {
      botaoConfigTratado = true;
      abrirPortalConfiguracao("botão BOOT pressionado por 2 segundos");
    }
    return;
  }

  inicioBotaoMs = 0;
  botaoConfigTratado = false;
}

void iniciarWifi() {
  WiFi.mode(WIFI_STA);
  WiFi.persistent(false);
  WiFi.setAutoReconnect(true);
  WiFi.begin(wifiSsid.c_str(), wifiSenha.c_str());

  const uint32_t agora = millis();
  inicioFalhaWifiMs = agora;
  ultimaReconexaoMs = agora;
  wifiEstavaConectado = false;
  Serial.printf("Conectando ao Wi-Fi: %s\n", wifiSsid.c_str());
}

void manterWifi() {
  const uint32_t agora = millis();

  if (WiFi.status() == WL_CONNECTED) {
    digitalWrite(Config::LED_PIN, HIGH);

    if (!wifiEstavaConectado) {
      wifiEstavaConectado = true;
      Serial.printf("Wi-Fi conectado. IP: %s\n", WiFi.localIP().toString().c_str());
    }

    if (!relogioSolicitado) {
      configTime(0, 0, "pool.ntp.org", "time.google.com");
      relogioSolicitado = true;
    }
    return;
  }

  digitalWrite(Config::LED_PIN, LOW);

  if (wifiEstavaConectado) {
    wifiEstavaConectado = false;
    inicioFalhaWifiMs = agora;
    Serial.println("Wi-Fi desconectado. Tentando reconectar.");
  }

  if (agora - inicioFalhaWifiMs >= Config::LIMITE_CONEXAO_MS) {
    abrirPortalConfiguracao("Wi-Fi indisponível por 45 segundos");
    return;
  }

  if (agora - ultimaReconexaoMs >= Config::RECONEXAO_MS) {
    WiFi.disconnect();
    WiFi.begin(wifiSsid.c_str(), wifiSenha.c_str());
    ultimaReconexaoMs = agora;
  }
}

void atualizarMedicao() {
  const uint32_t agora = millis();
  const uint32_t intervalo = agora - ultimoCalculoMs;
  if (intervalo < Config::CALCULO_MS) {
    return;
  }

  pulsosUltimoCalculo = retirarPulsos();
  const float litros = pulsosUltimoCalculo / Config::PULSOS_POR_LITRO;
  vazaoLitrosMin = litros / (intervalo / 60000.0F);
  consumoTotal += litros;
  ultimoCalculoMs = agora;
}

String horarioIsoAtual() {
  const time_t agora = time(nullptr);
  if (agora < 1700000000) {
    return "";
  }

  struct tm utc;
  gmtime_r(&agora, &utc);
  char buffer[25];
  strftime(buffer, sizeof(buffer), "%Y-%m-%dT%H:%M:%SZ", &utc);
  return String(buffer);
}

String caminhoLeitura(uint32_t sequencia) {
  char caminho[32];
  snprintf(caminho, sizeof(caminho), "/fila/%010lu.json", static_cast<unsigned long>(sequencia));
  return String(caminho);
}

uint16_t contarArquivosFila() {
  if (!armazenamentoDisponivel) {
    return 0;
  }

  uint16_t quantidade = 0;
  File diretorio = LittleFS.open(Config::DIRETORIO_FILA);
  if (!diretorio) {
    return 0;
  }

  File arquivo = diretorio.openNextFile();
  while (arquivo) {
    quantidade++;
    arquivo.close();
    arquivo = diretorio.openNextFile();
  }
  diretorio.close();
  return quantidade;
}

String primeiroArquivoFila() {
  if (!armazenamentoDisponivel) {
    return "";
  }

  String primeiro;
  File diretorio = LittleFS.open(Config::DIRETORIO_FILA);
  if (!diretorio) {
    return "";
  }

  File arquivo = diretorio.openNextFile();
  while (arquivo) {
    const String caminho = arquivo.path();
    if (primeiro.isEmpty() || caminho < primeiro) {
      primeiro = caminho;
    }
    arquivo.close();
    arquivo = diretorio.openNextFile();
  }
  diretorio.close();
  return primeiro;
}

void limitarFila() {
  while (contarArquivosFila() > Config::MAX_FILA) {
    const String primeiro = primeiroArquivoFila();
    if (primeiro.isEmpty() || !LittleFS.remove(primeiro)) {
      break;
    }
  }
}

void guardarLeituraNaFila() {
  if (!armazenamentoDisponivel) {
    Serial.println("ERRO: leitura não salva porque o LittleFS está indisponível.");
    return;
  }

  char evento[80];
  snprintf(
      evento,
      sizeof(evento),
      "%012llX-%lu-%lu",
      static_cast<unsigned long long>(ESP.getEfuseMac()),
      static_cast<unsigned long>(idInicializacao),
      static_cast<unsigned long>(sequenciaLeitura));

  String json;
  json.reserve(180);
  json = "{\"event_id\":\"" + String(evento) + "\",\"fluxo_litros\":";
  json += String(vazaoLitrosMin, 3);
  json += ",\"consumo_total\":" + String(consumoTotal, 3);

  const String horario = horarioIsoAtual();
  if (!horario.isEmpty()) {
    json += ",\"measured_at\":\"" + horario + "\"";
  }
  json += "}";

  const String caminho = caminhoLeitura(sequenciaLeitura);
  File arquivo = LittleFS.open(caminho, FILE_WRITE);
  if (!arquivo) {
    Serial.println("ERRO: não foi possível criar um item na fila.");
    return;
  }

  arquivo.print(json);
  arquivo.close();
  sequenciaLeitura++;
  preferencias.putUInt("seq", sequenciaLeitura);
  limitarFila();
}

bool enviarArquivoDaFila(const String &caminho) {
  File arquivo = LittleFS.open(caminho, FILE_READ);
  if (!arquivo) {
    return false;
  }

  const String json = arquivo.readString();
  arquivo.close();

  WiFiClientSecure cliente;
  cliente.setCACert(PMCA_ROOT_CA);

  HTTPClient http;
  const String url = String(PMCA_API_BASE_URL) + "/api/leitura";
  if (!http.begin(cliente, url)) {
    Serial.println("ERRO: não foi possível iniciar a conexão HTTPS.");
    return false;
  }

  http.setConnectTimeout(5000);
  http.setTimeout(8000);
  http.addHeader("Content-Type", "application/json");
  http.addHeader("Authorization", "Bearer " + apiKey);

  const int statusHttp = http.POST(json);
  http.end();

  if (statusHttp >= 200 && statusHttp < 300) {
    LittleFS.remove(caminho);
    return true;
  }

  if (statusHttp == 401 || statusHttp == 403) {
    Serial.printf("API key recusada pelo servidor (HTTP %d).\n", statusHttp);
    abrirPortalConfiguracao("API key recusada; informe a nova chave");
    return false;
  }

  // Erros 4xx abaixo são permanentes para este arquivo e bloqueariam toda a fila.
  if (statusHttp == 400 || statusHttp == 404 || statusHttp == 413 || statusHttp == 422) {
    Serial.printf("Leitura descartada por erro permanente HTTP %d.\n", statusHttp);
    LittleFS.remove(caminho);
    return true;
  }

  if (statusHttp < 0) {
    Serial.printf("Falha de conexão: %s\n", HTTPClient::errorToString(statusHttp).c_str());
  } else {
    Serial.printf("Servidor respondeu HTTP %d; a leitura continuará na fila.\n", statusHttp);
  }
  return false;
}

void enviarProximoDaFila() {
  if (!armazenamentoDisponivel || WiFi.status() != WL_CONNECTED || portalAtivo) {
    return;
  }

  // Um único POST por passagem evita bloquear medição, status e reconexão por
  // três requisições HTTPS consecutivas. Enquanto houver atraso, esta função é
  // chamada novamente a cada segundo e a fila é drenada continuamente.
  const String primeiro = primeiroArquivoFila();
  if (!primeiro.isEmpty()) {
    enviarArquivoDaFila(primeiro);
  }
}

void salvarConsumoTotal() {
  const uint32_t agora = millis();
  if (agora - ultimoSalvamentoMs < Config::SALVAR_TOTAL_MS) {
    return;
  }

  if (consumoTotal - totalSalvo >= 0.05F) {
    preferencias.putFloat("total", consumoTotal);
    totalSalvo = consumoTotal;
  }
  ultimoSalvamentoMs = agora;
}

void imprimirStatus() {
  const uint32_t agora = millis();
  if (agora - ultimoStatusMs < Config::STATUS_MS) {
    return;
  }

  const char *estadoWifi = WiFi.status() == WL_CONNECTED ? "conectado" : "desconectado";
  uint32_t totalTransicoes;
  uint8_t nivelSensor;
  portENTER_CRITICAL(&muxPulsos);
  totalTransicoes = transicoesSensor;
  nivelSensor = ultimoNivelSensor;
  portEXIT_CRITICAL(&muxPulsos);

  Serial.printf(
      "Pulsos: %lu | Vazão: %.3f L/min | Total: %.3f L | Wi-Fi: %s | Fila: %u | GPIO %u: %s | Transições: %lu\n",
      static_cast<unsigned long>(pulsosUltimoCalculo),
      vazaoLitrosMin,
      consumoTotal,
      estadoWifi,
      contarArquivosFila(),
      Config::SENSOR_PIN,
      nivelSensor == HIGH ? "ALTO" : "BAIXO",
      static_cast<unsigned long>(totalTransicoes));

  if (agora >= 15000 && totalTransicoes == 0 &&
      agora - ultimoAvisoSensorMs >= 30000) {
    Serial.printf(
        "AVISO: nenhum sinal chegou ao GPIO %u. Confira o fio de sinal, o GND comum e a alimentação do sensor.\n",
        Config::SENSOR_PIN);
    ultimoAvisoSensorMs = agora;
  }
  ultimoStatusMs = agora;
}

void setup() {
  Serial.begin(115200);
  delay(250);

  pinMode(Config::SENSOR_PIN, INPUT_PULLUP);
  pinMode(Config::LED_PIN, OUTPUT);
  pinMode(Config::CONFIG_PIN, INPUT_PULLUP);
  digitalWrite(Config::LED_PIN, LOW);

  preferencias.begin("pmca", false);
  wifiSsid = preferencias.getString("ssid", "");
  wifiSenha = preferencias.getString("senha", "");
  apiKey = preferencias.getString("key", "");
  sequenciaLeitura = preferencias.getUInt("seq", 1);
  idInicializacao = preferencias.getUInt("boot", 0) + 1;
  preferencias.putUInt("boot", idInicializacao);

  armazenamentoDisponivel = LittleFS.begin(true);
  if (armazenamentoDisponivel) {
    LittleFS.mkdir(Config::DIRETORIO_FILA);
  } else {
    Serial.println("ERRO: LittleFS indisponível; leituras offline não serão salvas.");
  }

  consumoTotal = preferencias.getFloat("total", 0.0F);
  totalSalvo = consumoTotal;

  ultimoNivelSensor = digitalRead(Config::SENSOR_PIN);
  attachInterrupt(digitalPinToInterrupt(Config::SENSOR_PIN), registrarPulso, CHANGE);

  const uint32_t agora = millis();
  ultimoCalculoMs = agora;
  ultimoRegistroLeituraMs = agora;
  ultimaTentativaFilaMs = agora;
  ultimoStatusMs = agora;
  ultimoSalvamentoMs = agora;

  Serial.println();
  Serial.println("PMCA iniciado.");
  Serial.printf(
      "Sensor configurado no GPIO %u com %.1f pulsos por litro. Estado inicial: %s.\n",
      Config::SENSOR_PIN,
      Config::PULSOS_POR_LITRO,
      ultimoNivelSensor == HIGH ? "ALTO" : "BAIXO");
  Serial.println("Para reconfigurar, segure o botão BOOT por 2 segundos com o aparelho ligado.");

  if (possuiConfiguracao()) {
    iniciarWifi();
  } else {
    abrirPortalConfiguracao("Wi-Fi ou API key ainda não configurados");
  }
}

void loop() {
  atualizarMedicao();
  salvarConsumoTotal();
  imprimirStatus();

  if (portalAtivo) {
    processarPortal();
    delay(2);
    return;
  }

  processarBotaoConfiguracao();
  if (portalAtivo) {
    return;
  }

  manterWifi();
  if (portalAtivo) {
    return;
  }

  const uint32_t agora = millis();
  if (agora - ultimoRegistroLeituraMs >= Config::REGISTRO_LEITURA_MS) {
    guardarLeituraNaFila();
    ultimoRegistroLeituraMs = agora;
  }

  if (agora - ultimaTentativaFilaMs >= Config::PROCESSAR_FILA_MS) {
    enviarProximoDaFila();
    // Use o horário após o POST, pois a conexão HTTPS pode levar alguns segundos.
    ultimaTentativaFilaMs = millis();
  }

  delay(5);
}
