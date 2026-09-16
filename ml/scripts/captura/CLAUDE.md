# CityRain — Jetson Nano (nó de borda)

TCC de Rodrigo (Engenharia/Ciência da Computação, IMT), orientador Prof. Gabriel de Souza Lima.
CityRain classifica intensidade de chuva urbana a partir de imagens de câmera veicular — camada
complementar (não substitui pluviômetro), com diferencial de densidade espacial via H3, cruzando
dados com CGE-SP, INMET e CEMADEN. Equipe: Rodrigo (hardware/edge — este equipamento), Guilherme
Mattioli (backend), Gabriel Moreno e Paulo Vespero (frontend).

Este documento é o estado **verificado** da Jetson, levantamento inicial em 2026-07-21 com
atualizações em 2026-07-29. Antes de assumir qualquer coisa aqui como ainda verdadeira, reconfira —
sistemas de campo mudam de estado a cada boot/deploy.

## ⚠️ Não existe repositório git

Não há `.git` em nenhum lugar sob `/home/jetson`. O "projeto" hoje é um conjunto de scripts soltos
em `~/scripts/` mais duas pastas de imagens capturadas. Se o código "de verdade" (com histórico,
backend, frontend) vive em outra máquina/repositório remoto, vale confirmar com Rodrigo antes de
tratar este diretório como fonte única de verdade — por ora este arquivo trata só do que roda
*nesta* Jetson.

## Hardware

- NVIDIA Jetson Nano Developer Kit (board Yahboom), SoC **tegra210** (t210ref), 4GB RAM (3.9G
  visíveis, ~1.1G livres com o desktop já de pé — ver seção Boot/Desktop abaixo)
- Boot atual a partir de **`/dev/sda1`** (SSD/disco USB, 59.5G, clone padrão NVIDIA do eMMC), não
  do cartão. O eMMC original (`mmcblk0p1`, 14G) continua montado em `/media/jetson/EMMC` como
  resíduo do processo de clonagem — não é usado em runtime, mas ocupa espaço físico/lógico.
- Câmera USB Logitech C270 (nominal) — **ver discrepância abaixo, não estava enumerando no momento
  do levantamento**
- GPS u-blox NEO-6M (GY-GPS6MV2) via UART do header de 40 pinos
- Botão físico de shutdown via GPIO (pino BOARD 13)
- Sem RTC com bateria: `/dev/rtc0` existe mas `hwclock -r` falha
  ("Cannot access the Hardware Clock via any known method") — confirma que não há RTC persistente
  utilizável.

## Sistema operacional

- L4T R32.7.6 (JetPack 4.x), `uname -r` = 4.9.299-tegra
- Ubuntu 18.04.6 LTS (Bionic) — **repositórios antigos, Python 3.6.9 como padrão** (`/usr/bin/python3`),
  Python 2.7.17 também presente. `pip` é a versão 9.0.1 (bem antiga) — esperar dor de cabeça com
  wheels pré-compilados para aarch64 mais recentes (torch, onnxruntime etc. nas próximas semanas).
- Boot default é **`graphical.target`** com autologin habilitado (`/etc/gdm3/custom.conf`:
  `AutomaticLoginEnable=true`, `AutomaticLogin=jetson`) — ou seja, sobe até a área de trabalho
  sozinho, sem precisar de teclado/tela, mas ainda é um desktop completo (gdm3/lightdm de pé),
  consumindo RAM que vai fazer falta quando a inferência CNN entrar. Não é bloqueador da Semana 1,
  mas vale reavaliar (trocar para `multi-user.target`) antes de rodar o modelo on-device.
- Root em `/dev/sda1`: 14G, 57% usado, 5.7G livres. As 8530 imagens em `~/frames` (mais o conteúdo
  de `~/frames_legado_misturado`) já são uma fatia relevante disso — atenção ao espaço quando a
  captura rodar semanas seguidas, e principalmente quando entrar fila local de retry de upload.

## Estrutura em `~/scripts`

| Arquivo | Papel | Observação |
|---|---|---|
| `captura.py` | Captura contínua da câmera (`cv2.VideoCapture(0)`, salva 1 frame/s em `~/frames`) | Roda via `citycam.service`. Usa índice `0`, não path fixo. Desde 2026-07-29, grava também um `.json` companheiro por frame (metadado) — ver "Decisões tomadas". |
| `captura.py.bak` | Backup manual anterior | Resíduo, não referenciado por nenhum serviço |
| `continue` | Arquivo vazio (0 bytes) | Resíduo de edição, sem uso aparente |
| `gps.py` | Leitor de GPS (GGA/RMC) contínuo, com reconexão automática, que mantém o último fix em `/run/cityrain/gps.json` | Roda via `gps.service` (novo, 2026-07-21). Ver seção "Decisões tomadas". |
| `botao_desliga.py` | Monitor de botão físico (GPIO BOARD 13) → `shutdown -h now` | Roda via `botao-desliga.service`, usa `Jetson.GPIO`. Debounce de 2s adicionado em 2026-07-29 (ver "Decisões tomadas") — ainda não validado com pressão física real. |
| `uploader.py` | Envia pares `frame_*.jpg`+`frame_*.json` de `~/frames` ao backend, com fila local (o próprio diretório) e retry com backoff | Roda via `uploader.service`. Amostra 1 frame/N s em rede "metered" (hotspot do celular), drena tudo em rede ilimitada (cabo/WiFi de casa). Só apaga o par após HTTP 2xx. **Desde 2026-09-15**, roda o gate binário (`gate.py`) antes de enviar: "chuva" monta o payload achatado real e envia; "seco" desvia pro esqueleto (ver "Decisões tomadas 2026-09-15"). |
| `gate.py` | **Novo (2026-09-15).** Ponte fina entre `uploader.py` e `~/modelo_chuva/detector.py` (modelo já treinado) | Import leve (só repassa constantes); carrega o modelo de verdade (torch) só na primeira classificação. Força `usar_gpu=False` — ver "Decisões tomadas 2026-09-15" (incompatibilidade de CUDA). |
| `mock_backend.py` | Servidor HTTP local (`http.server` da stdlib) que simula o endpoint do backend, pra testar o `uploader.py` sem depender do Guilherme | Uso manual: `python3 mock_backend.py [porta]`. Não é serviço systemd. |
| `cityrain_config.json` | Config compartilhada entre `captura.py` (device_id) e `uploader.py` (backend_url, token, amostragem, gate) | `backend_url` ainda é placeholder (`http://127.0.0.1:8080/upload`) — trocar quando o Guilherme passar a URL real. Novos campos 2026-09-15: `source_type`, `modelo_chuva_path`, `limiar_chuva`, `pasta_sem_chuva_pendente`. |
| `CONTRATO_API.md` | Contrato de upload — **reescrito em 2026-09-15** pra bater com o `openapi.json` real (payload achatado, `weather_label`/`confidence`) | Documento, não é código executável. Caso "seco" documentado como esqueleto pendente (sem endpoint real ainda). |
| `MUDANCAS_NECESSARIAS_BACKEND.md` | **Novo (2026-09-15).** Pedido formal pro Guilherme: endpoint pra "seco" sem foto, quem gera garoa/moderado/forte, formalizar schema de `metadata`, payload+processo pra conseguir o `api_key` do device | Documento pra Rodrigo copiar e enviar. Não é código executável. |
| `wifi_watchdog.py` | **Novo (2026-07-29, 21:34).** Monitora `nmcli device status` do `wlan0`; se ficar 5min+ sem conexão, força `ip link set wlan0 down/up` pra destravar o driver | Roda via `wifi-watchdog.service`. Criado depois de uma queda real de ~36min do WiFi/hotspot observada nos testes desta mesma sessão — não inventa sinal onde não há, só destrava o driver quando o sinal já voltou mas o `wlan0` ficou preso. |
| `verifica_teste_campo.py` | **Novo (2026-07-29).** Script de auditoria pós-trajeto (roda manualmente, não é serviço) | Recebe o horário de início do trajeto e resume: reinícios/erros do `citycam.service`, gaps na continuidade dos frames, presença de `.json`+GPS, erros do `uploader.service` e tamanho da fila, reconexões/resets do `wifi-watchdog.service`, e se a guarda de disco disparou. Uso: `python3 verifica_teste_campo.py "AAAA-MM-DD HH:MM"`. |

`~/frames/` (8530 arquivos, nome `frame_AAAAMMDD_HHMMSS_mmm.jpg`) e `~/frames_legado_misturado/`
(coleção maior, provavelmente mistura de sessões antigas) são dados capturados, não código.

## Serviços systemd relevantes

| Serviço | Estado | Detalhe |
|---|---|---|
| `citycam.service` | enabled, em crash-loop enquanto a câmera está desconectada (esperado) | `Restart=always`, falha com "Erro: não foi possível abrir a câmera" quando `/dev/video0` não existe; volta sozinho ao reconectar o cabo USB |
| `botao-desliga.service` | enabled, active, estável (~1 semana de uptime) | Funcionando conforme esperado |
| `gps.service` | **novo (2026-07-21), enabled, active** | Roda `scripts/gps.py`; `RuntimeDirectory=cityrain` cria `/run/cityrain` automaticamente; `Environment=PYTHONUNBUFFERED=1` pra logs aparecerem no `journalctl` sem atraso. Testado sem hardware físico conectado: fica em `fix: false` de forma estável, sem crash-loop. |
| `nvgetty.service` | **disabled, inactive** (desde 2026-07-21) | Desabilitado para liberar `/dev/ttyTHS1` pro GPS — ver seção "Decisões tomadas" |
| `gpsd.socket` / `gpsd.service` | socket enabled+listening, serviço inativo (ativação por socket) | Não interfere agora (serviço dorme até alguém conectar em `127.0.0.1:2947`), mas é outro consumidor em potencial da porta serial se algo o ativar — considerar desabilitar o socket se não for usado, para não competir com o `gps.service` próprio |
| `systemd-timesyncd.service` | active, `System clock synchronized: yes` | NTP configurado explicitamente (NIC.br) — ver seção "Decisões tomadas" |
| `fake-hwclock` | **instalado e enabled (2026-07-21)** | Ver seção "Decisões tomadas" |
| `uploader.service` | **novo (2026-07-29), enabled+active — confirmado nesta sessão** | Roda `scripts/uploader.py`. Mesmo molde do `gps.service` (`Restart=always`, `PYTHONUNBUFFERED=1`). Testado manualmente (fora do systemd) contra `mock_backend.py`: envia, apaga após 2xx, mantém na fila e faz retry com backoff se o backend cair. |
| `wifi-watchdog.service` | **novo (2026-07-29, 21:34), enabled+active** | Roda `scripts/wifi_watchdog.py`. Ver linha da tabela de scripts acima — reinicia `wlan0` se ficar 5min+ sem conexão. |

## Dispositivos reais (não assumir paths)

- Câmera: nenhum `/dev/video*` presente no levantamento (`ls /sys/class/video4linux/` vazio).
  `lsusb` mostrava só um receptor wireless Logitech (mouse/teclado, `046d:c542`), não a C270.
  Módulo `uvcvideo` está carregado (`lsmod`) e registrado (`dmesg`), então o driver está pronto —
  falta o dispositivo físico aparecer.
- Serial GPS: **decidido `/dev/ttyTHS1`** (pinos 8/10, header 40-pin). Antes desta sessão, tinha
  permissão `crw--w---- root:tty` (grupo só com *write*, `jetson` não está no grupo `tty`) e era
  disputado por um `getty` real do `nvgetty.service`. Resolvido em 2026-07-21: `nvgetty` desabilitado
  + regra udev `/etc/udev/rules.d/99-cityrain-gps.rules` fixando `GROUP="dialout", MODE="0660"`.
  Agora `crw-rw---- root:dialout`, `jetson` acessa direto sem `sudo`. Fiação física ainda não feita
  (só teste pontual, já removido) — `/dev/ttyTHS2` existia como alternativa já funcional
  (`dialout`) mas não foi escolhida por ser menos padrão/documentada no header 40-pin.
  Histórico de shell (`.bash_history`) mostrava Rodrigo sempre rodando `gps.py` com `sudo` — o que
  mascarava o problema de permissão antes desta correção.
- GPIO: `Jetson.GPIO`, modo `BOARD`, pino 13 é o botão de shutdown. `/dev/gpiochip0`/`gpiochip1`
  existem.
- Grupos do usuário `jetson`: `adm dialout cdrom sudo audio dip video plugdev i2c lpadmin gdm
  lightdm gpio weston-launch sambashare` — repare que **não inclui `tty`**.

## Rede

- `eth0` conectado (Wired connection 1, autoconnect yes) — foi o que deu a este ambiente
  conectividade e NTP durante o levantamento.
- Perfil WiFi já salvo no NetworkManager: `Ap_76a` (autoconnect yes, senha redigida — não versionada).
  **⚠️ Rodrigo confirmou que não reconhece essa rede** — pelo nome da senha, é provavelmente o
  hotspot de algum colega de equipe (Gabriel Moreno? Prof. Gabriel?) usado numa sessão de teste
  anterior por outra pessoa mexendo nesta Jetson, não o WiFi de casa do Rodrigo. Decisão
  (2026-07-21): **deixar como está por enquanto**, resolver depois — não tratar como rede confiável
  de bancada nem mexer na prioridade/rota dela até então.
- **WiFi via dongle USB — resolvido em 2026-07-29** (ver "Decisões tomadas"). Esta Jetson não tem
  WiFi embutido (`lspci` sem placa M.2); no levantamento de 2026-07-21 nenhum dongle estava
  plugado. Rodrigo comprou e conectou um dongle **Realtek RTL8188EU** (`lsusb` ID `2357:010c`,
  driver `r8188eu` do staging do kernel, já presente por padrão — nenhuma compilação necessária).
  Cria a interface `wlan0`, gerenciada por NetworkManager. **Atenção**: esse chipset específico é
  **só 2.4GHz** (1T1R, 802.11n) — não enxerga rede 5GHz. Tethering do iPhone via cabo USB continua
  descartado: `CONFIG_USB_IPHETH` não está habilitado neste kernel (`4.9.299-tegra`), e os headers
  instalados são de outra versão (`4.9.337`), inviabilizando compilar o módulo com segurança no
  prazo do TCC.
- Sem `chrony` nem `ntp` clássico instalados — só `systemd-timesyncd` (nativo do sistema), que já
  está ativo e sincronizando enquanto há link de rede. `NetworkManager-wait-online.service` está
  **disabled** e nada usa `network-online.target` bloqueante — boot não trava mesmo sem nenhuma
  rede disponível (confirmado 2026-07-21).

## Dependências Python já instaladas (pip3, ambiente do sistema)

`Jetson.GPIO 2.0.17`, `numpy 1.13.3`, `pynmea2 1.19.0`, `pyserial 3.5`, `requests 2.18.4`,
`requests-unixsocket 0.1.5`. `python3-opencv` via apt (OpenCV 3.2.0, libs `libopencv-*3.2`).
Nada de `onnxruntime`, `torch` ou `tensorrt` python bindings instalado ainda (esperado — é objetivo
de semanas futuras). TensorRT em si vem com o L4T/JetPack, mas não confirmei ainda os bindings
Python nem a versão exata — verificar antes de escrever o pipeline de inferência.

## Pegadinhas já resolvidas (confirmadas nesta sessão)

- Módulo de kernel `uvcvideo` carregado corretamente (resolvido, faltava na imagem Yahboom original).
- `botao-desliga.service` estável há mais de uma semana rodando.
- `systemd-timesyncd` já ativo e sincronizando via rede (parte do objetivo 2 já está de pé; falta
  só o fallback offline).

## Decisões tomadas (2026-07-21, sessão de trabalho)

1. **`nvgetty.service` desabilitado e parado** (`systemctl disable --now`). Ele estava enabled+
   ativo, com um `getty` real segurando `/dev/ttyTHS1` — resquício da imagem Yahboom que nunca
   tinha sido de fato desligado (a `Description=UART on ttyTHS0` do unit é só texto genérico
   desatualizado; nesta placa tegra210 o `nvgetty.sh` sobe getty em `ttyTHS1`). Não foi possível
   `mask` porque o unit é um arquivo real do L4T, não um symlink — `disable --now` já é suficiente
   (não sobe mais no boot, processo já morto). Se algum dia precisar do console serial de
   emergência de volta: `sudo systemctl enable --now nvgetty.service`.
2. **GPS decidido em `/dev/ttyTHS1`** (pinos 8/10 do header 40-pin — padrão em qualquer Jetson
   Nano, mais fácil de cabear/documentar que `ttyTHS2`). Ainda não há fiação física feita (só um
   teste pontual, já desconectado). Permissão resolvida via **`/etc/udev/rules.d/99-cityrain-gps.rules`**
   (`KERNEL=="ttyTHS1", GROUP="dialout", MODE="0660"`) — isso fixa o device no grupo `dialout`
   (que `jetson` já integra) independente do estado do `nvgetty`, sobrevive a reboot, e evita
   precisar colocar o usuário no grupo `tty` (que é compartilhado com os consoles do sistema).
   Confirmado com `udevadm test`: `/dev/ttyTHS1` agora fica `crw-rw---- root:dialout`.
3. **Câmera C270 estava desconectada de propósito** nesta sessão (Rodrigo confirmou — só tinha
   plugado pra um teste pontual e removeu). O crash-loop do `citycam.service` é esperado/inofensivo
   nesse estado (ele volta a funcionar assim que o cabo USB da câmera for reconectado, graças ao
   `Restart=always`); não é bug de software.
4. **NTP + fallback offline resolvidos (item 2 da Semana 1).** Problema: sem RTC com bateria, o
   relógio zera a cada boot até algo corrigir; NTP só corrige quando há rede, deixando um intervalo
   com timestamp errado logo no boot (e offline, fica errado pra sempre). Solução, em duas partes:
   - `systemd-timesyncd` (já vinha ativo) agora configurado em `/etc/systemd/timesyncd.conf` com
     `NTP=a.st1.ntp.br b.st1.ntp.br c.st1.ntp.br` (servidores do NIC.br, mais rápidos/confiáveis no
     Brasil) e `FallbackNTP=pool.ntp.org`. Corrige a hora pra exata assim que há internet.
   - Pacote **`fake-hwclock`** instalado e `enabled`: salva a hora em `/etc/fake-hwclock.data`
     periodicamente (`/etc/cron.hourly/fake-hwclock`, a cada hora) e no shutdown (`ExecStop=save`
     no unit); no boot, roda `fake-hwclock load` **antes de `sysinit.target`** (praticamente o
     primeiro coisa a rodar, bem antes de qualquer serviço do CityRain), restaurando a última hora
     conhecida em vez de deixar o relógio num valor arbitrário. Não é a hora exata (não conta o
     tempo desligado), só uma aproximação razoável até o NTP corrigir — mas já evita a colisão de
     timestamp entre sessões offline.
   - **Testado nesta sessão**: forcei o relógio pra `2000-01-01` (simulando reset de boot sem RTC) e
     rodei `fake-hwclock load` manualmente — restaurou corretamente a última hora salva
     (`2026-07-22 00:49:02`). `systemd-timesyncd` confirmado sincronizando via `a.st1.ntp.br`.
5. **Parser NMEA robusto (item 3 da Semana 1).** `scripts/gps.py` reescrito: lê `/dev/ttyTHS1`
   continuamente, reconecta sozinho se a porta cair (`serial.SerialException` → espera 5s → tenta
   de novo, indefinidamente), ignora qualquer linha corrompida/checksum inválido
   (`pynmea2.ParseError`) sem lançar exceção, e mantém o **último fix conhecido** mesmo quando o
   sinal cai (só a flag `fix` vira `false`; `latitude`/`longitude` não são apagadas) — assim quem
   for montar o metadado por captura (item 4) sempre tem uma coordenada disponível, sabendo se é
   fresca ou não pelo campo `atualizado_em`. Roda como `gps.service` (novo), escrevendo o estado em
   `/run/cityrain/gps.json` (tmpfs, não desgasta o storage, some sozinho a cada reboot) de forma
   atômica (`tmp` + `os.replace`). `RuntimeDirectory=cityrain` no unit cria o diretório em `/run`
   automaticamente. **Testado nesta sessão** com sentenças NMEA de exemplo (GGA com fix, GGA sem
   fix/qualidade 0, RMC, e uma linha de checksum inválido de propósito) — todos os casos se
   comportaram como esperado. Serviço também testado rodando sem o módulo GPS físico conectado:
   fica estável em `fix: false`, sem crash-loop. Fiação física do NEO-6M em `ttyTHS1` ainda
   pendente (ver item 2 da lista de decisões acima).
6. **Revisão de `gps.py`, `captura.py` e `botao_desliga.py` (2026-07-21).** Encontrado e corrigido:
   - `gps.py`: as conversões numéricas (`int(msg.gps_qual)`, `float(msg.horizontal_dil)` etc.) não
     estavam protegidas — uma sentença com checksum válido mas campo em formato inesperado
     derrubava o processo inteiro (perdendo o estado acumulado em memória a cada restart). Agora
     envolvidas em `try/except (ValueError, TypeError)`, testado com uma sentença malformada de
     propósito: estado permanece íntegro, só loga e ignora a linha.
   - `gps.py`: adicionado watchdog de silêncio (`SILENCIO_MAX_S = 15`) — se nenhuma sentença válida
     chegar por mais de 15s (antena arrancada, módulo sem energia — não só "qualidade 0"), `fix`
     é degradado pra `false` sozinho, em vez de ficar congelado no último valor indefinidamente.
   - `captura.py`: adicionado guarda de espaço em disco (`ESPACO_MINIMO_MB = 500`) — **não apaga
     nada** (não há pipeline de upload ainda; apagar seria perder dado de campo de vez), só pausa a
     gravação de frames novos se o disco ficar abaixo de 500MB livres, logando no máximo 1x/min.
     Motivo: medido nesta sessão que a captura contínua a 1fps consome **~6,1GB/dia** (71KB médios
     por frame × 86400 frames/dia), e havia só 5,7GB livres — sem guarda, o disco encheria em menos
     de um dia de campo contínuo, arriscando escrita corrompida/filesystem cheio.
   - Rotação/retenção de frames antigos (apagar de fato) foi **propositalmente adiada** — decisão
     do Rodrigo — até existir o pipeline de upload pro backend; antes disso, qualquer frame
     apagado é dado de campo perdido sem cópia em lugar nenhum.
   - `citycam.service` e `gps.service` ganharam `Environment=PYTHONUNBUFFERED=1` (mesmo problema de
     buffer de stdout do Python, que atrasava/escondia mensagens no `journalctl`).
   - **Identificado, mas não corrigido ainda (pendente de decisão do Rodrigo)**: `botao_desliga.py`
     desliga a Jetson na primeira leitura `LOW` do pino, sem debounce — risco real de falso
     positivo por ruído elétrico do motor/vibração dentro do carro. Também usa polling a cada 200ms
     em vez de detecção por interrupção (`GPIO.add_event_detect`) — funciona, mas gasta CPU à toa.

## Decisões tomadas (2026-07-29, sessão de trabalho)

1. **Item 1 da Semana 1 (conectividade persistente) — desbloqueado.** Dongle WiFi USB Realtek
   RTL8188EU chegou, foi plugado e reconhecido de imediato pelo driver `r8188eu` (staging, já
   presente no kernel — sem necessidade de compilar nada). Interface `wlan0` criada e gerenciada
   por NetworkManager.
2. **Conectado ao hotspot pessoal do iPhone do Rodrigo** (rede WiFi "Rodrigo", WPA2). Precisou
   ativar **"Acesso Pessoal" → "Maximizar Compatibilidade"** no iPhone — sem isso o hotspot roda em
   5GHz por padrão em iPhones recentes, banda que o RTL8188EU não enxerga (só 2.4GHz). Depois de
   ativar, a rede apareceu no scan (`nmcli device wifi list`) com sinal 100%. Conexão testada e
   confirmada com internet real: IP `172.20.10.7/28` via DHCP, `ping 8.8.8.8` por `wlan0` com 0% de
   perda (33–81ms). Perfil de conexão salvo com autoconnect (padrão do NetworkManager).
   **Reconexão automática + failover real testados e confirmados em 2026-07-29** (cabo Ethernet
   desconectado fisicamente): `wlan0` assumiu a rota default sozinho, sem intervenção manual, e
   comandos/pings continuaram respondendo normalmente pelo hotspot do celular. **Nuance**: nos
   primeiros testes desta mesma sessão houve uma queda real de ~36min do WiFi antes de reconectar
   sozinho — o `wifi-watchdog.service` (ver tabela de serviços) foi criado por causa disso, força
   down/up no `wlan0` se ficar 5min+ sem conexão. O teste final "deu certo" rodou com o watchdog já
   no ar; não confirmado ainda se a reconexão seria confiável sem ele. Item 1 da Semana 1 agora
   **totalmente concluído**, com essa ressalva registrada.
3. **Rotas de rede confirmadas corretas para o caso de uso de campo**: com `eth0` conectado (casa/
   bancada), ele é a rota default (metric 100) e o WiFi fica em standby (metric 600) — não há
   conflito entre os dois ativos ao mesmo tempo. No carro, sem cabo Ethernet nenhum, o `wlan0`
   assume a rota default automaticamente (confirmado na prática em 2026-07-29, failover real com
   o cabo desconectado).
4. **Limpeza de perfis WiFi**: durante os testes, uma tentativa de conectar na rede de casa
   ("RODRIGO", WPA2) com a senha errada (`[REDIGIDO]` — na verdade a senha do hotspot do iPhone, não
   da rede de casa) deixou um perfil salvo com credencial inválida e travou o `wlan0` em
   `connecting (need authentication)`, bloqueando novos scans (`Error: Scanning not allowed while
   unavailable or activating`). Perfil `RODRIGO` (maiúsculo, o de casa) foi apagado a pedido do
   Rodrigo (`nmcli connection delete`). Perfis que restaram: `Rodrigo` (hotspot iPhone, ativo),
   `Wired connection 1` (cabo), `docker0`, e o antigo `Ap_76a` (rede de origem desconhecida — segue
   intocado, decisão de 2026-07-21 continua valendo).
5. **Nota operacional sobre `sudo` nesta Jetson**: comandos que mexem em rede via `nmcli`
   (connect/disconnect/delete de conexão) exigem autorização via polkit, que falha com "not
   authorized" quando executado a partir de uma sessão sem terminal interativo/D-Bus de sessão
   ativo (como o shell usado para automatizar comandos nesta sessão). `sudo -v` rodado nesse mesmo
   shell não resolve porque o cache de credenciais do sudo é por terminal/sessão e não é
   compartilhado. Solução usada: pedir para o Rodrigo rodar o comando com `sudo` diretamente no
   terminal dele — evita também expor a senha do sudo em texto puro na conversa.

## Decisões tomadas (2026-07-29, sessão de trabalho — parte 2)

Continuação da sessão do dongle WiFi (ver decisões 1-5 acima). Com o prazo apertado (entrega em
~2 semanas), Rodrigo decidiu não esperar o formato final do metadado vindo do colega — seguir com
um schema provisório, fácil de ajustar depois, para não bloquear o pipeline de envio.

6. **Arquitetura de inferência confirmada com Rodrigo**: serão **dois modelos**, não um. (a) Gate
   binário chuva/não-chuva **na Jetson**, decidindo se um frame é enviado ou descartado — ainda
   **não treinado**, fica pra fase stretch. (b) Classificador de **4 classes** (seco/garoa/
   moderado/forte) **no backend**, que roda sobre os frames que a Jetson mandou. Importante: o
   gate on-device só pode ser treinado depois de existir dataset — e esse dataset é justamente o
   que este pipeline de upload vai coletar, incluindo frames "sem chuva". Por isso o `uploader.py`
   nasceu com um ponto de extensão (`deve_enviar()`) que hoje sempre retorna `True` — enviar tudo
   agora é necessário pra ter dado de treino da classe "seco" depois.
7. **Item 4 da Semana 1 (metadado por captura) — implementado.** `captura.py` agora grava um
   `frame_<timestamp>.json` companheiro pra cada `.jpg`, com `device_id`, timestamp UTC
   (`datetime.now(timezone.utc)`, independente do nome do arquivo que continua em hora local) e o
   último fix do `/run/cityrain/gps.json` (ou `null` se o `gps.service` estiver fora do ar — a
   captura nunca falha por causa do GPS). Escrita atômica (tmp + `os.replace`, mesmo padrão do
   `gps.py`). **Testado via simulação** (câmera física ainda desconectada) confirmando leitura de
   config, leitura do estado do GPS e escrita atômica corretas — falta validar com a câmera
   plugada de verdade gerando o par `.jpg`+`.json` no fluxo real do `citycam.service`.
8. **Pipeline de envio ao backend implementado** (`uploader.py` + `uploader.service` +
   `cityrain_config.json` + `mock_backend.py` + `CONTRATO_API.md`). Decisões:
   - **Fila = o próprio `~/frames`**: sem banco de dados, sobrevive a reboot de graça. Um par
     `.jpg`+`.json` é "pronto pra envio" pela simples presença do `.json`.
   - **Retenção: apaga após 2xx confirmado do backend** — supera a decisão anterior (2026-07-21)
     de nunca apagar, que só valia enquanto não existia upload. Resolve o aperto de disco
     (5,4GB livres / ~6GB de captura por dia).
   - **Detecção de rede "metered"**: lê a interface da rota default (`ip route show default`) e
     mapeia pro nome da conexão NetworkManager (`nmcli ... connection show --active`); se o nome
     estiver na lista `conexoes_metered` do config (hoje só `"Rodrigo"`, o hotspot do iPhone),
     amostra 1 frame a cada `intervalo_amostragem_metered_s` (padrão 15s) em vez de drenar tudo —
     em cabo/WiFi de casa, drena a fila inteira. Evita estourar o plano de dados do celular.
   - **Retry**: timeout 30s, backoff exponencial 5s→300s em qualquer falha (rede, timeout, 5xx).
     4xx é tratado como erro de contrato (não de rede) — loga com destaque e mantém na fila, nunca
     descarta o frame.
   - **Contrato do lado do backend ainda não confirmado com o Guilherme** — `CONTRATO_API.md`
     documenta a proposta (POST multipart, campos `image`+`metadata`) pra ele validar/ajustar.
     `backend_url` no config é só placeholder (`http://127.0.0.1:8080/upload`).
   - **Testado ponta-a-ponta nesta sessão** (manualmente, fora do systemd, contra
     `mock_backend.py`): upload com sucesso apaga o par; backend fora do ar mantém o par na fila e
     tenta de novo com backoff; quando o backend volta, drena sozinho. **`uploader.service` foi
     instalado a pedido do Rodrigo** (comando rodado por ele via `sudo`) — confirmar que subiu
     (`systemctl status uploader.service`) na próxima sessão.
9. **Debounce no botão de shutdown** (pendência identificada em 2026-07-21, resolvida agora):
   `botao_desliga.py` só desliga se o pino ficar `LOW` ininterrupto por 2 segundos
   (`pressao_confirmada()`), em vez de agir na primeira leitura. Reduz risco de shutdown acidental
   por ruído elétrico/vibração do carro. **Ainda não validado com pressão física real do botão** —
   só revisão de código + `py_compile`. Detecção continua por polling (200ms), não por interrupção
   (`GPIO.add_event_detect`) — ficou fora do escopo desta rodada, não é bloqueador.
10. **Frames antigos sem metadado** (os 8530 em `~/frames` + `~/frames_legado_misturado`, todos
    capturados antes do item 7 existir): **fora da fila automática do `uploader.py`** por definição
    (não têm `.json` companheiro). Decisão de subir manualmente ou manter só como dataset local
    ficou em aberto — não é urgente, não competem por espaço da mesma forma agora que a política de
    retenção mudou para "apaga após upload".

## Decisões tomadas (2026-09-14, sessão de integração do modelo — em andamento)

Rodrigo trouxe da própria máquina (via `scp`) o modelo de rede neural já treinado e o contrato da
API do backend, com o objetivo de montar o pipeline completo (captura → gate on-device →
upload já classificado) e testar localmente antes de ir pra rua. Estado ao final desta sessão
(pode ter continuado depois — **reconferir antes de assumir concluído**):

1. **A arquitetura do backend mudou em relação ao que estava documentado.** O contrato real
   (`openapi.json` buscado ao vivo do backend, ver item 2) deixa claro que **o CNN roda na própria
   Jetson** e o backend só recebe `weather_label`+`confidence` já prontos no `metadata` do
   `POST /api/v1/ingest` — substitui o plano antigo de "classificador de 4 classes no backend".
   O modelo que a Jetson roda é o **gate binário chuva/não-chuva** (ver item 3), não um stub.
2. **Backend real descoberto e já está em produção**: `https://api-production-046f.up.railway.app`
   (`/health` e `/health/db` respondendo OK). Contrato completo salvo em
   `~/modelo_chuva/openapi.json` (buscado direto do `/openapi.json` do backend, mais confiável que
   o `contrato.html` que o Rodrigo mandou, que é só o HTML estático do Swagger UI sem o schema).
   Resumo do contrato:
   - `POST /api/v1/ingest` (multipart `image` + `metadata` JSON): exige `captured_at` (ISO 8601),
     `latitude`, `longitude`, `source_type`, e (por texto da descrição, não fica explícito no
     schema formal) `weather_label`+`confidence`. Idempotente por imagem (reenviar após falha de
     rede retorna 200 em vez de 201). Isso é **bem diferente** do schema atual do
     `uploader.py`/`CONTRATO_API.md` (que aninha tudo em `gps{}` e não tem `weather_label`) — vai
     precisar reescrever a montagem do `metadata` antes de apontar pro backend real.
   - **Todos os endpoints exigem `HTTPBearer`**, inclusive `POST /api/v1/devices/` (registrar
     dispositivo) — ou seja, **precisa de um token admin do Guilherme só pra conseguir a `api_key`
     do device** (que só aparece uma vez, no `DeviceCreatedResponse`). `cityrain_config.json` segue
     com `token: null`. **Bloqueio externo, só o Rodrigo resolve com o Guilherme** — não dá pra
     testar contra o backend de verdade sem isso; enquanto isso, testar contra `mock_backend.py`
     (que não checa auth).
3. **Modelo recebido: `~/modelo_chuva/bestModel.pth` (9,15MB) + `~/modelo_chuva/detector.py`.**
   Sem precisar de torch instalado, inspecionei os pesos com um "unpickler" falso (script em
   `/tmp/inspect_state_dict.py`, não copiado pra cá) e confirmei: é um
   `torchvision.models.mobilenet_v2` padrão com `classifier` trocado por `Linear(1280, 2)` — 2
   classes de saída. O `detector.py` (que o Rodrigo mandou depois, e que resolveu as dúvidas antes
   de eu precisar perguntar tudo) documenta o contrato de pré-processamento real do treino:
   - Entrada **384x384** (não 224 — não presumir o padrão comum de transfer learning sem checar),
     RGB, normalização ImageNet (`mean=[0.485,0.456,0.406]`, `std=[0.229,0.224,0.225]`), redimensionamento bilinear.
   - Índice de saída **1 = "com_gota" (chuva)**, índice 0 = "sem_gota" — já resolvido no código,
     não precisa mais adivinhar ordem de classe.
   - Limiar padrão 0.5 (métricas do TCC do Rodrigo: precisão 99,5%, recall 96,1%).
   - Suporta motor PyTorch (`.pth`) ou ONNX Runtime (`.onnx`), com fallback automático por extensão
     do arquivo — dá pra trocar por uma versão ONNX no futuro sem tocar no resto do pipeline.
4. **Ambiente de inferência montado nesta sessão** (doloroso, documentar bem pra não repetir):
   - `torch 1.11.0a0+17540c5+nv22.01` instalado via wheel oficial NVIDIA pra JetPack 4.6.1/Python
     3.6 (`https://developer.download.nvidia.com/compute/redist/jp/v461/pytorch/torch-1.11.0a0+17540c5+nv22.01-cp36-cp36m-linux_aarch64.whl`,
     184MB, ainda no ar). Precisou, além do wheel: pacotes CUDA runtime que faltavam
     (`cuda-libraries-10-2` + `libcudnn8`, ~1,8GB — o wheel da NVIDIA carrega essas libs mesmo
     rodando só em CPU) e `cuda-nvtx-10-2`. Depois faltou `libomp.so` (sem versão) — o pacote
     `libomp5` do Ubuntu só cria `libomp.so.5`; resolvido com
     `ln -sf /usr/lib/aarch64-linux-gnu/libomp.so.5 /usr/lib/aarch64-linux-gnu/libomp.so` + `ldconfig`.
   - **numpy do PyPI (`manylinux2014_aarch64`) trava com `Illegal instruction (core dumped)` nesta
     Jetson** a partir de `numpy==1.19.5` — incompatibilidade binária com o Cortex-A57 (a wheel
     genérica do PyPI aparentemente assume instruções que esse core não tem). `numpy==1.19.4`
     funciona normalmente e resolve a interoperabilidade `torch.from_numpy()` (o `numpy` do apt,
     1.13.3, é velho demais pro bridge do torch — falha com `RuntimeError: Numpy is not available`).
     **Se precisar mexer no numpy de novo: testar `1.19.4` antes de qualquer versão mais nova.**
   - `torchvision` **não tem wheel pronta** pra essa combinação — precisou compilar do zero
     (`git clone --branch v0.12.0 --depth 1 https://github.com/pytorch/vision`, ~40-90min na Nano,
     `MAX_JOBS=2` pra não estourar RAM). Ver estado da build em
     `~/modelo_chuva/build_torchvision.log` — **conferir se terminou e se importa antes de
     continuar** (`python3 -c "import torchvision; from torchvision.models import mobilenet_v2"`).
   - Disco ficou apertado durante essa instalação (chegou a 83% usado, ~2,3GB livres). Vale limpar
     `~/modelo_chuva/torchvision` (código-fonte + objetos de build) depois que a instalação
     terminar — não precisa mais dele depois do `setup.py install`.
5. **Torchvision 0.12.0 compilou, mas está quebrado — não é corrupção por queda de energia,
   é incompatibilidade de versão com Python 3.6.** Reconferido na sessão seguinte (mesmo dia à
   noite, depois de a Jetson ter desligado e voltado sozinha no meio do caminho — não investigado a
   causa desse desligamento a pedido do Rodrigo). Diagnóstico:
   - `import torchvision` dá **Segmentation fault (core dumped)**, não um erro limpo.
   - Os `.so` compilados (`_C.so` 33MB, `image.so`, `video_reader.so`) são ELF válidos e completos —
     descarta corrupção de arquivo por escrita interrompida.
   - `import torch` sozinho funciona normalmente (`1.11.0a0+17540c5`) — descarta problema geral de
     ambiente/energia afetando tudo.
   - Backtrace via `gdb` (`gdb -q -batch -ex run -ex bt --args python3 -c "import torchvision"`)
     mostra ~130 frames repetidos de `_PyEval_EvalFrameDefault`/`_PyObject_FastCallDict` em loop —
     assinatura de **recursão descontrolada em Python estourando a stack C**, não crash de código
     nativo/CUDA.
   - Causa raiz: `torchvision/datasets/fgvc_aircraft.py` usa `from __future__ import annotations`
     (sintaxe só válida a partir do Python 3.7 — PEP 563). `torchvision/__init__.py` importa
     `datasets` de forma eager junto com `models`, então **qualquer** `import torchvision` tropeça
     nesse arquivo nesta Jetson (Python 3.6.9, não dá pra trocar). O mecanismo de resolução de egg
     (`pkg_resources`/`easy-install`) parece re-tentar o import em loop em vez de propagar o
     `SyntaxError` direto, daí o segfault por stack overflow em vez de um erro limpo.
   - **Ideia a testar primeiro na próxima sessão, antes de recompilar de novo**: o `detector.py` só
     usa a arquitetura `mobilenet_v2` pra classificação — os módulos compilados em C++/CUDA do
     torchvision (`_C.so`) são pra `nms`/`roi_align` (detecção/segmentação), que não são usados
     aqui. Pode dar pra copiar só `torchvision/models/mobilenetv2.py` (puro Python, só depende de
     `torch`) pro projeto e carregar o `bestModel.pth` direto nele, **sem instalar o pacote
     `torchvision` inteiro** — evitaria todo esse problema sem precisar recompilar. Se não funcionar,
     alternativa é recompilar numa tag anterior a v0.12.0 (antes do `fgvc_aircraft.py`), compatível
     com Python 3.6 — arriscando mismatch de ABI com o `torch 1.11` já instalado.
   - Ainda **não** rodamos o `detector.py` contra um frame real (nem `mock_backend.py`, nem backend
     real) — bloqueado por este problema.
6. **Backend real testado nesta sessão (só health/auth, sem enviar dado de verdade)**:
   `GET /health` → `200 {"status":"ok"}`; `GET /health/db` → `200 {"status":"ok","database":"connected"}`;
   `POST /api/v1/ingest` sem token → `403`; `POST /api/v1/devices/` sem token → `403`. Backend está
   de pé e saudável, exige `HTTPBearer` como documentado — confirma que o bloqueio do token do
   Guilherme (item 2 acima) é o único impeditivo pra testar o fluxo real.
7. **Plano pra próxima sessão** (nesta ordem): (a) tentar vendorizar só `mobilenetv2.py` do
   torchvision pra destravar o `detector.py` sem depender do build quebrado; (b) validar com uma
   foto de chuva conhecida e uma seca pra confirmar que a classe não saiu invertida; (c) plugar o
   `detector.py` no `captura.py`/`uploader.py`, reescrevendo o `metadata` pro schema novo
   (`captured_at`/`latitude`/`longitude`/`source_type`/`weather_label`/`confidence`, achatado — não
   mais aninhado em `gps{}`); (d) testar local contra `mock_backend.py`; (e) só então apontar
   `backend_url` pro Railway real, depois de ter o token do Guilherme; (f) limpar
   `~/modelo_chuva/torchvision` (fonte da build) quando o item (a) ou o rebuild alternativo estiver
   resolvido — disco em 83% usado, 2,3GB livres.
8. **`~/frames` da sessão 2026-09-05→2026-09-13 (2.772 arquivos, 126MB) transferida manualmente
   pro PC pessoal do Rodrigo via `rsync` nesta sessão** — aguardando confirmação dele de que chegou
   íntegra antes de apagar da Jetson (mesmo padrão das sessões anteriores, ver histórico de memória:
   nunca apagar dado de campo sem confirmação explícita de cópia segura).

## Decisões tomadas (2026-09-15, sessão de retomada — esqueleto chuva/não-chuva)

Jetson desligou sozinha de novo entre a sessão de 09-14 e esta (mesmo padrão de sempre:
`TEGRA_POWER_ON_RESET`, corte de energia real — não investigado, Rodrigo pediu pra não mexer).
`uploader.service` subiu sozinho no boot (21:06) e ficou em backoff normal, sem efeito colateral
(`backend_url` ainda placeholder, `Connection refused` — nada foi perdido).

1. **`openapi.json` real conferido de novo, byte a byte idêntico ao salvo em 09-14** — nenhuma
   mudança do lado do Guilherme desde a última sessão. Aproveitei pra inspecionar o schema mais a
   fundo (antes só tínhamos olhado o `Body_ingest`) e achei 2 problemas de arquitetura que não
   tinham sido percebidos:
   - **`GET /api/v1/captures` e `GET /api/v1/stats/geo` usam enum de 4 classes**
     (`seco/garoa/moderado/forte`) pra filtro e agregação — mas o gate que a Jetson roda é
     **binário** (`com_gota`/`sem_gota`). Não tem como a Jetson sozinha preencher
     garoa/moderado/forte.
   - **Não existe endpoint pra avisar "sem chuva" sem mandar foto** — `POST /api/v1/ingest` exige
     `image` no schema. O plano do Rodrigo (só subir foto quando tem chuva, "seco" vira só uma
     mensagem) não tem onde encostar no contrato atual.
   - Documentado tudo isso, mais o pedido de token/registro de device com o payload exato de
     `DeviceCreate` (`name`, `hw_model: "jetson_nano"` — não `jetson_xavier`, que é só o exemplo do
     schema), em **`~/scripts/MUDANCAS_NECESSARIAS_BACKEND.md`**, pronto pro Rodrigo copiar e
     mandar pro Guilherme.
2. **Esqueleto do pipeline chuva/não-chuva implementado e testado em `uploader.py` + `gate.py`
   novo**, enquanto se espera a resposta do Guilherme:
   - Antes de cada envio, `uploader.py` roda o gate (`gate.classificar`) uma vez por frame e grava
     `weather_label`/`confidence` de volta no `.json` local (cache — não reclassifica em retry).
   - `weather_label == "chuva"`: monta o `metadata` já no formato achatado real da API
     (`captured_at`/`latitude`/`longitude`/`source_type`/`weather_label`/`confidence`) e envia
     como sempre.
   - `weather_label == "seco"`: **não envia nem apaga** — move o par pra
     `~/frames/sem_chuva_pendente/`, isolado da fila principal, até existir um endpoint de verdade
     pra esse caso (item 1 do `MUDANCAS_NECESSARIAS_BACKEND.md`). Quando o Guilherme responder, é
     só trocar a função `move_para_pendente_seco()` por uma chamada real.
   - **Testado só contra cópias isoladas** de frames reais (`frame_20260905_151154_299.jpg`,
     confirmado `chuva`/0.9967 — bate com o `deteccoes.csv` de 09-15 anterior) e contra
     `mock_backend.py` numa porta de teste — nunca contra a fila real (`~/frames`, 2772 pares) nem
     via `uploader.service`. **`uploader.service` NÃO foi reiniciado nesta sessão** — continua
     rodando o código antigo (`deve_enviar()` sempre `True`) até alguém decidir reiniciar. Reiniciar
     vai disparar a reclassificação de todos os 2772 pares pendentes (~2-2,5s cada, ~1h30-2h de
     CPU) e começar a mover os "secos" pra fora de `~/frames` — avisar o Rodrigo antes de reiniciar
     de propósito, não fazer automático.
3. **Bug real de hardware descoberto durante o teste**: o wheel de torch instalado em 09-14
   (`torch-1.11.0a0+17540c5+nv22.01`, buildado pra JetPack 4.6.1) tem kernels CUDA só pra
   `sm_62`/`sm_72` — a GPU desta Jetson Nano é Tegra X1, `sm_53`, **não suportada por esse wheel**.
   Tentar `usar_gpu=True` (padrão do `detector.py`) derruba com
   `RuntimeError: CUDA error: no kernel image is available for execution on the device`. É por
   isso que o teste anterior (`deteccoes.csv`, sessão 09-15 cedo) só funcionou: foi rodado via CLI
   com `--cpu`. **`gate.py` agora força `usar_gpu=False` sempre**, com o motivo documentado no
   código. Inferência fica em ~2-2,5s/frame só de CPU — aceitável pra fila em background, mas
   **não dá pra rodar o gate dentro do `captura.py`** (que precisa manter 1fps) — por isso o gate
   vive no `uploader.py`, não na captura.
   - Se precisar de inferência mais rápida no futuro: `detector.py` já suporta motor ONNX Runtime
     como alternativa (não depende de torch/torchvision) — não testado ainda nesta Jetson.

**Why:** o plano de arquitetura (gate na Jetson decide enviar/não enviar, backend/dashboard usa 4
classes) já estava documentado desde 07-29, mas só ao inspecionar o `openapi.json` a fundo (schema
de filtro/agregação, não só o de ingest) ficou claro que o contrato atual não tem como acomodar
esse plano sem mudança do lado do backend — daí isso não ter aparecido nas sessões anteriores, que só
olharam o schema de `POST /ingest`.
**How to apply:** antes de reiniciar `uploader.service` ou apontar `backend_url` pro Railway real,
confirmar com o Rodrigo se o Guilherme já respondeu o `MUDANCAS_NECESSARIAS_BACKEND.md` — enviar
`weather_label: "chuva"` sem saber se o backend/dashboard aceita esse valor (fora do enum de 4
classes) pode gerar dado inconsistente no banco de produção. Também não assumir que rodar em GPU
vai "só funcionar" nesta Jetson — este wheel específico de torch não suporta o hardware dela.

## Decisões tomadas (2026-09-15, mesma sessão — migração pra ONNX Runtime resolveu a performance)

Rodrigo pediu validação explícita da arquitetura visando **performance** (Jetson Yahboom fraca) e
**tolerância a falha** (não perder fila se cair). Resultado:

1. **Quarentena por excesso de tentativas** (`uploader.py`): campo `tentativas_gate` gravado no
   `.json` **antes** de chamar o gate (não depois) — se o processo morrer no meio da inferência
   (crash nativo, não é `except` capturável), o contador sobrevive no disco. Depois de
   `TENTATIVAS_GATE_MAX = 5` falhas no mesmo frame, o par vai pra `~/frames/erro_gate/` em vez de
   ficar bloqueando a fila inteira pra sempre (`Restart=always` + `RestartSec=5` faria o mesmo
   frame mais antigo travar tudo atrás dele indefinidamente, sem isso). Testado isoladamente.
2. **Gargalo de performance identificado e resolvido**: medi a inferência de verdade — torch/.pth
   em CPU (forçado por causa da incompatibilidade de GPU documentada acima) custava **~2,1s/frame**,
   mais lento que a câmera captura (1fps) — fila cresceria sem parar em qualquer trajeto contínuo
   (79min de trajeto = ~2h42 só pra classificar). Rodrigo escolheu migrar pra **ONNX Runtime**
   como solução (em vez de amostragem ou aceitar o atraso). Passos:
   - Nenhum TensorRT/onnxruntime estava instalado. Descoberto que o repo apt oficial da NVIDIA
     (`nvidia-l4t-apt-source.list`, já configurado desde a instalação do torch) tem
     `libnvinfer8`/`python3-libnvinfer` 8.2.1 pra `r32.7` — mas **instalar exige sudo interativo,
     que esta sessão não tem** (mesma limitação de sempre, ver decisão 2026-07-29 item 5). Comando
     pronto pro Rodrigo rodar no terminal dele:
     ```
     sudo apt-get update && sudo apt-get install -y libnvinfer8 libnvinfer-plugin8 \
       libnvonnxparsers8 libnvparsers8 python3-libnvinfer
     ```
   - **`onnxruntime_gpu 1.10.0` (cp36, aarch64) instalado via `pip3 install --user`** — não
     precisa de sudo. Wheel baixado do Jetson Zoo/box.com (referência oficial usada até pelo guia
     de build do mmdeploy pra Jetson), validado como zip/wheel legítimo antes de instalar.
     Protobuf do sistema (3.0.0) já satisfaz a dependência — versões mais novas de onnxruntime
     (1.11+) exigem protobuf que só roda em Python ≥3.7, então **não subir a versão do
     onnxruntime sem checar isso de novo**.
   - **`~/modelo_chuva/exportar_onnx.py` (novo)**: converte `bestModel.pth` → `bestModel.onnx`
     (opset 11, tamanho de entrada fixo 1×3×384×384). Rodado uma vez, gerou `bestModel.onnx`
     (8,8MB). Validado bit a bit contra o `.pth` original no mesmo frame de teste
     (`frame_20260905_151154_299.jpg`): probabilidade idêntica (0.99665665...), mesma classe.
   - **Resultado de performance**: CPU via onnxruntime já é ~6,5x mais rápido que torch
     (**302ms** vs 1958-2881ms) com resultado idêntico. E mais importante: **CUDAExecutionProvider
     do onnxruntime funciona de verdade nesta GPU** (diferente do wheel de torch) — paga ~14-18s de
     inicialização de contexto CUDA uma vez só (por vida do processo `uploader.service`), depois
     fica em **~95-100ms/frame**. TensorRT ainda não instalado (falta o apt do Rodrigo), mas
     onnxruntime já cai sozinho pro CUDA sem erro fatal (só loga um aviso de "TensorRT
     indisponível" e segue). **Isso já resolve o gargalo de throughput sozinho** — nem precisa do
     TensorRT pra a fila parar de crescer sem controle. `gate.py`/`cityrain_config.json` já
     apontam pro `.onnx` (`usar_gpu=True`, motor escolhido automaticamente pela extensão do
     arquivo em `detector.py`).
   - Reclamado espaço em disco antes de instalar (~400MB): apagado `~/modelo_chuva/torchvision`
     (código-fonte da build antiga, resíduo já marcado pra limpeza) e o `.whl` do torch (só um
     instalador, redownloadável se precisar — URL documentada na seção anterior). Disco: 83% → 80%
     usado (2,3G → 2,7G livres).
   - **Ainda não reiniciei o `uploader.service`** — continua rodando o código antigo. Com o novo
     motor onnx, reprocessar os 2772 pares pendentes agora custaria só **~5 minutos** (não mais
     ~1h30-2h como estimado antes da migração) — mudou bastante o cálculo de custo de reiniciar,
     mas a decisão de quando apontar `backend_url`/reiniciar continua do Rodrigo (ver item 2 da
     seção anterior sobre o contrato do backend ainda não estar fechado).
3. **Preocupação levantada pelo Rodrigo, documentada mas não implementada ainda**: o gate decide
   por frame isolado, sem olhar a vizinhança temporal — um frame único pode sair `sem_gota` por
   ruído pontual no meio de uma sequência de chuva de verdade, e como "seco" nunca é enviado (nem
   a foto), esse frame se perde silenciosamente. Adicionado como item novo (5) no
   `MUDANCAS_NECESSARIAS_BACKEND.md`, perguntando ao Guilherme se a suavização por série temporal
   deveria rodar no backend (usando o histórico por device) e, se sim, se a Jetson precisaria mudar
   o critério de descarte (ex.: só tratar como "seco" depois de N frames seguidos, tipo o debounce
   já usado no botão de shutdown) pra não perder o dado antes de qualquer suavização rodar.

**Why:** a arquitetura original (rodar o gate a cada frame, decidir na hora) parecia razoável no
papel, mas só medir o tempo real de inferência nesta Jetson especificamente revelou que não
acompanha 1fps — importante não assumir que "rodou uma vez e deu certo" (`deteccoes.csv` da sessão
anterior) significa que a arquitetura aguenta o volume real de um trajeto de campo.
**How to apply:** se o Rodrigo perguntar de novo sobre performance, os números de referência desta
Jetson são: torch/CPU ~2,1s/frame (não usar), onnxruntime/CPU ~300ms/frame (funciona, sem GPU),
onnxruntime/CUDA ~95-100ms/frame + ~15-18s de warm-up único (o que está configurado agora). Não
prometer que TensorRT vai ficar ainda mais rápido sem medir — o ganho de CUDA pra TensorRT pode ser
pequeno depois que CUDA já resolveu o gargalo principal.

## Backlog do TCC (contexto maior, não é tudo desta semana)

- **Semana 1**: conectividade persistente no boot (✅ concluído — dongle WiFi + hotspot + reconexão
  automática/failover real testados e confirmados 2026-07-29); NTP + fallback offline (✅
  fake-hwclock); parser NMEA robusto (✅ GGA/RMC, sem sinal não quebra o pipeline); metadado por
  captura (✅ implementado 2026-07-29, com schema provisório — falta validar com câmera física
  plugada).
- **Envio ao backend com fila local e retry** (✅ implementado e testado 2026-07-29 contra mock —
  falta: contrato final confirmado com o Guilherme, `backend_url`/`token` reais, e teste contra o
  backend de verdade).
- **Debounce do botão de shutdown** (✅ implementado 2026-07-29 — falta validar com pressão física).
- **Depois / stretch**: gate binário chuva/não-chuva rodando **on-device** na Jetson (ONNX/
  TensorRT, respeitando RAM da Nano e o Python 3.6/pip antigo) — decidido em 2026-07-29 que esse
  gate só entra depois de existir dataset e modelo treinado; o classificador de 4 classes
  (seco/garoa/moderado/forte) roda no **backend**, fora do escopo desta Jetson.
