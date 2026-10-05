# CityRain — código embarcado da Jetson Nano

Todo o **código-fonte, config e documentação** que roda na Jetson Nano, extraído do dispositivo em
2026-09-15. Esta é a fonte de verdade do que está embarcado: os
arquivos em `/home/jetson/scripts/` e as units em `/etc/systemd/system/` da Jetson são cópias
deste diretório.

## Estrutura

```
ml/scripts/captura/
├── CLAUDE.md                          # estado verificado do projeto — vale como README/contexto
├── captura.py                         # captura contínua da câmera (citycam.service)
├── gps.py                             # leitor GPS (gps.service)
├── botao_desliga.py                   # monitor do botão físico de shutdown (botao-desliga.service)
├── uploader.py                        # fila + gate + envio ao backend (uploader.service)
├── gate.py                            # ponte uploader.py -> modelo (novo, 2026-09-15)
├── wifi_watchdog.py                   # watchdog do wlan0 (wifi-watchdog.service)
├── mock_backend.py                    # servidor fake pra testar o uploader sem depender do backend real
├── verifica_teste_campo.py            # auditoria manual pós-trajeto
├── cityrain_config.json               # config compartilhada (device_id, backend_url, token, gate)
├── CONTRATO_API.md                    # contrato de upload documentado
├── MUDANCAS_NECESSARIAS_BACKEND.md    # ⚠️ é a mensagem pra mandar ao Guilherme sobre a API
├── modelo_chuva/
│   ├── detector.py                    # inferência (motor torch ou onnxruntime)
│   ├── mobilenetv2_vendored.py        # arquitetura vendorizada (evita o torchvision quebrado)
│   ├── exportar_onnx.py               # conversão .pth -> .onnx (rodar 1x por modelo novo)
│   └── instalar_*.sh, compilar_torchvision.sh   # scripts de setup do ambiente (dolorosos, documentados)
└── systemd/
    ├── citycam.service, gps.service, botao-desliga.service
    ├── uploader.service, wifi-watchdog.service
```

## O que ficou de fora de propósito

Pesos de modelo (`.pth`/`.onnx`), o wheel do onnxruntime (23MB), logs de build, o `openapi.json`
capturado do backend e o `contrato.html` (Swagger estático) — tudo binário, gerado ou baixado de
terceiro, e que permanece só na Jetson. Não é código nosso e infla o repositório sem
necessidade (pesos de modelo merecem git-lfs ou um storage separado, não um commit normal).

Também ficaram de fora, por serem resíduo sem uso: `captura.py.bak`, o arquivo vazio `continue`, e
`__pycache__/`.

## Cuidados ao versionar

- `cityrain_config.json` hoje só tem `token: null` (sem segredo real) — quando ganhar o `api_key`
  real do backend, tirar do controle de versão (`.gitignore`) antes de commitar de novo.
- As senhas de WiFi que apareciam no `CLAUDE.md` foram **redigidas** antes do primeiro commit.
  Não reintroduzir credencial em texto puro em nenhum arquivo deste diretório.
- Os `.service` em `systemd/` são cópias de `/etc/systemd/system/` — servem como documentação de
  configuração, não são executados daqui.
