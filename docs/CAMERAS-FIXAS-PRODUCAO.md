# Câmeras fixas para produção — lista pronta para cadastrar no backend

Levantamento de 18/10/2026 (Guilherme). São as câmeras com **posição verificada**, **pluviômetro CEMADEN reportando por
perto** e que **o modelo conhece** (entraram no treino). Links conferidos no YouTube em 18/10 à noite.

## Como cadastrar uma câmera

No backend, cada câmera é um *device* com `tipo = "fixa"`. Registro (precisa da `ADMIN_KEY`, por canal privado):

```bash
curl -X POST "$BACKEND/api/v1/devices/" \
  -H "Authorization: Bearer $ADMIN_KEY" -H "Content-Type: application/json" \
  -d '{"name": "fixa-guaruja_enseada", "tipo": "fixa",
       "latitude": -23.9852, "longitude": -46.2107,
       "stream_url": "https://www.youtube.com/watch?v=v5Y6WsD577M",
       "descricao": "Guarujá — Hotel Palmar, Av. Miguel Estefno 4507, Enseada"}'
```

A resposta traz a **chave do dispositivo** (aparece uma vez só): guardar em `ml/configs/coleta_fixa_tokens.json`
(fora do Git) com a chave = id da câmera (sem o `fixa-`). O coletor manda as fotos com `--enviar`
(`docs/GUIA-COLETA-EQUIPE.md`). Câmera que já existe no banco: atualizar por SQL (exemplos em
`docs/PASSAGEM-camera-fixa.md`). `name` ≤ 100 caracteres; `descricao` ≤ 200.

## Câmeras para cadastrar

| # | `name` | Local (`descricao`) | Latitude | Longitude | `stream_url` (18/10) | Estação CEMADEN mais perto | No ar em 18/10? |
|---|---|---|---|---|---|---|---|
| 1 | `fixa-sp_centro_geolan` | Geolan — Rua Vitória (Vitória Hostel), República, SP | -23.5393 | -46.6408 | https://www.youtube.com/watch?v=CKpA7U_wAbw | AC Central de SP, 0,7 km (3 a ≤2 km) | ✅ (link **novo** desde 15/10; o antigo `dJN7snkYg-I` morreu) |
| 2 | `fixa-guaruja_enseada` | Guarujá — Hotel Palmar, Av. Miguel Estefno 4507, Enseada | -23.9852 | -46.2107 | https://www.youtube.com/watch?v=v5Y6WsD577M | Enseada, 1,5 km | ✅ |
| 3 | `fixa-ubatuba_tenorio` | UBACAM — Praia do Tenório (canto direito), Ubatuba | -23.4653 | -45.0580 | https://www.youtube.com/watch?v=CJGzm3qjFUk | Tenório, 0,2 km (voltou ao ar em 15/10) | ✅ |
| 4 | `fixa-bc_atlantica` | CLIMA BC — Av. Atlântica, Centro, Balneário Camboriú | -26.9930 | -48.6330 | https://www.youtube.com/watch?v=5Xl6pSgiy3A | Monte Alegre, 3,3 km (consenso de 4 a ≤5 km) | ✅ |
| 5 | `fixa-poa_centro_historico` | Porto Alegre Skyline — Caldas Júnior com Andradas, Centro Histórico | -30.0309 | -51.2317 | **https://www.youtube.com/@portoalegreskyline/live** | G2-Centro, 0,4 km | ✅ (a live **muda de link todo dia**: usar a URL do canal `/live`) |
| 6 | `fixa-rs_ponte_bananal` | Saturno Tecnologia — Ponte do Bananal (Rio Caí), Vale Real/Feliz (RS) | -29.4011 | -51.2552 | https://www.youtube.com/watch?v=R1OSBfhaGOA | Vale Real, 1,0 km | ✅ |
| 7 | `fixa-saosebastiao_maresias` | Surfistafotografo — Maresias, torre dos bombeiros, Cond. Ondas, entrada 15 | -23.7909 | -45.5745 | https://www.youtube.com/watch?v=aFvuSy05ki8 | Maresias, 0,9 km | ✅ |
| 8 | `fixa-sv_marinazeus` | Surfistafotografo — Marina Zeus, Av. Saturnino de Brito 315, São Vicente | -23.9779 | -46.3867 | https://www.youtube.com/watch?v=gVMDaagu-b8 | Parque Prainha, 0,3 km | ✅ |
| 9 | `fixa-miracema_praca` | Itanet — Praça Ary Parreiras, Miracema (RJ) | -21.4123 | -42.1971 | https://www.youtube.com/watch?v=BCVoIpECdBs | Centro (Miracema), 30 m | ✅ |
| 10 | `fixa-sbc_riachogrande_2` | Riacho Grande Online cam. 2 — Drogasil, R. Heinrich Nordhoff, Riacho Grande (SBC) | -23.77886 | -46.53075 | https://www.youtube.com/watch?v=8WaOvqdqYmA | Areião, 2,7 km (consenso de 3 a ≤5 km) | ✅ (link muda quando reinicia) |
| 11 | `fixa-sbc_riachogrande_1` | Riacho Grande Online cam. 1 — vista para o Posto Ipiranga, R. Heinrich Nordhoff 61 (SBC) | -23.77756 | -46.52944 | https://www.youtube.com/watch?v=NX7tG-w6wRQ | Areião, 2,5 km (consenso) | ✅ (link muda quando reinicia) |
| 12 | `fixa-sv_itarare` | CVLLP — rampa de voo livre do Morro do Itararé, São Vicente | -23.9647 | -46.3626 | ⚠️ `ukoSyGLdoTQ` virou **privado** | Nova Cintra, 2,1 km (consenso) | ❌ fora do ar em 18/10 — cadastrar como inativa até voltar |
| 13 | `fixa-sp_santoamaro_largo13` | São Paulo com Regiane — R. Barão do Rio Branco com Av. Mário Lopes Leão, Santo Amaro | -23.65107 | -46.70911 | ⚠️ última: `JB2qiaZfOIw` (encerrada) | Santo Amaro Paulista, 0,1 km | ❌ live intermitente: volta com link novo |

**Onde achar o link novo quando a live reinicia** (abrir a aba de transmissões do canal e pegar a que está "AO VIVO"):

| Câmera | Canal |
|---|---|
| sp_centro (Geolan) | https://www.youtube.com/channel/UC4evRUjdKbPTBvNClkZaCAg/streams |
| Guarujá, Maresias, Marina Zeus (Surfistafotografo) | https://www.youtube.com/channel/UCGJaqUeVWMrxawXUhCK2wPw/streams |
| Tenório (UBACAM) | https://www.youtube.com/channel/UCVQG1pBkRM4xlRrBmV65kUw/streams |
| BC (CLIMA BC Brazil) | https://www.youtube.com/channel/UCi1vQx48j_nfrMg6XH5PItQ/streams |
| POA (Porto Alegre Skyline) | https://www.youtube.com/@portoalegreskyline/live (já resolve sozinha) |
| rs_ponte (Saturno Tecnologia) | https://www.youtube.com/channel/UCOChNEks-A79lRWlI8uwhdA/streams |
| Miracema (Itanet) | https://www.youtube.com/channel/UCurXkCBYXFJOtDFrz3LKAFg/streams |
| Riacho Grande 1 e 2 | https://www.youtube.com/channel/UCKy0WuvgxyCwFCauBC0WG7Q/streams ("AO VIVO 1-" e "AO VIVO 2-") |
| Santo Amaro (São Paulo com Regiane) | https://www.youtube.com/channel/UCcHFc7ONlYeqA3p4zqRTw5A/streams |

## NÃO cadastrar (ou desativar se já existem)

| Câmera | Motivo |
|---|---|
| `fixa-santos_gonzaga`, `fixa-praiagrande_boqueirao` (já existem no banco) | posição não verificada (o rótulo muda dentro da área possível); Santos saiu do ar. **Desativar** (`DELETE /api/v1/devices/{id}` = desativa) |
| Paulista (Rádio TV CDL) | a live alterna com o estúdio (pessoas na imagem) |
| Congonhas 1–3, Riacho Grande 3 | prédio/posição não confirmados |
| Perequê-Açu, Baguari, Taboão, Guarapuava | posição só aproximada (ou live encerrada) |

## Sobre o modelo

O modelo trocado no PR (F2 + perda ordinal, treinado **sem a BC**) entrou no treino com as câmeras 1–3 e 5–13; a BC é
"câmera nova" para ele (é onde o checador mede). Em câmera nunca vista o desempenho é bem menor — para incluir uma câmera
nova de verdade, ela precisa primeiro ser coletada e entrar no treino. A classe "moderada" tem acerto baixo em câmera
nova; para o painel, tratar moderada/forte como "chuva intensa provável".
