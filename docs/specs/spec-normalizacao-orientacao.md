# SPEC F0.1 — Normalização de orientação da coleta própria

> **Documento autocontido.** Tudo que é necessário para executar está aqui — não é preciso
> ler a conversa que o originou. Em caso de conflito entre esta spec e o estado real do
> disco, **pare e reporte a divergência** em vez de improvisar.
>
> Projeto: CityRain (TCC IMT). Convenções do repo: PEP 8, type hints em funções públicas,
> docstrings Google style, nomes de variáveis em inglês, comentários podem ser em português.
> Commits: `tipo: descrição` em português.

## Contexto (por que isso existe)

A coleta de frames é feita por uma câmera veicular numa Jetson Nano. A câmera foi montada
de ponta-cabeça em três das quatro sessões de coleta, então **três pastas estão rotacionadas
180°** e uma está correta. Auditoria visual feita em 15/09/2026 confirmou, pasta a pasta:

| Pasta (em `ml/data/raw/imt_coleta/`) | Rotação necessária | jpg | json | Observações |
|---|---|---:|---:|---|
| `cityrain_frames/` | **180°** | 1.017 | 1.017 | pares jpg+json íntegros |
| `cityrain_frames2/` | **180°** | 4.746 | 4.746 | pares íntegros |
| `cityrain_frames3/` | **180°** | 1.385 | 1.386 | 1 json órfão: `frame_20260905_151154_299.json` (sem jpg) |
| `framesSemNada/frames/` | **nenhuma (0°)** | 4.848 | 0 | 65 jpg de **0 byte**; sem metadados; jpgs ficam no subdiretório `frames/` |

Todos os jpgs são 640×480, sem tag EXIF de orientação (gravados por `cv2.imwrite`, que não
escreve EXIF). A rotação correta foi confirmada olhando as imagens: na orientação certa, o
capô/painel do carro fica embaixo e o céu em cima (vista de dashcam).

**Atenção:** a rotação é POR PASTA, nunca global. Rotacionar a `framesSemNada` a
estragaria — ela já está certa.

## Objetivo

Criar um script que materialize as quatro pastas em `ml/data/processed/imt_coleta/`, todas
na orientação correta, limpas de lixo, **sem jamais modificar `ml/data/raw/`**.

## Entregáveis

1. `ml/configs/normalizacao_imt.yaml` — config declarando as pastas e suas rotações
2. `ml/scripts/preprocessamento/normalizar_orientacao.py` — o script
3. `ml/tests/test_normalizacao.py` — testes com imagens sintéticas
4. Execução real do script sobre as 4 pastas, com o relatório de saída conferido

Vão para o git: config, script, testes. **Pixels nunca vão para o git** — o `.gitignore`
já cobre `ml/data/raw/**` e `ml/data/processed/**`; confirme com `git status` ao final.

## Requisitos funcionais

### RF1 — Config YAML (não hardcode)
O mapeamento pasta → rotação vive em `ml/configs/normalizacao_imt.yaml`, algo como:

```yaml
raiz_entrada: ml/data/raw/imt_coleta
raiz_saida: ml/data/processed/imt_coleta
pastas:
  cityrain_frames:    { rotacao_graus: 180 }
  cityrain_frames2:   { rotacao_graus: 180 }
  cityrain_frames3:   { rotacao_graus: 180 }
  framesSemNada:      { rotacao_graus: 0, subpasta_jpgs: frames }
```

Pasta presente no disco mas ausente da config (ou vice-versa) ⇒ warning explícito no
relatório, nunca falha silenciosa.

### RF2 — Rotação sem perdas de dimensão
- Rotação de 180° via `PIL.Image.transpose(Image.Transpose.ROTATE_180)` (exato, sem
  interpolação). Salvar com `quality=95`.
- Rotação 0° ⇒ **cópia byte a byte** do arquivo (sem reencodar; usar `shutil.copy2`).
- Dimensões de saída idênticas às de entrada (640×480).

### RF3 — Metadados acompanham
- Para pastas com `.json` por frame: copiar cada json **inalterado** para a saída, ao lado
  do jpg correspondente.
- A estrutura de saída é achatada e uniforme: `processed/imt_coleta/<pasta>/*.jpg|*.json`
  (a subpasta `frames/` da `framesSemNada` desaparece na saída).

### RF4 — Limpeza
- Jpg de 0 byte ⇒ **pular** e listar no relatório (esperado: 65, todos na `framesSemNada`).
- Json órfão (sem jpg homônimo) ⇒ pular e listar (esperado: 1, na `cityrain_frames3`).
- Jpg órfão (sem json) em pasta que tem metadados ⇒ pular e listar (esperado: 0 — se
  aparecer algum, é sinal de divergência com esta spec; reportar).
- Arquivos `.DS_Store` e afins: ignorar, não copiar.

### RF5 — Relatório de execução auditável
Ao final, gravar `processed/imt_coleta/<pasta>/_normalizacao.json` por pasta, com:
`rotacao_aplicada`, `total_entrada`, `total_saida`, `pulados` (lista com motivo:
`zero_byte` | `json_orfao` | `jpg_orfao`), `timestamp_execucao_utc`, e o hash sha256 do
config usado. Também imprimir um resumo tabular no stdout.

### RF6 — Idempotência e segurança
- Re-execução: se o arquivo de saída já existe, **pular** (contabilizado no relatório como
  `ja_existia`). Flag `--force` reprocessa tudo.
- Flag `--dry-run`: lista o que faria (contagens por pasta e por motivo) sem escrever nada.
- O script **nunca escreve em `raiz_entrada`** — se qualquer caminho de escrita resolver
  para dentro dela, abortar com erro.

### RF7 — Amostras para conferência humana
Flag `--amostras N` (default 4): salva `processed/imt_coleta/_amostras/<pasta>.jpg` — um
grid com N frames espalhados pela pasta (ex.: percentis 10/35/60/85), já normalizados,
para conferência visual rápida.

### RF8 — CLI
```
python ml/scripts/preprocessamento/normalizar_orientacao.py \
    --config ml/configs/normalizacao_imt.yaml [--dry-run] [--force] [--amostras 4]
```
Dependências permitidas: `Pillow`, `PyYAML`, stdlib. Nada de OpenCV/torch aqui.

## Fora de escopo (não fazer)

- Não redimensionar, recortar, corrigir cor ou deduplicar.
- Não tocar em `ml/data/processed/youtube/` nem em `public_datasets/`.
- Não alterar nenhum conteúdo de json (cópia literal).
- Não deletar nada de `raw/` (os 0-byte ficam lá; só não são copiados).

## Testes exigidos (`ml/tests/test_normalizacao.py`)

Usar `tmp_path` do pytest; gerar imagens sintéticas **assimétricas** (ex.: quadrante
superior-esquerdo vermelho, resto preto) para poder afirmar rotação por pixel:

1. Rotação 180° move o quadrante vermelho para o inferior-direito; dimensões preservadas.
2. Rotação 0° produz cópia byte-idêntica (comparar sha256).
3. Jpg de 0 byte é pulado e aparece no relatório com motivo `zero_byte`.
4. Json órfão é pulado e reportado; jpg+json válidos saem juntos.
5. Segunda execução sem `--force` não reescreve nada (mtime inalterado) e contabiliza
   `ja_existia`; com `--force`, reescreve.
6. `--dry-run` não cria nenhum arquivo.

## Critérios de aceite (todos obrigatórios)

- [ ] `pytest ml/tests/test_normalizacao.py` passa integralmente
- [ ] Execução real termina sem erro e o relatório bate com o esperado:
  - [ ] `cityrain_frames`: 1.017 jpg + 1.017 json na saída
  - [ ] `cityrain_frames2`: 4.746 + 4.746
  - [ ] `cityrain_frames3`: 1.385 + 1.385 (o órfão reportado, não copiado)
  - [ ] `framesSemNada`: 4.783 jpg (4.848 − 65 zero-byte), 0 json, achatada (sem subpasta `frames/`)
- [ ] Grid de amostras gerado para as 4 pastas; nas três `cityrain_frames*` o capô aparece
      embaixo e o céu em cima; a `framesSemNada` continua como estava
- [ ] Re-execução imediata reporta 100% `ja_existia` e não altera mtimes
- [ ] `git status` não acusa nenhum arquivo novo sob `ml/data/` (pixels fora do git);
      config + script + testes commitados na branch `exp/normalizacao-orientacao` ou similar
- [ ] `raw/` byte-idêntico ao estado anterior (nenhuma escrita lá)

## Verificação rápida (para quem revisar)

```bash
find ml/data/processed/imt_coleta -name '*.jpg' | wc -l          # esperado: 11.931
find ml/data/processed/imt_coleta -name '*.json' ! -name '_*' | wc -l  # esperado: 7.148
find ml/data/processed/imt_coleta -size 0 | wc -l                # esperado: 0
git status --porcelain ml/data/ | wc -l                          # esperado: 0
```
