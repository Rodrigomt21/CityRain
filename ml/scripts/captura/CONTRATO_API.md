# Contrato — upload de frame CityRain (Jetson → backend)

**Atualizado em 2026-09-15** pra bater com o `openapi.json` real do backend
(`https://api-production-046f.up.railway.app`) e com o gate binário chuva/não-chuva já treinado
e integrado no `uploader.py` (`gate.py` + `~/modelo_chuva/detector.py`). Substitui o rascunho
anterior (schema aninhado em `gps{}`, sem `weather_label`) — ver
`MUDANCAS_NECESSARIAS_BACKEND.md` pros pontos que ainda dependem de resposta do Guilherme.

## Requisição — caso "chuva" (implementado e testado contra `mock_backend.py`)

```
POST {backend_url}      (hoje: placeholder http://127.0.0.1:8080/upload — trocar quando tiver URL real)
Authorization: Bearer {token}      (se token estiver configurado; ausente = sem header)
Content-Type: multipart/form-data
```

Campos do multipart:

| Campo      | Tipo         | Descrição                                              |
|------------|--------------|---------------------------------------------------------|
| `image`    | arquivo JPEG | O frame capturado (`frame_<timestamp>.jpg`)             |
| `metadata` | string (JSON, achatado — ver abaixo) | Montado pelo `uploader.py` a partir do `.json` local + resultado do gate |

### Formato de `metadata` enviado ao backend (achatado, bate com `Body_ingest_capture_api_v1_ingest_post`)

```json
{
  "captured_at": "2026-09-05T18:11:54.306881+00:00",
  "latitude": null,
  "longitude": null,
  "source_type": "jetson_nano",
  "weather_label": "chuva",
  "confidence": 0.9966566562652588
}
```

- `weather_label`/`confidence` vêm do gate binário rodando **na própria Jetson** (`gate.py`),
  não são inventados: `"chuva"` = classe `com_gota` do modelo, `"seco"` = `sem_gota` (ver seção
  seguinte). **Atenção**: o dashboard usa um enum de 4 classes (`seco/garoa/moderado/forte`) — o
  gate hoje só sabe dizer `chuva`/`seco`, não a intensidade. Ver `MUDANCAS_NECESSARIAS_BACKEND.md`
  item 2, ainda sem resposta do Guilherme sobre quem preenche garoa/moderado/forte.
- `latitude`/`longitude` podem vir `null` se o `gps.service` não tiver fix — **ainda não
  confirmado com o Guilherme se o backend aceita nulo aqui** (ver `MUDANCAS_NECESSARIAS_BACKEND.md`).
- O `.json` local (schema interno, gravado pelo `captura.py`) continua tendo mais campos
  (`schema`, `device_id`, `arquivo`, `gps` completo) — esses ficam só na Jetson, não vão pro
  backend; o `uploader.py` extrai só o que o contrato pede.

## Caso "seco" — **ainda não implementado contra o backend, é esqueleto**

Quando o gate classifica `sem_gota`, o `uploader.py` **não envia a foto** (economiza banda —
esse é o motivo do gate existir) e move o par pra `~/frames/sem_chuva_pendente/` em vez de
enviar ou apagar. Isso é intencional e temporário: **não existe hoje um endpoint no backend pra
avisar "sem chuva" sem mandar imagem** (`POST /api/v1/ingest` exige `image`). Ver
`MUDANCAS_NECESSARIAS_BACKEND.md` item 1 — assim que o Guilherme confirmar o formato (endpoint
novo ou `image` opcional), trocar a função `move_para_pendente_seco()` por uma chamada de
verdade.

## Resposta esperada (caso "chuva")

| Código      | Significado pro uploader                                                        |
|-------------|-----------------------------------------------------------------------------------|
| `2xx`       | Recebido e persistido. O uploader **apaga** o par jpg+json local.                |
| `4xx`       | Payload rejeitado (schema errado, auth inválida, etc). O uploader **mantém** o par na fila e loga com destaque — indica que o contrato precisa de ajuste, não que a rede caiu. |
| `5xx` / timeout / erro de rede | Falha transitória. O uploader **mantém** o par na fila e tenta de novo depois (backoff exponencial 5s → 300s). |

Importante pro Guilherme: **nunca** responder 2xx antes de persistir de fato — é o sinal que a
Jetson usa pra apagar o único registro daquele frame.

## Ainda em aberto (ver `MUDANCAS_NECESSARIAS_BACKEND.md` pro texto completo pra mandar ao Guilherme)

1. Endpoint/variante pro caso "seco" sem imagem.
2. Quem gera `garoa`/`moderado`/`forte` — o gate da Jetson só é binário.
3. Formalizar `weather_label`/`confidence`/demais campos como schema tipado (hoje só texto livre).
4. Token admin (`HTTPBearer`) pra registrar o device e conseguir a `api_key` real.
