# Segurança

## Como reportar

Encontrou uma falha? Não abra issue pública. Escreva para a equipe pelo repositório ([Rodrigomt21/CityRain](https://github.com/Rodrigomt21/CityRain)) com os passos para reproduzir; respondemos em até 3 dias úteis durante o semestre letivo.

## Modelo de ameaça

O CityRain é um protótipo acadêmico com dados públicos de chuva. O que protegemos:

| Ativo | Risco | Controle |
|---|---|---|
| Ingestão (`POST /api/v1/ingest`) | dispositivo falso enviando dados | token por dispositivo (`secrets.token_urlsafe(32)`), banco guarda só o SHA-256; dispositivo desativado perde acesso na hora |
| Cadastro de dispositivos | criação de tokens por terceiros | `ADMIN_KEY` obrigatória; vazia = rotas de admin desligadas (401); comparação em tempo constante |
| Armazenamento | upload de arquivo arbitrário | conteúdo validado pelos bytes iniciais (JPEG/PNG), teto de tamanho, metadata ≤ 16 KB, nome e extensão gerados pelo servidor |
| Privacidade (LGPD) | exposição de imagem do carro e de placa | foto do carro nunca é servida; placa só na rota de admin; fotos de câmera fixa apagadas após 60 min |
| Informação interna | caminho de arquivo, erro de banco | rotas públicas não devolvem caminho no disco, mensagem de erro interna nem detalhe da conexão com o banco |
| Navegador | uso indevido por outros sites | CORS restrito às origens configuradas, sem credenciais; cabeçalhos `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy` e `Permissions-Policy` no painel |

## Segredos

Nunca commitar: `backend/.env`, `ml/.env`, `ml/configs/coleta_fixa_tokens.json`, `ml/scripts/captura/cityrain_config.json`. Todos estão no `.gitignore` e têm um `.example` com o formato. Em 18/10/2026 o histórico inteiro do Git foi verificado contra cada segredo em uso, sem ocorrência.

Variáveis `VITE_` do painel vão para o JavaScript público: nunca colocar chave nelas.

## Decisões conscientes

- Leituras do painel são públicas (capturas, câmeras, veículos, estatísticas): o produto é um mapa aberto de chuva. A posição do carro aparece por até 30 min no ao vivo, sem placa nem foto.
- Sem limite de taxa na API: o tráfego é de poucos dispositivos conhecidos. Próximo passo, se aberta a terceiros.
- Sem Content-Security-Policy no painel por enquanto, para não quebrar tiles do mapa e fotos na defesa; próximo passo.
- Dependências de build do painel com alertas do `npm audit` (cadeia do Tailwind 3) não vão para o site publicado; a migração para o Tailwind 4 fica para depois da defesa.
