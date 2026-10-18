# Guia da sessão de carro (Jetson) — da saída ao dado rotulado

Para quem dirige com a Jetson (Moreno nesta semana). Objetivo: a sessão voltar
com GPS e horário bons e virar **dado de teste rotulado por pluviômetro** com um comando.

## 1. Antes de sair (5 minutos)

1. **Alimentação: power bank com pass-through** (carrega e alimenta ao mesmo tempo).
   Ligar a placa direto no acendedor derruba a Jetson no start-stop do carro: foi o que
   cortou as sessões anteriores. Sem power bank, não saia.
2. **GPS com fix antes de partir.** Esperar o fix no céu aberto (alguns minutos) antes de
   rodar. Sem fix o frame não tem posição e não vira rótulo (na sessão de 13/09, 38% dos
   frames ficaram sem fix).
3. **Relógio certo (NTP).** Com internet (hotspot do celular) a hora sincroniza sozinha.
   Confira com `timedatectl` na Jetson (`System clock synchronized: yes`). Os JSONs novos
   trazem `hora_rmc_utc` (hora do GPS), que serve para auditar o relógio depois.
4. **Câmera na orientação combinada** e conferir um frame no local. O script assume que as
   fotos saem de ponta-cabeça (rotação 180°, como nas sessões anteriores); se a câmera
   estiver certa, use `--rotacao 0`.
5. **Rota perto de pluviômetro.** Passar a até 2 km de uma estação CEMADEN que reporta
   (ver `docs/fontes-estacoes.md`); perto de nenhuma, o rótulo cai em consenso regional (5 km).
6. Sair **com chuva de verdade**; o gargalo do projeto são eventos de chuva moderada/forte.

## 2. Copiar a sessão da Jetson

Com a Jetson na rede (`ssh jetson`, IP fixo 192.168.0.154), copie a pasta com os `frame_*.jpg`
e `frame_*.json` para o computador. Exemplo (ajuste o caminho de origem):

```bash
scp -r jetson:/home/jetson/frames ~/sessoes/2026-10-15_moreno
```

Um dump com subpastas também funciona (o script procura `frame_*` recursivamente).
Se a Jetson foi desligada de forma brusca, os últimos jpgs podem estar corrompidos ou sem JSON.
O script ignora esses casos e conta.

## 3. O comando

Na raiz do repo, com o venv do `ml/`:

```bash
ml/.venv/bin/python ml/scripts/sessao_carro/processar_sessao.py ~/sessoes/2026-10-15_moreno
```

Ele faz, em ordem: valida horário e GPS, copia para `ml/data/raw/imt_coleta/<nome>/`,
gira as fotos para `ml/data/processed/imt_coleta/<nome>/`, baixa o CEMADEN só dos dias e
das estações perto da rota que ainda não estão em cache, rotula e imprime o resumo. O manifest da
sessão fica em `ml/data/manifests/sessoes/manifest_<nome>.csv` (o `manifest_imt.csv`
global não é alterado).

Opções úteis: `--dry-run` (não escreve nada), `--sem-rede` (usa só o cache),
`--dia AAAA-MM-DD` (se a pasta mistura dias), `--nome` (nome da sessão), `--rotacao 0`.

Precisa de `CEMADEN_EMAIL`/`CEMADEN_SENHA` em `ml/.env` para baixar. A API tem cota:
se responder **HTTP 401**, o script **para** e avisa os pares que faltaram; rode de novo
mais tarde, pois o que já baixou fica em cache. Não insista.

## 4. Lendo o resumo

**Bloco de validação (topo)**
- `GPS fix: X%`. Abaixo de 50% o script alerta. Quanto menor, mais frames sem rótulo.
- `Tempo UTC`. Confira se bate com o horário real da saída (UTC = local + 3 h).
- `ALERTA: RELÓGIO ...`: horário antigo, no futuro, salto para trás, nome do arquivo
  diferente do JSON, ou relógio diferente da hora do GPS. Com esse alerta o rótulo não é confiável
  (o horário casa o frame com a chuva medida). Avise o Rodrigo antes de usar a sessão como teste.

**Resumo por classe**: por dia/sessão, quantos frames viraram `seco`, `garoa`, `moderada`,
`forte`, e quantos ficaram sem rótulo, com o motivo:

| Motivo | O que significa |
|---|---|
| `sem_gps_fix` | frame sem posição (e sem consenso de seco da rede) |
| `posicao_desatualizada` | último fix tem mais de 12 s |
| `poucas_estacoes_consenso` / `sem_consenso_regional` | não há 3 estações com dado perto o bastante; **comum** porque Mooca e AC Almeida Lima não devolvem dado no PED |
| `seco_incerto` | uma estação zerou, mas outra viu chuva em ±60 min; não se arrisca `seco` |
| `zona_morta` | valor na fronteira entre duas classes |

Regras valem as de sempre: rótulo só de pluviômetro, sem sintético em teste. Se a
sessão não tiver `moderada`/`forte`, ela ajuda como teste de `seco`/`garoa`; para as outras
classes a saída tem de pegar chuva forte.

## 5. Depois

Avise o Rodrigo com o nome da sessão e o resumo impresso. Não faça commit do
`ml/data/`; os manifests em `ml/data/manifests/sessoes/` seguem o fluxo normal do repo.
