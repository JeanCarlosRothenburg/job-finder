"""Filtros em duas etapas: regras baratas antes do LLM e confirmação com o que o LLM extraiu."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .localidade import avaliar_local
from .perfil import Perfil
from .texto import contem_termo, normalizar

SENIORIDADES = {
    "estagio": ["estagio", "estagiario", "estagiaria", "intern", "internship"],
    "junior": ["junior", "jr", "jr.", "nivel i", "entry level"],
    "pleno": ["pleno", "mid level", "mid-level", "nivel ii"],
    "senior": ["senior", "sr", "sr.", "nivel iii"],
    "especialista": ["especialista", "staff", "principal", "lead", "lider", "tech lead"],
}

_INGLES_RUIM = re.compile(
    r"ingl[eê]s\s+(avan[cç]ado|fluente|fluência|conversa[cç][aã]o)|"
    r"(fluent|advanced)\s+english|english\s*[:\-]?\s*(fluent|advanced|c1|c2)|"
    r"fluência\s+em\s+ingl[eê]s|conversação\s+em\s+ingl[eê]s",
    re.I,
)
_ANOS = re.compile(
    r"(\d{1,2})\s*\+?\s*(?:anos|years)\s+(?:de\s+)?(?:experi[eê]ncia|experience|atua[cç][aã]o)", re.I
)
_FUSO = re.compile(r"\b(est|pst|cet|gmt[+-]\d|us time ?zone|fuso (?:dos eua|europeu|americano))\b", re.I)

_STOP_EN = {"the", "and", "with", "you", "our", "for", "will", "are", "experience", "team", "work", "we"}
_STOP_PT = {"de", "e", "com", "para", "voce", "nossa", "nosso", "experiencia", "equipe", "trabalho", "que", "uma"}


@dataclass
class ResultadoFiltro:
    aprovada: bool
    motivo: str = ""
    avisos: list[str] = field(default_factory=list)


def senioridade_do_texto(texto: str) -> str:
    """Primeira senioridade encontrada no texto (normalmente o título)."""
    n = normalizar(texto)
    for nivel in ("estagio", "especialista", "senior", "pleno", "junior"):
        if any(contem_termo(n, t) for t in SENIORIDADES[nivel]):
            return nivel
    return ""


def anos_exigidos(texto: str) -> int | None:
    achados = [int(m.group(1)) for m in _ANOS.finditer(texto or "")]
    return min(achados) if achados else None


def parece_ingles(texto: str) -> bool:
    palavras = normalizar(texto).split()
    if len(palavras) < 40:
        return False
    en = sum(p in _STOP_EN for p in palavras)
    pt = sum(p in _STOP_PT for p in palavras)
    return en > 3 * max(pt, 1)


_TITULO_AREA = [
    "back-end", "backend", "back end", "front-end", "frontend", "front end", "full-stack", "fullstack",
    "full stack", "desenvolvedor de software", "desenvolvedora de software", "pessoa desenvolvedora de software",
    "engenheiro de software", "engenheira de software", "software engineer", "software developer",
]


def titulo_indica_area(titulo: str) -> bool:
    """O título já diz back-end, front-end, full-stack ou desenvolvimento de software."""
    n = normalizar(titulo)
    return any(contem_termo(n, t) for t in _TITULO_AREA)


def _titulo_ok(titulo: str, perfil: Perfil) -> str:
    n = normalizar(titulo)
    for termo in perfil.titulos_excluir:
        if contem_termo(n, termo):
            return f"título contém '{termo}'"
    if perfil.titulos_incluir and not any(contem_termo(n, t) for t in perfil.titulos_incluir):
        return "título fora de back-end, front-end ou full-stack"
    return ""


def _local_ok(modelo: str, cidade: str, uf: str, perfil: Perfil, avisos: list[str]) -> str:
    if modelo == "remoto":
        return ""
    if modelo in ("presencial", "hibrido"):
        dentro, dist = avaliar_local(cidade, uf, (perfil.cidade_base, perfil.uf_base), perfil.raio_km, perfil.cidades_aceitas_extra)
        if dentro is False:
            return f"{modelo} em {cidade}/{uf} a {dist:.0f} km (limite {perfil.raio_km:.0f} km)"
        if dentro is None:
            avisos.append("cidade não identificada")
        elif dist is not None:
            avisos.append(f"{dist:.0f} km de {perfil.cidade_base}")
        return ""
    avisos.append("modelo de trabalho não informado")
    return ""


def pre_filtro(vaga, perfil: Perfil) -> ResultadoFiltro:
    """Etapa 1: só com os dados coletados, antes de gastar o LLM."""
    avisos: list[str] = []
    motivo = _titulo_ok(vaga.titulo, perfil)
    if motivo:
        return ResultadoFiltro(False, motivo)

    sen = vaga.senioridade or senioridade_do_texto(" ".join([vaga.titulo, *(vaga.etiquetas or [])]))
    if sen and sen not in perfil.senioridades_aceitas:
        return ResultadoFiltro(False, f"senioridade {sen}")
    if not sen:
        avisos.append("senioridade não informada")

    anos = anos_exigidos(vaga.descricao)
    if anos is not None and anos > perfil.max_anos_exigidos:
        return ResultadoFiltro(False, f"pede {anos} anos de experiência")

    motivo = _local_ok(vaga.modelo, vaga.cidade, vaga.uf, perfil, avisos)
    if motivo:
        return ResultadoFiltro(False, motivo)

    if parece_ingles(vaga.descricao):
        return ResultadoFiltro(False, "vaga escrita em inglês")
    if _INGLES_RUIM.search(vaga.descricao or ""):
        return ResultadoFiltro(False, "exige inglês avançado ou fluente")
    if _FUSO.search(vaga.descricao or ""):
        avisos.append("pode exigir fuso do exterior")
    return ResultadoFiltro(True, avisos=avisos)


def pos_filtro(vaga, extracao: dict, perfil: Perfil) -> ResultadoFiltro:
    """Etapa 2: confirma com os campos extraídos pelo LLM."""
    avisos: list[str] = []
    # A área não descarta nem reduz a nota: títulos genéricos ("Desenvolvedor", "Programador",
    # "Engenheiro de Software") são decididos pela correspondência dos requisitos com o currículo.
    # Outras áreas (dados, QA, mobile, infra...) já caem no pré-filtro pelo título.
    if extracao.get("cargo_area") == "outro" and not titulo_indica_area(vaga.titulo):
        avisos.append("área não identificada pelo modelo")

    sen = extracao.get("senioridade", "nao_informado")
    if sen not in ("nao_informado", "", None) and sen not in perfil.senioridades_aceitas:
        return ResultadoFiltro(False, f"senioridade {sen} (descrição)")

    anos = extracao.get("anos_experiencia_min")
    if isinstance(anos, int) and anos > perfil.max_anos_exigidos:
        return ResultadoFiltro(False, f"pede {anos} anos de experiência")

    modelo = vaga.modelo or (extracao.get("modelo_trabalho") or "").replace("nao_informado", "")
    cidade = vaga.cidade or extracao.get("cidade") or ""
    uf = vaga.uf or extracao.get("uf") or ""
    motivo = _local_ok(modelo, cidade, uf, perfil, avisos)
    if motivo:
        return ResultadoFiltro(False, motivo)

    ingles = extracao.get("ingles", "nao_exigido")
    if extracao.get("vaga_em_ingles") or ingles in ("avancado", "fluente"):
        return ResultadoFiltro(False, f"exige inglês {ingles}")
    if extracao.get("fuso_exterior"):
        return ResultadoFiltro(False, "trabalho no fuso dos EUA ou Europa")

    contrato = extracao.get("contrato", "nao_informado")
    if contrato not in ("nao_informado", "", None, "outro") and contrato not in perfil.contratos_aceitos:
        return ResultadoFiltro(False, f"contrato {contrato}")
    if contrato in ("nao_informado", "", None):
        avisos.append("contrato não informado")
    return ResultadoFiltro(True, avisos=avisos)
