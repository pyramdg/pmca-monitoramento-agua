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

constexpr uint8_t SENSOR_PIN=27, LED_PIN=2, CONFIG_PIN=0;
constexpr float PULSOS_POR_LITRO=450.0F;
constexpr uint32_t CALCULO_MS=1000, ENVIO_MS=10000, RECONEXAO_MS=10000;
constexpr uint32_t LIMITE_CONEXAO_MS=45000, SALVAR_MS=60000;
constexpr uint16_t MAX_FILA=500, DNS_PORT=53;
constexpr char SENHA_PORTAL[]="pmca-2026";

portMUX_TYPE mux=portMUX_INITIALIZER_UNLOCKED;
volatile uint32_t pulsos=0, ultimoPulsoUs=0;
Preferences prefs; DNSServer dns; WebServer web(80);
String ssid, senhaWifi, apiKey, nomePortal;
float fluxo=0, total=0, totalSalvo=0;
uint32_t ultimoCalculo=0, ultimoEnvio=0, ultimaReconexao=0, inicioConexao=0;
uint32_t ultimoSalvamento=0, reiniciarEm=0, sequencia=1, bootId=0;
bool portal=false, relogioSolicitado=false;

void IRAM_ATTR pulso(){uint32_t agora=micros();if(agora-ultimoPulsoUs<1000)return;portENTER_CRITICAL_ISR(&mux);pulsos++;ultimoPulsoUs=agora;portEXIT_CRITICAL_ISR(&mux);}

String htmlEscape(String s){s.replace("&","&amp;");s.replace("\"","&quot;");s.replace("<","&lt;");s.replace(">","&gt;");return s;}
bool configurado(){return !ssid.isEmpty()&&!senhaWifi.isEmpty()&&!apiKey.isEmpty();}

String pagina(const String &msg=""){
  String p; p.reserve(4500);
  p+=F(R"HTML(<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>PMCA</title><style>*{box-sizing:border-box}body{margin:0;min-height:100vh;display:grid;place-items:center;font-family:system-ui;color:#102b3b;background:linear-gradient(145deg,#061b2c,#087b91)}main{width:min(92%,460px);padding:30px;border-radius:22px;background:#fff;box-shadow:0 24px 70px #0018}.logo{display:grid;place-items:center;width:48px;height:48px;border-radius:15px;background:#45d3d0;font-weight:900}h1{margin:22px 0 8px}p{color:#617783;line-height:1.5}.msg{padding:10px;border-radius:9px;background:#e5f8f5;color:#087060}label{display:grid;gap:7px;margin:17px 0;font-size:.82rem;font-weight:750}input{width:100%;padding:13px;border:1px solid #d5e2e6;border-radius:10px;font:inherit}button{width:100%;padding:13px;border:0;border-radius:10px;background:#0878a0;color:#fff;font:inherit;font-weight:800}.apagar{margin-top:12px;background:#fff;color:#a33;border:1px solid #ecd1d1}.hint{font-size:.76rem}</style></head><body><main><div class="logo">PM</div><h1>Conectar o medidor</h1><p>Informe a rede deste local e a chave copiada do painel PMCA.</p>)HTML");
  if(!msg.isEmpty())p+="<p class=\"msg\">"+htmlEscape(msg)+"</p>";
  p+="<form method=\"post\" action=\"/salvar\"><label>Nome do Wi-Fi<input name=\"ssid\" required maxlength=\"32\" value=\""+htmlEscape(ssid)+"\"></label>";
  p+=F("<label>Senha do Wi-Fi<input type=\"password\" name=\"senha\" maxlength=\"63\" placeholder=\"Deixe vazio para manter a atual\"></label><label>API key do dispositivo<input type=\"password\" name=\"key\" placeholder=\"Deixe vazio para manter a atual\"></label><p class=\"hint\">A API key identifica o aparelho. O endereço do servidor já está gravado.</p><button>Salvar e conectar</button></form><form method=\"post\" action=\"/apagar\"><button class=\"apagar\">Apagar configuração</button></form></main></body></html>");return p;
}

void salvar(){String novoSsid=web.arg("ssid"),novaSenha=web.arg("senha"),novaKey=web.arg("key");if(novoSsid.isEmpty()||(novaSenha.isEmpty()&&senhaWifi.isEmpty())||(novaKey.isEmpty()&&apiKey.isEmpty())){web.send(400,"text/html; charset=utf-8",pagina("Preencha Wi-Fi, senha e API key."));return;}prefs.putString("ssid",novoSsid);if(!novaSenha.isEmpty())prefs.putString("senha",novaSenha);if(!novaKey.isEmpty())prefs.putString("key",novaKey);web.send(200,"text/html; charset=utf-8",pagina("Salvo. O aparelho vai conectar."));reiniciarEm=millis()+1500;}
void apagar(){prefs.remove("ssid");prefs.remove("senha");prefs.remove("key");web.send(200,"text/html; charset=utf-8",pagina("Configuração apagada. Reiniciando."));reiniciarEm=millis()+1500;}

void iniciarPortal(){if(portal)return;portal=true;WiFi.disconnect(true);WiFi.mode(WIFI_AP);char id[7];snprintf(id,sizeof(id),"%06llX",ESP.getEfuseMac()&0xFFFFFF);nomePortal="PMCA-Setup-"+String(id);WiFi.softAP(nomePortal.c_str(),SENHA_PORTAL);dns.start(DNS_PORT,"*",WiFi.softAPIP());web.on("/",HTTP_GET,[]{web.send(200,"text/html; charset=utf-8",pagina());});web.on("/salvar",HTTP_POST,salvar);web.on("/apagar",HTTP_POST,apagar);web.onNotFound([]{web.sendHeader("Location","http://192.168.4.1/",true);web.send(302,"text/plain","");});web.begin();Serial.printf("Conecte em %s, senha %s; abra http://192.168.4.1\n",nomePortal.c_str(),SENHA_PORTAL);}
void processarPortal(){dns.processNextRequest();web.handleClient();digitalWrite(LED_PIN,(millis()/300)%2);if(reiniciarEm&&static_cast<int32_t>(millis()-reiniciarEm)>=0)ESP.restart();}

void iniciarWiFi(){WiFi.mode(WIFI_STA);WiFi.setAutoReconnect(true);WiFi.persistent(false);WiFi.begin(ssid.c_str(),senhaWifi.c_str());inicioConexao=ultimaReconexao=millis();}
void manterWiFi(){if(WiFi.status()==WL_CONNECTED){digitalWrite(LED_PIN,HIGH);if(!relogioSolicitado){configTime(0,0,"pool.ntp.org","time.google.com");relogioSolicitado=true;}return;}digitalWrite(LED_PIN,LOW);if(millis()-inicioConexao>=LIMITE_CONEXAO_MS){iniciarPortal();return;}if(millis()-ultimaReconexao>=RECONEXAO_MS){WiFi.disconnect();WiFi.begin(ssid.c_str(),senhaWifi.c_str());ultimaReconexao=millis();}}

uint32_t retirarPulsos(){portENTER_CRITICAL(&mux);uint32_t n=pulsos;pulsos=0;portEXIT_CRITICAL(&mux);return n;}
void medir(){uint32_t agora=millis(),tempo=agora-ultimoCalculo;if(tempo<CALCULO_MS)return;float litros=retirarPulsos()/PULSOS_POR_LITRO;fluxo=litros/(tempo/60000.0F);total+=litros;ultimoCalculo=agora;}
String isoAgora(){time_t t=time(nullptr);if(t<1700000000)return "";struct tm utc;gmtime_r(&t,&utc);char b[25];strftime(b,sizeof(b),"%Y-%m-%dT%H:%M:%SZ",&utc);return String(b);}
String caminho(uint32_t n){char b[32];snprintf(b,sizeof(b),"/fila/%010lu.json",static_cast<unsigned long>(n));return String(b);}
uint16_t tamanhoFila(){uint16_t n=0;File d=LittleFS.open("/fila"),f=d.openNextFile();while(f){n++;f=d.openNextFile();}return n;}
String primeiro(){String a;File d=LittleFS.open("/fila"),f=d.openNextFile();while(f){String n=f.path();if(a.isEmpty()||n<a)a=n;f=d.openNextFile();}return a;}
void limitarFila(){while(tamanhoFila()>MAX_FILA){String a=primeiro();if(a.isEmpty())break;LittleFS.remove(a);}}

void guardar(){char evento[80];snprintf(evento,sizeof(evento),"%012llX-%lu-%lu",ESP.getEfuseMac(),static_cast<unsigned long>(bootId),static_cast<unsigned long>(sequencia));String j="{\"event_id\":\""+String(evento)+"\",\"fluxo_litros\":"+String(fluxo,3)+",\"consumo_total\":"+String(total,3);String hora=isoAgora();if(!hora.isEmpty())j+=",\"measured_at\":\""+hora+"\"";j+="}";File f=LittleFS.open(caminho(sequencia),FILE_WRITE);if(f){f.print(j);f.close();sequencia++;prefs.putUInt("seq",sequencia);limitarFila();}}
bool enviar(const String &nome){File f=LittleFS.open(nome,FILE_READ);if(!f)return false;String j=f.readString();f.close();WiFiClientSecure cliente;cliente.setCACert(PMCA_ROOT_CA);HTTPClient http;String url=String(PMCA_API_BASE_URL)+"/api/leitura";if(!http.begin(cliente,url))return false;http.setConnectTimeout(5000);http.setTimeout(8000);http.addHeader("Content-Type","application/json");http.addHeader("Authorization","Bearer "+apiKey);int status=http.POST(j);http.end();if(status>=200&&status<300){LittleFS.remove(nome);return true;}if(status==401||status==403)Serial.println("API key recusada; atualize-a no portal.");return false;}
void enviarFila(){if(WiFi.status()!=WL_CONNECTED)return;for(uint8_t i=0;i<3;i++){String a=primeiro();if(a.isEmpty()||!enviar(a))break;}}
void salvarTotal(){if(millis()-ultimoSalvamento<SALVAR_MS||total-totalSalvo<0.05F)return;prefs.putFloat("total",total);totalSalvo=total;ultimoSalvamento=millis();}
bool botaoPressionado(){if(digitalRead(CONFIG_PIN)!=LOW)return false;uint32_t inicio=millis();while(digitalRead(CONFIG_PIN)==LOW){if(millis()-inicio>=2000)return true;delay(10);}return false;}

void setup(){Serial.begin(115200);pinMode(SENSOR_PIN,INPUT_PULLUP);pinMode(LED_PIN,OUTPUT);pinMode(CONFIG_PIN,INPUT_PULLUP);prefs.begin("pmca",false);ssid=prefs.getString("ssid","");senhaWifi=prefs.getString("senha","");apiKey=prefs.getString("key","");sequencia=prefs.getUInt("seq",1);bootId=prefs.getUInt("boot",0)+1;prefs.putUInt("boot",bootId);LittleFS.begin(true);LittleFS.mkdir("/fila");total=prefs.getFloat("total",0);totalSalvo=total;attachInterrupt(digitalPinToInterrupt(SENSOR_PIN),pulso,FALLING);ultimoCalculo=ultimoEnvio=ultimoSalvamento=millis();if(!configurado()||botaoPressionado())iniciarPortal();else iniciarWiFi();}
void loop(){medir();salvarTotal();if(portal){processarPortal();delay(2);return;}manterWiFi();if(portal)return;if(millis()-ultimoEnvio>=ENVIO_MS){guardar();enviarFila();ultimoEnvio=millis();}delay(5);}
