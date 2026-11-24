# job-finder

Busca vagas de Engenharia de Software, filtra pelo seu perfil, dá uma nota de 0 a 10 e prepara a
candidatura em modo semiautomático. Roda local, com custo zero: Python, SQLite, Ollama nativo e o
Claude da sua assinatura (pelo servidor MCP) para os textos.

Proposta de arquitetura: https://claude.ai/artifact/3sJmUnbBsTtQ6osLgtKHZr

## Como funciona

```
coletores (Gupy, GitHub, alertas de e-mail, manual)
   → deduplicação → pré-filtro por regras → Ollama extrai requisitos em JSON (ou heurística)
   → pós-filtro → nota calculada pelo código → nota ≥ 8 entra na Pilha
Pilha (swipe) → Confirmar → Claude gera textos via MCP → você abre a vaga, cola e envia → Candidaturas realizadas
```

- **Fontes**: Gupy (JSON público do portal), repositórios de vagas no GitHub (`backend-br/vagas`,
  `frontendbr/vagas`, `react-brasil/vagas`), alertas do LinkedIn e do Indeed lidos do Gmail por IMAP
  (só leitura) e vagas coladas por você. Nada de bots no LinkedIn, Indeed ou GeekHunter.
- **Filtros**: back-end, front-end ou full-stack; júnior ou pleno (até 4 anos pedidos); presencial
  ou híbrido só até 70 km de Presidente Getúlio/SC (coordenadas do IBGE); remoto em qualquer lugar;
  descarta vagas em inglês, que pedem inglês avançado/fluente ou fuso do exterior. Toda vaga
  descartada guarda o motivo (aba Recusadas).
- **Nota**: o Ollama (modelo de ~4B) só extrai os requisitos. O código calcula:
  valor 1,0 (experiência profissional), 0,5 (só conhecimento) ou 0; `nota = 10 × (0,8 × O + 0,2 × D)`,
  limitada a 7 se faltar um obrigatório central (peso 3). Pesos e corte ficam no `perfil.yaml`.
  Sem Ollama, uma heurística local assume a extração e o app avisa no topo.
- **Claude**: o servidor MCP expõe as vagas confirmadas; o Claude escreve os textos com as skills
  `/gupy` e `/linkedin`, revisa a zona cinzenta com `/analisar` e grava tudo de volta no app.

## Instalação no Mac (sem Docker)

```bash
git clone https://github.com/JeanCarlosRothenburg/job-finder.git
cd job-finder
./scripts/instalar_mac.sh        # instala uv e Ollama (Homebrew), baixa o qwen3:4b e roda os testes
```

Depois:

1. Preencha o `perfil.yaml` a partir do currículo: skills em `profissional` ou `conhecimento`
   (nunca as misture), formação, inglês, raio. Ele fica fora do Git.
2. Ajuste o `.env` se quiser outro modelo (ex.: `OLLAMA_MODELO=gemma3:4b`) ou outro intervalo de coleta.
3. Confira as fontes: `uv run job-finder testar-fontes`.
4. Suba o app: `uv run job-finder serve` e abra http://127.0.0.1:8000. A coleta roda sozinha a
   cada 3 horas (primeira rodada 1 minuto depois de subir) ou pelo botão **Buscar vagas agora**.

### Comandos

| Comando | O que faz |
|---|---|
| `job-finder serve` | Interface web, API (docs em `/docs`) e agendador |
| `job-finder ciclo` | Coleta e analisa uma vez |
| `job-finder coletar --fonte gupy` | Só coleta (fontes: `gupy`, `github`, `email`) |
| `job-finder processar` | Filtra, extrai e calcula a nota das vagas coletadas |
| `job-finder recalcular` | Recalcula notas e filtros depois de editar o `perfil.yaml` (sem LLM) |
| `job-finder testar-fontes` | Consulta cada fonte sem gravar nada |
| `job-finder testar-ollama` | Verifica se o Ollama e o modelo estão prontos |
| `job-finder mcp` | Servidor MCP (stdio) para o Claude |

## Conectar o Claude (custo zero)

No app do Claude para desktop, em *Settings → Developer → Edit Config*, acrescente o servidor
(modelo em `scripts/claude_desktop_config.exemplo.json`, ajuste o caminho):

```json
{
  "mcpServers": {
    "job-finder": {
      "command": "/opt/homebrew/bin/uv",
      "args": ["--directory", "/Users/SEU_USUARIO/job-finder", "run", "job-finder", "mcp"]
    }
  }
}
```

No Claude Code: `claude mcp add job-finder -- uv --directory /Users/SEU_USUARIO/job-finder run job-finder mcp`.

Depois é só pedir, por exemplo: *"use o job-finder e gere os textos das vagas confirmadas com
/gupy e /linkedin"* ou *"revise a zona cinzenta do job-finder com /analisar"*.

Ferramentas: `listar_vagas_confirmadas`, `listar_vagas`, `listar_zona_cinzenta`, `ler_vaga`,
`ler_perfil`, `salvar_textos`, `marcar_revisada`, `adicionar_vaga`, `completar_descricao`.
Sem MCP, o botão **Copiar para o Claude** monta a vaga para colar numa conversa.

O Claude entra quando você pede, nunca sozinho no agendador: chamar a API da Anthropic pelo
backend seria cobrado por uso.

## Alertas do LinkedIn e do Indeed (opcional)

1. Crie alertas de vaga no LinkedIn e no Indeed para o seu Gmail.
2. Gere uma senha de app em https://myaccount.google.com/apppasswords (exige verificação em duas etapas).
3. Preencha `IMAP_USUARIO` e `IMAP_SENHA_APP` no `.env`.

O coletor abre a caixa em modo só leitura e pega título, empresa e link. Como o e-mail não traz a
descrição, a vaga aparece na aba **Alertas e manual** para você colar a descrição (ou pedir ao
Claude com `completar_descricao`).

## Interface

- **Pilha**: um cartão por vez, ordenado por nota. Arraste para a direita ou → confirma; para a
  esquerda ou ← recusa; ↺ ou Ctrl/Cmd+Z desfaz.
- **Candidatar**: textos da Gupy (formal e leve), 3 skills, mensagem ao recrutador; botões Abrir
  vaga, Copiar, Marcar como enviada e Voltar para a pilha.
- **Candidaturas realizadas**: data, cargo, empresa, nota, canal, link e observações.
- **Alertas e manual**: vagas dos e-mails sem descrição e formulário para colar uma vaga.
- **Recusadas**: recusadas por você, abaixo da nota e descartadas pelo filtro, com o motivo.

## Gupy

A Gupy não tem API oficial para candidatos; o coletor usa o JSON do portal de vagas, que muda sem
aviso (os endereços `/api/v1/jobs` antigos passaram a responder 404). Ele tenta, em ordem, os
endereços em `src/job_finder/coletores/gupy.py`. Se nenhum funcionar, abra https://portal.gupy.io,
faça uma busca com o DevTools aberto (aba Rede), copie a URL da requisição que devolve as vagas e
coloque em `GUPY_ENDPOINT` no `.env`.

## Docker (para o futuro)

`docker compose up -d` sobe o app em http://localhost:8000 com o SQLite num volume. O Ollama
continua nativo no host (`host.docker.internal:11434`), porque no macOS o container não usa a GPU.

## Desenvolvimento

```bash
uv sync --extra dev
uv run pytest
```

Estrutura: `coletores/` (uma fonte por arquivo, mesma interface), `filtros.py`, `extracao.py`
(Ollama com JSON Schema no `format` e heurística), `nota.py`, `pipeline.py`, `servicos.py`
(regras compartilhadas pela API e pelo MCP), `api.py`, `mcp_server.py`, `web/` (HTML, CSS e JS
sem etapa de build). Coordenadas dos municípios: [kelvins/municipios-brasileiros](https://github.com/kelvins/municipios-brasileiros) (MIT).
