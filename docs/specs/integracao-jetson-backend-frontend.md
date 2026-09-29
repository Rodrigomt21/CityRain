# CityRain — integração Jetson, backend e dashboard

Data: 28/09/2026. Documento para alinhamento e execução pela equipe.

**Situação:** o gate da Jetson detecta chuva, mas não estima intensidade. O uploader ainda envia `weather_label="chuva"`, que a API rejeita. A solução escolhida é separar detecção (`rain_detected` e `detection_confidence`) de intensidade (`weather_label` e `confidence`). A implementação foi interrompida e ainda não está pronta para deploy.

## 1. O que foi verificado

Inspeção local dos arquivos em 28/09/2026 e recuperação do histórico da sessão anterior. Não houve novo teste de produção ou acesso à Jetson nesta revisão.

| Item | Estado e evidência |
|---|---|
| Rejeição de chuva | A sessão anterior registrou HTTP 400: `weather_label deve ser um de: ['seco', 'garoa', 'moderado', 'forte']`, ao enviar `chuva` com confiança 0,9746. É evidência histórica, não teste repetido nesta revisão. |
| Upload sem imagem | Já existe no backend local atualizado: `media_service.py` grava `seco` e `confidence=null` quando não há imagem. Não é necessário pedir um endpoint novo. |
| Registro do dispositivo | Concluído segundo a sessão anterior. Confirmar validade da credencial no ensaio; não é necessário pedir um novo cadastro de saída. |
| Separação dos campos | Iniciada no worktree `code/CityRain-backend`, branch `fix/rain-detected`. Há alterações locais apenas em `backend/app/models/capture.py` e `backend/app/schemas/capture.py`. |
| Backend incompleto | O serviço de ingestão ainda exige intensidade com imagem e não persiste os novos campos. Existem apenas as migrations `0001` e `0002`; falta a migration desta mudança. O rascunho não deve ser publicado nesse estado. |
| Jetson incompleta | `ml/scripts/captura/uploader.py` ainda envia `weather_label/confidence` do gate; os secos vão para `sem_chuva_pendente/`. |
| GPS | O serviço de ingestão exige coordenadas numéricas válidas; `null` é rejeitado. O uploader ainda pode enviar nulos quando não há fix. |
| Frontend | Os hooks `useRainfallData.js` e `useClassificationData.js` usam simulação. O segundo importa `../utils/categories`, caminho ausente neste checkout; a definição está em `src/lib/categories.js`. Conferir os imports e o build ao integrar. |
| Agregação H3 | O backend já converte label nulo em `labels.unknown`, mas ainda não agrega detecção separadamente. |

Os arquivos antigos `CONTRATO_API.md` e `MUDANCAS_NECESSARIAS_BACKEND.md` descrevem a situação de 15/09. Para as pendências atuais, este documento prevalece. A spec de pipeline continua útil para confiabilidade da coleta, mas suas pendências de cadastro e endpoint seco precisam ser lidas com as correções acima.

## 2. Contrato a implementar

**Contrato alvo, ainda não disponível de ponta a ponta.** Manter `POST /api/v1/ingest`, autenticação Bearer e formulário multipart com `metadata` como string JSON e `image` opcional. Validar o JSON internamente por schema tipado; não basta alterar apenas a descrição do OpenAPI.

| Campo de metadata | Regra |
|---|---|
| `captured_at` | Data/hora ISO 8601 com fuso; normalizar em UTC. |
| `latitude`, `longitude` | Números finitos nos intervalos −90 a 90 e −180 a 180. Sem fix, preservar localmente e separar da fila apta a upload; não inventar coordenadas nem usar a posição atual para um frame antigo. |
| `source_type` | `jetson_nano` para esta placa. |
| `rain_detected` | Booleano do gate. `null` em registros legados cuja detecção não foi registrada. |
| `detection_confidence` | Número finito entre 0 e 1, obrigatório quando há `rain_detected`. Definir e testar se `probabilidade` retornada pelo detector é da classe escolhida ou de chuva antes de fazer a conversão; o nome do campo sozinho não resolve isso. |
| `weather_label` | Classe de intensidade: `seco`, `garoa`, `moderado`, `forte`; nulo quando não existe classificação de intensidade. Nunca enviar `chuva` nesse campo. |
| `confidence` | Confiança da classificação de intensidade, entre 0 e 1; nula quando a intensidade não foi classificada. Não copiar a confiança do gate para cá. |

### Chuva detectada, intensidade ainda desconhecida

Enviar JPEG e metadata como o exemplo abaixo (coordenadas e confiança ilustrativas):

```json
{
  "captured_at": "2026-09-28T18:00:00Z",
  "latitude": -23.65,
  "longitude": -46.57,
  "source_type": "jetson_nano",
  "rain_detected": true,
  "detection_confidence": 0.97,
  "weather_label": null,
  "confidence": null
}
```

Exibição: **“Chuva detectada · intensidade não medida”**. Não mapear para garoa, moderada, forte ou um valor em mm/h.

### Sem chuva detectada

Enviar metadata com `rain_detected=false` e confiança do gate, sem JPEG. Preservar a convenção existente do backend: `weather_label="seco"`, `confidence=null`. Isso representa a decisão do gate, não uma medição pluviométrica de 0 mm/h.

No fluxo novo, ausência de imagem sozinha não pode transformar `rain_detected=true` em seco: rejeitar a combinação. Manter explicitamente a compatibilidade do fluxo legado sem imagem e sem campos de detecção durante a transição.

### Intensidade futura e registros antigos

Quando houver modelo de intensidade validado, preencher `weather_label/confidence` com a saída dele. Os campos de detecção mantêm sua própria origem. Preservar clientes legados com imagem e classe de intensidade válida; não preencher retroativamente confiança de detecção sem evidência.

No banco, adicionar colunas de detecção nullable e permitir `weather_label` nulo. Manter as quatro classes existentes; não criar uma quinta intensidade fictícia. O texto de interface pode ser “Moderada”, mas o valor da API é `moderado`.

## 3. Trabalho por frente

Distribuição confirmada por Rodrigo: Rodrigo e Guilherme na Jetson e nos modelos; Gabriel no backend; Paulo no frontend.

### Gabriel — backend e publicação da API

- Concluir `MediaService.ingest`: validar e persistir os campos novos nos caminhos com e sem imagem; manter compatibilidade legada e rejeitar combinações contraditórias.
- Completar validação tipada, inclusive vínculo entre cada resultado e sua confiança. Atualizar respostas, documentação e filtros de captura para consultar detecção e intensidade desconhecida.
- Criar migration após `0002_confidence_nullable`; testar em PostgreSQL com dados existentes. Planejar rollback sem converter intensidade desconhecida em seco. Não executar downgrade que exija `NOT NULL` enquanto houver nulos sem uma estratégia explícita.
- Adaptar agregação H3 e schema de resposta para contagens de detecção. Manter `labels.unknown` para intensidade ausente; não confundir desconhecido com seco.
- Tratar idempotência do fluxo sem foto: atualmente não existe deduplicação por SHA nesse caminho. Definir uma chave estável de evento para que retry não duplique secos nas estatísticas.
- Confirmar branch de deploy e acesso ao Railway/PostgreSQL, publicar após validação e informar o contrato disponível ao restante do time.

O patch local pode ser concluído no repositório. Publicação, verificação do banco de produção e confirmação do branch configurado dependem do acesso ao ambiente; não foram feitas nesta revisão.

### Paulo — frontend

- Substituir a simulação dos hooks pelo consumo da API, incluindo autenticação, carregamento, erro e ausência de dados. Corrigir imports existentes e validar o build.
- Criar adaptador explícito: `seco → dry`, `garoa → drizzle`, `moderado → moderate`, `forte → heavy`. Tratar nulo antes de chamar funções de categoria.
- Mostrar chuva detectada sem intensidade em estado próprio, visualmente distinto de seco e de ausência de dados. Mostrar detecção legada desconhecida como desconhecida.
- Corrigir `getCategory` e `getMostSevereCategory`: hoje o fallback é seco; valores ausentes ou conjuntos vazios não comprovam tempo seco. Em JavaScript, `null` também pode ser convertido a zero nas comparações.
- Adaptar mapa, legenda, tabela, cartões e alertas. Só disparar alerta de intensidade forte com classificação que sustente isso; detecção binária sozinha não basta.
- Não preencher gráficos/KPIs em mm/h a partir de categorias ou do gate. Exibir “não medido” quando não existir uma medida ou estimativa quantitativa validada.
- Usar `labels.unknown` da agregação como intensidade desconhecida. Se uma célula tiver observações conhecidas e desconhecidas, mostrar ambas as contagens; não ocultar a incompletude em uma única cor sem legenda.

**Limiar divergente:** `src/lib/categories.js` usa 0,1/5/25 mm/h; `docs/plano-dataset.md` usa seco=0, garoa até 2,5, moderada até 10 e forte acima de 10. Para classes vindas da API, usar o mapeamento de rótulos, sem recalcular por mm/h inventado. Se houver dados quantitativos reais no dashboard, alinhar os cortes e suas fronteiras com a frente de ML e documentar a política escolhida.

### Rodrigo/Guilherme — Jetson, coleta e ensaio integrado

- Ajustar o uploader para os novos campos, mantendo leitura dos metadados antigos e separando a confiança do gate da intensidade.
- Implementar o envio de secos sem foto e reprocessar `sem_chuva_pendente/` de forma controlada, com chave de evento estável conforme contrato do backend.
- Separar capturas sem GPS válido para não bloquear toda a fila e não perder dados úteis ao acervo.
- Preservar os pares locais no modo de coleta. Um 2xx de metadata seca não significa que a foto foi copiada para o servidor.
- Atualizar contrato, mock e testes do uploader; configurar a URL completa de ingestão e a credencial já registrada após confirmação de compatibilidade da API.
- Validar sincronização de horário e serviços na placa. O restart que pede senha deve ser executado em terminal interativo: `ssh -t jetson "sudo systemctl restart gps.service"`.
- Concluir as verificações de energia, armazenamento e cópia de segurança da spec de pipeline antes do ensaio de campo. Esta documentação de integração não certifica a placa como pronta para coleta.

### Rodrigo/Guilherme — ML

O modelo de intensidade continua sendo entrega separada. O gate atual não permite prometer garoa/moderada/forte nem mm/h. Validar os cortes do dataset e o modelo antes de ativar essas saídas; registrar versão e significado das probabilidades.

## 4. Ordem e critérios de aceite

1. Fechar validação, compatibilidade e formato das contagens H3 entre backend e frontend.
2. Concluir backend e migration, testar em PostgreSQL e testar os consumidores com nulos antes de publicar.
3. Integrar frontend e uploader em ambiente de teste. Publicar API compatível antes de ativar o payload novo na Jetson.
4. Validar uma chuva, um seco, um legado e um frame sem fix; só então liberar o processamento da fila preservada.

| Teste | Resultado exigido |
|---|---|
| JPEG + detecção positiva, intensidade nula | 2xx após persistência; leitura devolve os campos; dashboard mostra intensidade não medida. |
| Metadata seca sem JPEG | Registro persistido sem mídia; detecção negativa; `seco` com confiança de intensidade nula. |
| Detecção positiva sem JPEG no fluxo novo | Rejeição clara; não registrar seco silenciosamente. |
| Payload legado com imagem e classe válida | Continua aceito; nenhuma confiança de detecção inventada. |
| Coordenadas nulas ou inválidas | Rejeição controlada na API; cópia local preservada e fila restante avança. |
| Retry após perda de resposta | Não duplica capturas, inclusive sem foto; não apaga dado antes de confirmação. |
| Célula H3 com intensidade desconhecida | Contagem preservada, sem renderização automática como seco. |
| Migration sobre base existente | Dados preservados, inserção/leitura novas funcionando e rollback documentado. |
| Falha 4xx/5xx ou queda de rede | Dado local preservado; falha observável e retomada testada. |

**Ainda não executado nesta revisão:** migration em PostgreSQL, build do frontend, testes do patch, deploy, reinício de serviços e ensaio ponta a ponta. A entrega desta revisão é a documentação conferida contra o código local; não uma certificação de funcionamento em produção.

## 5. Referências no repositório

- Worktree backend: `code/CityRain-backend`, branch `fix/rain-detected`.
- Backend: `app/models/capture.py`, `app/schemas/capture.py`, `app/services/media_service.py`, `app/services/capture_service.py`, `app/services/geo_service.py`, `app/schemas/stats.py` e `alembic/versions/` (relativos a `backend/`).
- Jetson: `ml/scripts/captura/uploader.py` e `gate.py`.
- Frontend: `frontend/src/lib/categories.js`, `frontend/src/hooks/useRainfallData.js` e `useClassificationData.js`.
- Coleta: [spec de pipeline](spec-pipeline-jetson.md).
- Modelagem: [plano de dataset](../plano-dataset.md).
