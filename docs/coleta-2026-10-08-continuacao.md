# Continuação da coleta — 08/10/2026, noite

## Resultado

- Confirmados 18.411 pares JPG/JSON da coleta anterior; todos os JPEGs legíveis.
- Recuperação DVR desde 08/10 às 20:00 UTC: 91 frames de SP (21:40–23:10 UTC) e 231 de Praia Grande (20:00–23:50 UTC). As demais fontes não tinham janelas de chuva no intervalo com as leituras disponíveis.
- Uma rodada atual das seis câmeras concluída às 23:12–23:13 de Brasília (09/10, 02:12–02:13 UTC).
- Incorporados 166 frames novos; 162 duplicatas exatas ignoradas por SHA-256, por câmera. Conferidos JPEG e hash dos novos arquivos. Nenhum original substituído.
- Acervo resultante: **18.577 pares** em `ml/data/raw/coleta_fixa/` (inclui cinco frames antigos de duas fontes atualmente desativadas).
- Busca de seco confirmado desde 20:00 UTC não encontrou novas janelas. Isso não significa que choveu em todas as câmeras.

## Estações e rótulos

Obtidas oito respostas novas para 06–07/10. O CEMADEN depois retornou nove HTTP 401 por limite de acesso; não foi possível completar 08/10. CSV consolidado: 9.101 leituras, 27 estações, último registro em 08/10 23:50 UTC. Arquivos já presentes foram reutilizados pelo script; a cobertura do dia corrente continua parcial.

Os dois manifests foram regenerados com as regras existentes, sem mudar limiares:

| Manifest | Seco | Garoa | Moderada | Forte | Sem rótulo |
|---|---:|---:|---:|---:|---:|
| Principal, 2 km + consenso | 1.061 | 5.771 | 69 | 0 | 11.676 |
| Complementar, 5 km | 1.347 | 8.818 | 558 | 15 | 7.839 |

**Não somar as linhas:** são duas rotulagens do mesmo acervo. Pelo CF3.2, somente moderada/forte do complementar podem entrar no treino, após revisão. Os frames atuais sem cobertura meteorológica não receberam rótulos inventados.

## Artefatos locais

- 18 painéis com 332 frames amostrados e planilha de revisão: `ml/data/review/camera_fixa/`. Revisão humana de câmera tampada/congelada/offline ainda pendente; nenhum frame foi marcado como aprovado automaticamente.
- Backup dos manifests anteriores: `ml/data/review/backup_antes_continuacao_20261008/`.
- Contagens, consolidação e logs de captura: `ml/data/review/continuacao_20261008/`.
- Downloads separados preservados: `ml/data/raw/coleta_fixa_continuacao_20261008/` (não usar como segundo dataset; os novos já foram incorporados ao acervo principal).

## Retomada

1. Revisar os painéis e preencher `revisao.csv` somente para defeitos de imagem, sem mudar classes visualmente.
2. Completar leituras de 08/10 quando a cota CEMADEN permitir. O script pula respostas existentes, inclusive dias parciais; a atualização de dias incompletos exige preservar o cache antigo e reconsultar os pares necessários. `--forcar` reconsulta negativas, mas não substitui respostas positivas já existentes.
3. Próxima colheita prevista no guia: 11/10. A coleta desta execução foi finita; não ficou coletor contínuo nem agendamento ativo.
4. Santos e Praia Grande continuam com posição aproximada; os metadados antigos de Praia Grande incluem a posição anterior à troca de live e foram preservados.
5. Seguir `PASSAGEM-camera-fixa.md` para splits, experimentos e exportação. Nenhum treinamento, envio de frames ao backend, commit ou deploy foi realizado nesta continuação.

## Coleta contínua ativada após a rodada

A pedido do Rodrigo, iniciada em 08/10 às 23:22 (Brasília): seis câmeras, um frame por câmera a cada 600 segundos, armazenamento local em `ml/data/raw/coleta_fixa/`. Sem envio ao backend e sem treinamento. Log em `ml/data/raw/coleta_fixa/coletor_continuo_20261008.log`; PID inicial do coletor 39559, registrado no arquivo `.pid` adjacente. `caffeinate -i` impede repouso por inatividade enquanto o processo estiver ativo; desligamento, fechamento da tampa ou encerramento da sessão/processo podem interromper a coleta. Não há serviço de reinício automático instalado.

Esta ativação substitui a observação anterior de que nenhum coletor ficou ativo. Os manifests descrevem a rodada concluída; os frames contínuos novos precisam ser rotulados após obter as leituras correspondentes.
