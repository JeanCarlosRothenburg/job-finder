"""Nota de 0 a 10 calculada pelo código, a partir dos requisitos extraídos.

Valor por requisito: 1,0 (experiência profissional), 0,5 (só conhecimento), 0 (não atende).
O = cobertura dos obrigatórios, D = cobertura dos diferenciais (soma de valor × peso / soma dos pesos).
Nota = 10 × (0,8 × O + 0,2 × D); sem diferenciais, Nota = 10 × O.
Trava: faltando um obrigatório de peso 3, a nota fica limitada a 7.
"""

from __future__ import annotations

from .perfil import Perfil

VALOR = {"profissional": 1.0, "conhecimento": 0.5, None: 0.0}

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
        valor = VALOR[nivel]
        peso = int(r.get("peso", 1))
        tipo = r.get("tipo", "obrigatorio")
        soma[tipo][0] += valor * peso
        soma[tipo][1] += peso
        if tipo == "obrigatorio" and peso == 3 and nivel is None:
            travada = True
        itens.append({**r, "match": nivel or "nao_atende", "skill_perfil": skill})

    o = soma["obrigatorio"][0] / soma["obrigatorio"][1] if soma["obrigatorio"][1] else None
    d = soma["diferencial"][0] / soma["diferencial"][1] if soma["diferencial"][1] else None
    if o is None and d is None:
        nota = 0.0
    elif d is None:
        nota = 10 * o
    elif o is None:
        nota = 10 * d
    else:
        nota = 10 * (perfil.peso_obrigatorio * o + perfil.peso_diferencial * d)
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
