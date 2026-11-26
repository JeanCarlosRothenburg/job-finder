"""Nota de 0 a 10 calculada pelo código, a partir dos requisitos extraídos.

Valor de cada requisito:
- 1,0 com experiência profissional;
- só conhecimento: 0,8 para práticas e ferramentas de apoio (Git, testes, CI/CD, Docker, ágil...)
  e 0,6 para tecnologias centrais (linguagens, frameworks, bancos, arquitetura);
- 0 quando não atende.
O = cobertura dos obrigatórios (soma de valor × peso / soma dos pesos).
D = cobertura dos diferenciais, que só somam: Nota = 10 × O + 0,5 × D (máximo 10).
Diferencial que falta nunca reduz a nota. Sem obrigatórios listados, Nota = 10 × D.
Trava: faltando um obrigatório de peso 3, a nota fica limitada a 7.
Os valores ficam em `nota:` no perfil.yaml.
"""

from __future__ import annotations

from .perfil import Perfil

# Práticas e ferramentas de apoio: quem estudou costuma se adaptar rápido no trabalho
PRATICAS = (
    "git", "github", "gitlab", "versionamento", "controle de versao", "testes", "teste", "tdd", "jest",
    "junit", "cypress", "ci cd", "ci/cd", "integracao continua", "docker", "container", "scrum", "kanban",
    "agil", "ageis", "code review", "jira", "uml", "documentacao", "observabilidade", "monitoramento",
    "linux", "sonarqube", "clean code", "solid", "design patterns",
)


def _e_pratica(nome: str) -> bool:
    from .texto import contem_termo, normalizar

    n = normalizar(nome)
    return any(contem_termo(n, p) for p in PRATICAS)


def valor(nivel: str | None, nome: str, perfil: Perfil) -> float:
    if nivel == "profissional":
        return 1.0
    if nivel == "conhecimento":
        return perfil.valor_conhecimento_pratica if _e_pratica(nome) else perfil.valor_conhecimento
    return 0.0

# Requisitos que não são tecnologia e se resolvem pelo perfil
_FORMACAO = ("graduacao", "superior", "bacharel", "formacao", "curso tecnico", "tecnico em", "cursando")
_INGLES = ("ingles",)


def _casar(req: str, perfil: Perfil) -> tuple[str | None, str | None]:
    from .texto import normalizar

    n = normalizar(req)
    if any(t in n for t in _INGLES):
        ordem = ["nao_exigido", "tecnico", "intermediario", "avancado", "fluente"]
        pedido = next((o for o in ordem[1:] if o[:5] in n), "tecnico")
        return ("profissional" if ordem.index(perfil.ingles) >= ordem.index(pedido) else None), "Inglês"
    if any(t in n for t in _FORMACAO) and perfil.formacao:
        # graduação concluída pedida e a do candidato está em andamento: atende parcialmente
        if perfil.graduacao_em_andamento and any(t in n for t in ("completo", "completa", "concluido", "concluida", "formado")):
            return "conhecimento", perfil.formacao[0]
        return "profissional", perfil.formacao[0]
    return perfil.nivel_de(req)


def calcular_nota(requisitos: list[dict], perfil: Perfil) -> tuple[float, dict]:
    itens = []
    soma = {"obrigatorio": [0.0, 0.0], "diferencial": [0.0, 0.0]}
    travada = False
    for r in requisitos:
        nivel, skill = _casar(r["nome"], perfil)
        v = valor(nivel, r["nome"], perfil)
        peso = int(r.get("peso", 1))
        tipo = r.get("tipo", "obrigatorio")
        soma[tipo][0] += v * peso
        soma[tipo][1] += peso
        if tipo == "obrigatorio" and peso == 3 and nivel is None:
            travada = True
        itens.append({**r, "match": nivel or "nao_atende", "skill_perfil": skill, "valor": v})

    o = soma["obrigatorio"][0] / soma["obrigatorio"][1] if soma["obrigatorio"][1] else None
    d = soma["diferencial"][0] / soma["diferencial"][1] if soma["diferencial"][1] else None
    if o is None and d is None:
        nota = 0.0
    elif o is None:
        nota = 10 * d
    else:
        nota = min(10.0, 10 * o + perfil.bonus_diferenciais * (d or 0.0))
    if travada:
        nota = min(nota, perfil.trava_obrigatorio_central)
    nota = round(nota, 1)

    def nomes(match: str) -> list[str]:
        return [f"{i['nome']}{' (diferencial)' if i['tipo'] == 'diferencial' else ''}" for i in itens if i["match"] == match]

    detalhe = {
        "cobertura_obrigatorios": None if o is None else round(o, 3),
        "cobertura_diferenciais": None if d is None else round(d, 3),
        "travada": travada,
        "atende_profissional": nomes("profissional"),
        "atende_conhecimento": nomes("conhecimento"),
        "nao_atende": nomes("nao_atende"),
        "requisitos": itens,
    }
    return nota, detalhe
