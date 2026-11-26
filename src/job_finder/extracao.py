"""Extração de requisitos em JSON: Ollama com JSON Schema no `format`, ou heurística local."""

from __future__ import annotations

import json
import logging
import re

import httpx

from .texto import contem_termo, normalizar

log = logging.getLogger(__name__)

VERSAO_PROMPT = "v1"

SCHEMA = {
    "type": "object",
    "properties": {
        "cargo_area": {"type": "string", "enum": ["backend", "frontend", "fullstack", "outro"]},
        "senioridade": {"type": "string", "enum": ["estagio", "junior", "pleno", "senior", "especialista", "nao_informado"]},
        "anos_experiencia_min": {"type": ["integer", "null"]},
        "modelo_trabalho": {"type": "string", "enum": ["presencial", "hibrido", "remoto", "nao_informado"]},
        "cidade": {"type": "string"},
        "uf": {"type": "string"},
        "ingles": {"type": "string", "enum": ["nao_exigido", "tecnico", "intermediario", "avancado", "fluente"]},
        "vaga_em_ingles": {"type": "boolean"},
        "fuso_exterior": {"type": "boolean"},
        "contrato": {"type": "string", "enum": ["clt", "pj", "outro", "nao_informado"]},
        "recrutador_nome": {"type": "string"},
        "requisitos": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "nome": {"type": "string"},
                    "tipo": {"type": "string", "enum": ["obrigatorio", "diferencial"]},
                    "peso": {"type": "integer", "minimum": 1, "maximum": 3},
                },
                "required": ["nome", "tipo", "peso"],
            },
        },
    },
    "required": [
        "cargo_area", "senioridade", "anos_experiencia_min", "modelo_trabalho", "cidade", "uf",
        "ingles", "vaga_em_ingles", "fuso_exterior", "contrato", "recrutador_nome", "requisitos",
    ],
}

PROMPT_SISTEMA = """Você extrai dados estruturados de vagas de emprego de tecnologia no Brasil.
Responda só com o JSON pedido. Não invente: use "nao_informado", "" ou null quando a vaga não disser.

Regras:
- requisitos: tecnologias, práticas e formações pedidas, uma por item, com nome curto e canônico
  (ex.: "Java", "Spring Boot", "PostgreSQL", "React", "Testes automatizados", "Docker", "Inglês técnico",
  "Graduação em TI"). No máximo 15 itens. Não inclua soft skills genéricas ("comunicação", "proatividade").
- tipo: "obrigatorio" para requisitos, "diferencial" para desejáveis, diferenciais ou "será um plus".
- peso: 3 se aparece no título ou é central no dia a dia; 2 se é citado mais de uma vez ou é importante; 1 caso contrário.
- cargo_area: "outro" para QA, dados, mobile, suporte, DevOps, infraestrutura.
- ingles: o nível exigido; "tecnico" para leitura ou inglês técnico.
- fuso_exterior: true só se o trabalho exige horário dos EUA ou da Europa.
- recrutador_nome: só se a vaga citar o nome de quem recruta.

Exemplo de requisito: {"nome": "Node.js", "tipo": "obrigatorio", "peso": 3}"""


_RODAPE = re.compile(
    r"\n[^\n]{0,40}(benef[ií]cios|o que oferecemos|nossos benef|sobre a empresa|quem somos|etapas do processo)[^\n]{0,60}\n.*",
    re.I | re.S,
)


def _descricao_enxuta(texto: str, limite: int = 3500) -> str:
    """Corta benefícios e etapas do processo (não têm requisitos) e limita o tamanho: menos tokens, mais rápido."""
    t = texto or ""
    m = _RODAPE.search(t)
    if m and m.start() > 400:
        t = t[: m.start()]
    return t[:limite]


def _mensagem_usuario(vaga) -> str:
    return (
        f"Título: {vaga.titulo}\nEmpresa: {vaga.empresa}\n"
        f"Local informado: {vaga.cidade}/{vaga.uf} ({vaga.modelo or 'modelo não informado'})\n"
        f"Etiquetas: {', '.join(vaga.etiquetas or [])}\n\nDescrição:\n{_descricao_enxuta(vaga.descricao)}"
    )


def extrair_ollama(vaga, url: str, modelo: str, timeout: float = 240) -> dict:
    corpo = {
        "model": modelo,
        "messages": [
            {"role": "system", "content": PROMPT_SISTEMA},
            {"role": "user", "content": _mensagem_usuario(vaga)},
        ],
        "format": SCHEMA,
        "stream": False,
        "think": False,  # Qwen3: desliga o modo de raciocínio (mais rápido)
        "keep_alive": "30m",  # mantém o modelo carregado entre vagas (evita recarregar a cada uma)
        "options": {"temperature": 0, "num_ctx": 4096, "num_predict": 900},
    }
    with httpx.Client(timeout=timeout) as cli:
        r = cli.post(f"{url}/api/chat", json=corpo)
        if r.status_code == 400 and "think" in r.text.lower():
            corpo.pop("think")  # modelos sem suporte a "think" (ex.: Gemma 3)
            r = cli.post(f"{url}/api/chat", json=corpo)
        r.raise_for_status()
        conteudo = r.json()["message"]["content"]
    return normalizar_extracao(json.loads(conteudo))


def ollama_disponivel(url: str, modelo: str) -> tuple[bool, str]:
    try:
        r = httpx.get(f"{url}/api/tags", timeout=3)
        r.raise_for_status()
        nomes = [m.get("name", "") for m in r.json().get("models", [])]
    except Exception as e:  # noqa: BLE001
        return False, f"Ollama fora do ar em {url} ({e.__class__.__name__})"
    if not any(n == modelo or n.split(":")[0] == modelo for n in nomes):
        return False, f"modelo {modelo} não instalado (rode: ollama pull {modelo})"
    return True, "ok"


def normalizar_extracao(d: dict) -> dict:
    """Garante todos os campos e tipos, mesmo se o modelo esquecer algum."""
    padrao = {
        "cargo_area": "fullstack", "senioridade": "nao_informado", "anos_experiencia_min": None,
        "modelo_trabalho": "nao_informado", "cidade": "", "uf": "", "ingles": "nao_exigido",
        "vaga_em_ingles": False, "fuso_exterior": False, "contrato": "nao_informado",
        "recrutador_nome": "", "requisitos": [],
    }
    out = {**padrao, **{k: v for k, v in (d or {}).items() if v is not None or k == "anos_experiencia_min"}}
    reqs, vistos = [], set()
    for r in out.get("requisitos") or []:
        nome = str(r.get("nome", "")).strip()
        if not nome or normalizar(nome) in vistos:
            continue
        vistos.add(normalizar(nome))
        tipo = r.get("tipo") if r.get("tipo") in ("obrigatorio", "diferencial") else "obrigatorio"
        try:
            peso = min(3, max(1, int(r.get("peso", 1))))
        except (TypeError, ValueError):
            peso = 1
        reqs.append({"nome": nome, "tipo": tipo, "peso": peso})
    out["requisitos"] = reqs[:20]
    out["uf"] = (out.get("uf") or "").upper()[:2]
    return out


# ---------------------------------------------------------------- heurística
# Usada quando o Ollama está fora do ar e nos testes. Menos precisa, mas determinística.
TECNOLOGIAS = [
    "Java", "Spring Boot", "Spring", "Kotlin", "Python", "Django", "Flask", "FastAPI", "PHP", "Laravel",
    "Symfony", "C#", ".NET", "Go", "Golang", "Ruby", "Rails", "Node.js", "NestJS", "Express", "JavaScript",
    "TypeScript", "React", "Next.js", "Vue", "Nuxt", "Angular", "Svelte", "HTML", "CSS", "Sass", "Tailwind",
    "jQuery", "Redux", "SQL", "PostgreSQL", "MySQL", "Oracle", "SQL Server", "MongoDB", "Redis", "Elasticsearch",
    "Kafka", "RabbitMQ", "Docker", "Kubernetes", "AWS", "Azure", "GCP", "Terraform", "Git", "CI/CD", "Linux",
    "APIs REST", "GraphQL", "gRPC", "Microsserviços", "Testes automatizados", "TDD", "Jest", "JUnit", "Cypress",
    "Scrum", "Kanban", "Clean Code", "SOLID", "Design Patterns", "DDD", "Hibernate", "JPA", "Delphi",
]
_SINONIMOS_HEUR = {
    "Node.js": ["node", "nodejs"], "APIs REST": ["rest", "restful", "api rest", "apis restful"],
    "Microsserviços": ["microservicos", "microsservicos", "microservices"],
    "Testes automatizados": ["testes unitarios", "testes automatizados", "unit tests", "testes de integracao"],
    "Go": ["golang"], "PostgreSQL": ["postgres"], "C#": ["csharp"], ".NET": ["dotnet", "asp.net"],
}
_SEC_DIF = re.compile(r"(diferencia|desej[aá]v|ser[aá] um plus|nice to have|b[oô]nus|plus)", re.I)
_SEC_OBR = re.compile(r"(requisitos|obrigat[oó]ri|o que (voc[eê] precisa|esperamos)|qualifica[cç]|must have|pr[eé]-requisito)", re.I)


def extrair_heuristica(vaga) -> dict:
    from .filtros import anos_exigidos, parece_ingles, senioridade_do_texto

    desc = vaga.descricao or ""
    titulo_n = normalizar(vaga.titulo)
    # marca cada linha como obrigatória ou diferencial conforme o último cabeçalho visto
    secao, linhas = "obrigatorio", []
    for linha in desc.splitlines():
        if _SEC_DIF.search(linha) and len(linha) < 120:
            secao = "diferencial"
        elif _SEC_OBR.search(linha) and len(linha) < 120:
            secao = "obrigatorio"
        linhas.append((secao, normalizar(linha)))
    texto_n = normalizar(desc)
    reqs = []
    ja = set()
    for tec in TECNOLOGIAS:
        termos = [tec, *_SINONIMOS_HEUR.get(tec, [])]
        if tec in ("Go",):  # "go" é palavra comum demais; só o sinônimo
            termos = ["golang"]
        if tec == "Spring" and "Spring Boot" in ja:
            continue
        no_titulo = any(contem_termo(titulo_n, t) for t in termos)
        tipos = [s for s, l in linhas if any(contem_termo(l, t) for t in termos)]
        if not tipos and not no_titulo:
            continue
        ja.add(tec)
        ocorrencias = sum(len(re.findall(rf"(?<![a-z0-9+#]){re.escape(normalizar(t))}(?![a-z0-9+#])", texto_n)) for t in termos)
        tipo = "obrigatorio" if no_titulo or "obrigatorio" in tipos else "diferencial"
        peso = 3 if no_titulo else (2 if ocorrencias >= 2 else 1)
        reqs.append({"nome": tec, "tipo": tipo, "peso": peso})

    n = normalizar(f"{vaga.titulo} {desc}")
    area = "fullstack"
    if any(contem_termo(titulo_n, t) for t in ("backend", "back end", "back-end")):
        area = "backend"
    elif any(contem_termo(titulo_n, t) for t in ("frontend", "front end", "front-end")):
        area = "frontend"
    modelo = vaga.modelo or ("remoto" if contem_termo(n, "remoto") or contem_termo(n, "home office")
                             else "hibrido" if contem_termo(n, "hibrido")
                             else "presencial" if contem_termo(n, "presencial") else "nao_informado")
    contrato = "clt" if contem_termo(n, "clt") else "pj" if contem_termo(n, "pj") else "nao_informado"
    ingles = "tecnico" if contem_termo(n, "ingles tecnico") else (
        "intermediario" if contem_termo(n, "ingles intermediario") else "nao_exigido")
    return normalizar_extracao({
        "cargo_area": area,
        "senioridade": senioridade_do_texto(vaga.titulo) or "nao_informado",
        "anos_experiencia_min": anos_exigidos(desc),
        "modelo_trabalho": modelo,
        "cidade": vaga.cidade, "uf": vaga.uf, "ingles": ingles,
        "vaga_em_ingles": parece_ingles(desc), "fuso_exterior": False,
        "contrato": vaga.contrato or contrato, "recrutador_nome": "", "requisitos": reqs,
    })
