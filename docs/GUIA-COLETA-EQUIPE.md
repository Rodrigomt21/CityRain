# Coleta das câmeras fixas — guia para a equipe no feriado

**Período: 09 a 12/10/2026.** Rodrigo estará viajando. A prioridade é salvar as imagens que ainda estão no DVR, obter as leituras dos pluviômetros quando disponíveis e guardar tudo para revisão. Não é preciso treinar modelos para fazer essa parte.

## 1. Combinem quem assume cada tarefa

| Tarefa | Responsável a combinar | Entrega |
|---|---|---|
| Rodar o coletor e recuperar o DVR | Uma pessoa com computador ligado e internet | Pares JPG + JSON, por câmera |
| Baixar CEMADEN e rotular | Uma pessoa com acesso ao PED | CSV das estações e os dois manifests |
| Revisar imagens defeituosas | Uma pessoa da equipe | `revisao.csv` preenchido e painéis preservados |
| Reunir e compartilhar os arquivos | Uma pessoa da equipe | Pacote com data, resumo e checksum |

Uma pessoa pode fazer mais de uma tarefa. Evitem dois responsáveis baixando a mesma câmera/período na mesma pasta ao mesmo tempo.

## 2. Estado deixado em 08/10

- Rodada consolidada: **18.577 pares JPG/JSON**, com manifests atualizados. A coleta contínua gera arquivos adicionais depois desse fechamento.
- Seis câmeras ativas: `sp_centro_geolan`, `santos_gonzaga`, `praiagrande_boqueirao`, `guaruja_enseada`, `ubatuba_tenorio`, `bc_atlantica`.
- **Não há cobertura completa de cinco dias.** Há lacunas de imagens e leituras; quantidade de fotos não comprova cobertura temporal.
- CEMADEN: 9.101 leituras de 27 estações; limite de acesso impediu completar 08/10. Não tratar ausência de leitura como tempo seco.
- 18 painéis / 332 imagens para revisão já foram gerados no Mac do Rodrigo; ainda precisam de revisão humana.
- Coletor local iniciado no Mac do Rodrigo em 08/10 às 23:22, a cada 10 minutos, **sem envio ao dashboard**. Depende do Mac ligado/com internet; não reinicia automaticamente. A equipe deve assumir em outra máquina se esse Mac ficar indisponível.
- Tentativa adicional de recuperar cinco dias foi **interrompida a pedido do Rodrigo**: 79 pares ficaram em `ml/data/raw/recuperacao_5dias_20261008/`, fora dos manifests. Não estão aprovados nem incorporados ao acervo principal.
- Santos e Praia Grande ainda têm posição aproximada; o split configurado exige posição verificada. Não marcar `posicao_verificada: true` sem conferir. Parte do histórico de Praia Grande é de uma live/posição anterior: preservar URL e coordenadas originais de cada JSON.

Detalhes da rodada: [coleta-2026-10-08-continuacao.md](coleta-2026-10-08-continuacao.md). Backend, frontend e treino: [PASSAGEM-camera-fixa.md](PASSAGEM-camera-fixa.md).

## 3. Preparar outro computador

Comandos abaixo para **Mac ou Linux/WSL**, no terminal, dentro da raiz `CityRain/`. No Windows, usar WSL com Ubuntu. Instalar Python 3.11 e FFmpeg antes de começar (`brew install python@3.11 ffmpeg` no Mac; no Linux, usar o gerenciador da distribuição).

Quem ainda não tem o repositório:

```bash
git clone https://github.com/Rodrigomt21/CityRain.git
cd CityRain
```

Quem já tem: atualizar o código preservando alterações locais. Os documentos e manifests desta continuação ainda precisam ser compartilhados ou publicados no Git; não presumir que um clone já os contém.

```bash
python3.11 -m venv ml/.venv
source ml/.venv/bin/activate
python -m pip install -r ml/requirements-ci.txt yt-dlp
python --version
yt-dlp --version
ffmpeg -version
```

Depois de ativar o ambiente, `python` e `yt-dlp` devem ser os de `ml/.venv/bin`. Isso importa: os scripts chamam `yt-dlp` pelo PATH.

**Para coletar imagens das lives não é necessário token do backend nem conta CEMADEN.** Para obter as leituras, é necessário cadastro autorizado no PED. Para trabalhar com o acervo anterior, também receber as pastas de dados do Rodrigo: o Git não inclui imagens nem a pasta de revisão.

## 4. Primeiro teste e coleta contínua

Teste uma rodada antes de deixar rodando:

```bash
python -u ml/scripts/coleta_fixa/coletor.py ml/configs/coleta_fixa.yaml --uma-rodada
```

Esperado: uma linha por câmera com nome `frame_...jpg` ou uma falha explícita. Os arquivos saem em `ml/data/raw/coleta_fixa/<camera>/`, sempre JPG + JSON. Verificar a imagem e o campo `capturado_em_utc` no JSON.

Depois, no Mac:

```bash
caffeinate -i python -u ml/scripts/coleta_fixa/coletor.py ml/configs/coleta_fixa.yaml --intervalo-s 600
```

No Linux/WSL:

```bash
python -u ml/scripts/coleta_fixa/coletor.py ml/configs/coleta_fixa.yaml --intervalo-s 600
```

Manter terminal aberto, computador ligado e internet. No notebook, tampa aberta; evitar suspensão nas configurações. `Ctrl+C` encerra o coletor. Não iniciar outra cópia na mesma pasta. Nenhum desses comandos instala serviço de boot ou agenda rodadas futuras.

**Dashboard é outra opção:** acrescentar `--enviar` somente se o responsável tiver os tokens dos dispositivos, recebidos por canal privado. Os tokens ficam em `ml/configs/coleta_fixa_tokens.json`, fora do Git. Sem `--enviar`, o sucesso da coleta é visto nos arquivos locais, não no site.

## 5. Recuperar o passado: começar em 09/10

O DVR depende da live e pode guardar menos que 120 horas. Lives reiniciadas/trocadas podem não oferecer os dias anteriores. Começar pelo histórico mais antigo **em 09/10**, sem esperar 11/10. Depois repetir a colheita em 11/10; a sequência planejada é 13, 15, 17 e fechamento em 18/10.

### 5.1 Com leituras CEMADEN disponíveis

Configurar `ml/.env` localmente (não enviar esse arquivo junto dos dados):

```dotenv
CEMADEN_EMAIL=seu_email_do_cadastro
CEMADEN_SENHA=sua_senha_do_cadastro
```

No dia 09/10, começar pelos dias completos de 04 a 08/10:

```bash
python -u ml/scripts/estacoes/baixar_cemaden_ped.py --dias 2026-10-04 2026-10-05 2026-10-06 2026-10-07 2026-10-08
```

No dia 11/10, pedir 09 e 10/10 e quaisquer dias anteriores ainda incompletos. Solicitar o próprio dia produz dados parciais.

Se aparecer **401 / limite de acessos**, parar as tentativas repetidas e registrar estação/dia pendentes. Coletar imagens continua sendo possível pela seção 5.2. Não trocar contas para contornar a cota.

**Atenção ao cache:** o script pula respostas positivas que já existem, mesmo se foram baixadas antes de acabar o dia. `--forcar` reconsulta negativas, mas não atualiza esses arquivos positivos. Para atualizar um dia parcial, o responsável deve preservar uma cópia do bruto, retirar somente os pares estação/dia identificados da pasta de cache e reconsultar quando a cota permitir. Se a atualização falhar, restaurar o bruto preservado e regenerar o CSV. Não apagar o cache inteiro; arquivos estão em `ml/data/raw/estacoes/respostas_brutas/cemaden_ped/`.

Com CSV atualizado, recuperar chuva e amostras secas:

```bash
python -u ml/scripts/coleta_fixa/recuperar_dvr.py --onde-choveu --desde 2026-10-04T00:00:00-03:00
python -u ml/scripts/coleta_fixa/recuperar_dvr.py --modo-seco --passo-s 300 --desde 2026-10-04T00:00:00-03:00
```

Esses modos limitam a busca ao DVR disponível. Nas rodadas seguintes, ajustar `--desde` à janela pendente, preservando sobreposição se o dia anterior estava incompleto. **Zero janelas significa apenas que não houve janela elegível com os dados disponíveis; não prova ausência de chuva.**

### 5.2 Sem leituras: recuperar imagens mesmo assim

Salvar uma imagem a cada dez minutos, sem atribuir classe. Isso evita perder o histórico enquanto a estação está indisponível.

Primeiro conferir o início disponível da live. No comando abaixo, trocar o ID pela câmera desejada:

```bash
python - <<'PY'
import sys
from datetime import timedelta
from pathlib import Path
import yaml
sys.path.insert(0, 'ml/scripts/coleta_fixa')
from coletor import carregar_fontes
from recuperar_dvr import StreamDVR
camera = 'ubatuba_tenorio'
cfg = yaml.safe_load(Path('ml/configs/coleta_fixa.yaml').read_text())
f = next(f for f in carregar_fontes(cfg) if f.id == camera)
d = StreamDVR(f.url)
print('Início conservador UTC:', max(d.inicio, d.head_t - timedelta(hours=119)).isoformat())
print('Fim disponível UTC:', d.head_t.isoformat())
PY
```

Usar `--de` dentro dessa faixa e `--ate` anterior ao fim disponível. **Exemplo de sintaxe**, só executar se a faixa impressa incluir esse intervalo:

```bash
python -u ml/scripts/coleta_fixa/recuperar_dvr.py --fonte ubatuba_tenorio --de 2026-10-07T00:00:00-03:00 --ate 2026-10-08T00:00:00-03:00 --passo-s 600
```

Repetir para os intervalos/câmeras faltantes, do mais antigo para o mais recente. Os IDs estão na seção 2. A estimativa de DVR não garante que todos os segmentos ainda existam; anotar erros. Não insistir em intervalos anteriores ao início da live.

Prioridades observadas no inventário de 08/10: Praia Grande sem imagens em **07/10 UTC**; Ubatuba e BC com pouquíssimas imagens em **08/10 UTC**. Essas datas são UTC (Brasília = UTC−3), não rótulos meteorológicos. Santos/Praia Grande trocaram links; o histórico da live nova pode não alcançar todo o período.

## 6. Atualizar manifests e fazer a revisão

Executar depois de reunir JPG/JSON e atualizar as estações. Fazer backup dos manifests e do `revisao.csv` existentes antes de regenerar. Se estão em máquinas diferentes, consolidar o acervo primeiro; não concatenar CSVs cegamente.

```bash
python ml/scripts/rotulagem/gerar_manifest.py --config ml/configs/rotulagem_coleta_fixa.yaml
python ml/scripts/rotulagem/gerar_manifest.py --config ml/configs/rotulagem_coleta_fixa_5km.yaml
python ml/scripts/dataset/paineis_revisao_fixa.py --manifest ml/data/manifests/manifest_coleta_fixa.csv --manifest ml/data/manifests/manifest_coleta_fixa_5km.csv
```

Abrir os painéis de `ml/data/review/camera_fixa/` e preencher `revisao.csv`: `excluir=1` e motivo apenas para defeitos como tela offline, câmera tampada ou transmissão errada. Para suspeita de congelamento, comparar frames de horários diferentes. Não mudar a classe olhando a imagem; pista molhada não prova chuva ativa.

**Gerar a planilha não é revisar.** Registrar nome do revisor, data e grupos câmera/classe efetivamente inspecionados em um `REVISAO.md` junto da planilha. Há uma limitação atual: o gerador de splits reconhece a existência de linhas do CSV como revisão; por isso não rodar splits/treino antes de a pessoa terminar e registrar a inspeção. Não alterar rótulos nem aprovar grupos automaticamente para passar essa condição.

O manifest de 5 km é complementar: somente moderada/forte podem ser aproveitadas no treino, após revisão, conforme CF3.2. Não somar contagens dos dois manifests — são os mesmos frames sob regras diferentes.

## 7. Compartilhar o resultado

Antes de empacotar, parar o coletor da máquina com `Ctrl+C`, conferir os últimos pares e regenerar manifests. Reiniciar o coletor depois do pacote, se desejado. Assim o pacote e os CSVs representam o mesmo fechamento.

Incluir:

- `ml/data/raw/coleta_fixa/`: JPG e JSON juntos;
- `ml/data/raw/estacoes/normalizado/`: leituras usadas na rotulagem;
- `ml/data/manifests/`: manifests e relatórios;
- `ml/data/review/camera_fixa/`: painéis, CSV e registro da revisão;
- configurações públicas de coleta e rotulagem;
- um resumo com commit do código, datas UTC, responsável, falhas, câmeras/intervalos pendentes e revisão feita ou pendente.

Se os frames não chegaram por transferência, o clone do Git sozinho não resolve. Para treinar depois, também será necessário o dataset `ml/data/processed/ircnn/`, o manifest correspondente e os demais pré-requisitos do plano C; o pacote abaixo é da **coleta fixa**, não de todos os experimentos.

Exemplo para um fechamento em 11/10, depois da revisão e da geração dos arquivos:

```bash
git rev-parse HEAD
# Copiar o hash acima para o resumo da entrega.
tar --exclude='*.log' --exclude='*.pid' --exclude='*.tmp' -czf ../cityrain-coleta-20261011.tar.gz ml/data/raw/coleta_fixa ml/data/raw/estacoes/normalizado ml/data/manifests ml/data/review/camera_fixa ml/configs/coleta_fixa.yaml ml/configs/rotulagem_coleta_fixa.yaml ml/configs/rotulagem_coleta_fixa_5km.yaml docs/GUIA-COLETA-EQUIPE.md
```

Verificar conteúdo com `tar -tzf ../cityrain-coleta-20261011.tar.gz`. No Mac, checksum com `shasum -a 256 ../cityrain-coleta-20261011.tar.gz`; no Linux, `sha256sum ../cityrain-coleta-20261011.tar.gz`. Enviar o hash junto do arquivo. **Não incluir `.env`, tokens, credenciais ou ambientes `.venv`.** Compartilhar por Drive/serviço combinado pela equipe; imagens não vão para o Git.

Quem recebe deve comparar o checksum e extrair em uma pasta separada, mantendo os caminhos `ml/...`. Conferir antes de mesclar com seu acervo. Em nomes repetidos com conteúdo diferente, preservar as duas cópias para investigar; não substituir silenciosamente.

## 8. Como registrar uma rodada

Copiar e preencher em um arquivo `RESUMO-ENTREGA.md` junto do pacote:

```text
Responsável e computador:
Commit do código:
Data/hora de fechamento UTC:
Câmeras e intervalos pedidos (UTC):
Câmeras e intervalos realmente recuperados:
Quantidade de pares JPG/JSON:
Dias/estações CEMADEN completos e pendentes:
Falhas de DVR / lives reiniciadas / links trocados:
Manifests regenerados em:
Revisão: pendente ou revisor/data/grupos inspecionados:
Arquivo compartilhado e SHA-256:
Próxima ação e responsável:
```

Para o feriado, a entrega suficiente é **dados preservados + cobertura documentada + revisão com status claro**. Splits, F0–F3, exportação e deploy continuam no [plano de passagem](PASSAGEM-camera-fixa.md), com congelamento configurado em `2026-10-13T00:00:00Z` (12/10 às 21h de Brasília). Não mudar esse corte nem usar o teste prospectivo para escolher modelo.
