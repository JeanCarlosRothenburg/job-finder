"""Perfil do candidato (perfil.yaml): fonte de verdade para filtros e nota."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .texto import contem_termo, normalizar

PERFIL_EXEMPLO = Path(__file__).resolve().parents[2] / "perfil.exemplo.yaml"

# Sinônimos genéricos de stacks. O perfil pode acrescentar os seus em `sinonimos`.
SINONIMOS_PADRAO: dict[str, list[str]] = {
    "javascript": ["js", "ecmascript", "es6"],
    "typescript": ["ts"],
    "node.js": ["node", "nodejs"],
    "react": ["react.js", "reactjs"],
    "vue": ["vue.js", "vuejs"],
    "angular": ["angularjs", "angular.js"],
    "postgresql": ["postgres", "psql"],
    "sql server": ["mssql", "sqlserver"],
    "c#": ["csharp", "c sharp"],
    ".net": ["dotnet", ".net core", "asp.net", "asp.net core"],
    "spring": ["spring boot", "springboot"],
    "git": ["github", "gitlab", "controle de versao"],
    "docker": ["containers", "conteineres"],
    "ci/cd": ["ci cd", "integracao continua", "entrega continua", "pipelines"],
    "testes automatizados": ["testes unitarios", "tdd", "testes de integracao", "unit tests"],
    "scrum": ["metodologias ageis", "agil", "kanban"],
    "apis rest": ["rest", "restful", "api rest", "apis restful", "web services"],
    "html": ["html5"],
    "css": ["css3", "sass", "scss"],
    "aws": ["amazon web services"],
    "python": ["python3"],
    "php": ["laravel"],
}


@dataclass
class Skill:
    nome: str
    nivel: str  # profissional | conhecimento
    sinonimos: list[str] = field(default_factory=list)
    anos: float | None = None

    def termos(self, extras: dict[str, list[str]]) -> list[str]:
        base = normalizar(self.nome)
        t = [self.nome, *self.sinonimos, *extras.get(base, [])]
        # sinônimo reverso: se "node" está no dicionário como sinônimo de "node.js"
        for chave, lista in extras.items():
            if base in [normalizar(x) for x in lista]:
                t.append(chave)
        return t


@dataclass
class Perfil:
    nome: str = "Candidato"
    cidade_base: str = "Presidente Getúlio"
    uf_base: str = "SC"
    raio_km: float = 70
    cidades_aceitas_extra: list[str] = field(default_factory=list)
    senioridades_aceitas: list[str] = field(default_factory=lambda: ["junior", "pleno"])
    max_anos_exigidos: int = 4
    contratos_aceitos: list[str] = field(default_factory=lambda: ["clt", "pj"])
    nota_corte: float = 8.0
    peso_obrigatorio: float = 0.8
    peso_diferencial: float = 0.2
    trava_obrigatorio_central: float = 7.0
    termos_busca: list[str] = field(default_factory=list)
    titulos_incluir: list[str] = field(default_factory=list)
    titulos_excluir: list[str] = field(default_factory=list)
    skills: list[Skill] = field(default_factory=list)
    formacao: list[str] = field(default_factory=list)
    ingles: str = "tecnico"
    sinonimos: dict[str, list[str]] = field(default_factory=dict)
    repositorios_github: list[str] = field(default_factory=list)
    exemplo: bool = False

    # ------------------------------------------------------------------ skills
    def _sinonimos(self) -> dict[str, list[str]]:
        d = {normalizar(k): list(v) for k, v in SINONIMOS_PADRAO.items()}
        for k, v in self.sinonimos.items():
            d.setdefault(normalizar(k), []).extend(v)
        return d

    def nivel_de(self, requisito: str) -> tuple[str | None, str | None]:
        """Devolve (nivel, skill) para um requisito: profissional, conhecimento ou (None, None)."""
        req = normalizar(requisito)
        if not req:
            return None, None
        extras = self._sinonimos()
        melhor: tuple[str | None, str | None] = (None, None)
        for skill in self.skills:
            for termo in skill.termos(extras):
                tn = normalizar(termo)
                if not tn:
                    continue
                if req == tn or contem_termo(req, tn) or (len(req) > 2 and contem_termo(tn, req)):
                    if skill.nivel == "profissional":
                        return "profissional", skill.nome
                    melhor = ("conhecimento", skill.nome)
        return melhor


def _ler_skills(dados: dict) -> list[Skill]:
    skills: list[Skill] = []
    for nivel in ("profissional", "conhecimento"):
        for item in (dados.get("skills") or {}).get(nivel, []) or []:
            if isinstance(item, str):
                skills.append(Skill(nome=item, nivel=nivel))
            else:
                skills.append(
                    Skill(
                        nome=item["nome"],
                        nivel=nivel,
                        sinonimos=item.get("sinonimos", []) or [],
                        anos=item.get("anos"),
                    )
                )
    return skills


def carregar_perfil(caminho: str | Path) -> Perfil:
    p = Path(caminho)
    exemplo = False
    if not p.is_file():
        local = Path.cwd() / "perfil.exemplo.yaml"
        p, exemplo = (local if local.is_file() else PERFIL_EXEMPLO), True
    dados = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    loc = dados.get("localidade", {}) or {}
    nota = dados.get("nota", {}) or {}
    filtros = dados.get("filtros", {}) or {}
    coleta = dados.get("coleta", {}) or {}
    return Perfil(
        nome=dados.get("nome", "Candidato"),
        cidade_base=loc.get("cidade_base", "Presidente Getúlio"),
        uf_base=loc.get("uf_base", "SC"),
        raio_km=float(loc.get("raio_km", 70)),
        cidades_aceitas_extra=loc.get("cidades_aceitas_extra", []) or [],
        senioridades_aceitas=filtros.get("senioridades_aceitas", ["junior", "pleno"]),
        max_anos_exigidos=int(filtros.get("max_anos_exigidos", 4)),
        contratos_aceitos=filtros.get("contratos_aceitos", ["clt", "pj"]),
        titulos_incluir=filtros.get("titulos_incluir", []) or [],
        titulos_excluir=filtros.get("titulos_excluir", []) or [],
        nota_corte=float(nota.get("corte", 8)),
        peso_obrigatorio=float(nota.get("peso_obrigatorio", 0.8)),
        peso_diferencial=float(nota.get("peso_diferencial", 0.2)),
        trava_obrigatorio_central=float(nota.get("trava_obrigatorio_central", 7)),
        termos_busca=coleta.get("termos_busca", []) or [],
        repositorios_github=coleta.get("repositorios_github", []) or [],
        skills=_ler_skills(dados),
        formacao=dados.get("formacao", []) or [],
        ingles=(dados.get("idiomas", {}) or {}).get("ingles", "tecnico"),
        sinonimos=dados.get("sinonimos", {}) or {},
        exemplo=exemplo or bool(dados.get("exemplo", False)),
    )
