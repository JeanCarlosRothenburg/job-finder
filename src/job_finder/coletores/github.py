"""Coletor de repositórios de vagas no GitHub (cada vaga é uma issue com etiquetas)."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Iterable

import httpx

from ..localidade import UFS
from ..texto import normalizar
from .base import USER_AGENT, VagaColetada, parse_data

_MODELO = {"remoto": "remoto", "remote": "remoto", "home office": "remoto", "hibrido": "hibrido",
           "hybrid": "hibrido", "presencial": "presencial", "alocado": "presencial"}
_SENIOR = {"junior": "junior", "jr": "junior", "pleno": "pleno", "senior": "senior", "estagio": "estagio",
           "especialista": "especialista"}
_CONTRATO = {"clt": "clt", "pj": "pj"}


def interpretar_issue(repo: str, issue: dict) -> VagaColetada | None:
    if "pull_request" in issue:
        return None
    titulo = (issue.get("title") or "").strip()
    etiquetas = [l["name"] if isinstance(l, dict) else str(l) for l in issue.get("labels", [])]
    modelo = senioridade = contrato = cidade = uf = ""

    for e in etiquetas:
        n = normalizar(e)
        modelo = modelo or _MODELO.get(n, "")
        senioridade = senioridade or _SENIOR.get(n, "")
        contrato = contrato or _CONTRATO.get(n, "")

    # Título no formato "[Cidade/UF] Cargo @ Empresa" ou "[Remoto] Cargo na Empresa"
    for bloco in re.findall(r"\[([^\]]+)\]", titulo):
        n = normalizar(bloco)
        if n in _MODELO:
            modelo = modelo or _MODELO[n]
            continue
        m = re.match(r"(.+?)\s*[/\-,]\s*([A-Za-z]{2})$", bloco.strip())
        if m and m.group(2).upper() in UFS:
            cidade, uf = m.group(1).strip(), m.group(2).upper()
    empresa = ""
    m = re.search(r"\s@\s*(.+)$", titulo) or re.search(r"\s(?:na|no|para a|para o)\s+([A-Z][\w&.\- ]+)$", titulo)
    if m:
        empresa = m.group(1).strip(" -[]")
    titulo_limpo = re.sub(r"\[[^\]]*\]", "", titulo)
    titulo_limpo = re.sub(r"\s@\s*.+$", "", titulo_limpo).strip(" -|")

    return VagaColetada(
        fonte=f"github:{repo}",
        id_externo=str(issue["number"]),
        url=issue.get("html_url", ""),
        titulo=titulo_limpo or titulo,
        empresa=empresa,
        cidade=cidade,
        uf=uf,
        modelo=modelo,
        descricao=issue.get("body") or "",
        senioridade=senioridade,
        contrato=contrato,
        etiquetas=etiquetas,
        publicada_em=parse_data(issue.get("created_at")),
    )


class ColetorGitHub:
    nome = "github"

    def __init__(self, repositorios: list[str], token: str = "", dias: int = 21, cliente: httpx.Client | None = None):
        self.repos = repositorios
        self.dias = dias
        cab = {"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"}
        if token:
            cab["Authorization"] = f"Bearer {token}"
        self.cli = cliente or httpx.Client(timeout=30, headers=cab)

    def coletar(self) -> Iterable[VagaColetada]:
        desde = (datetime.now(timezone.utc) - timedelta(days=self.dias)).strftime("%Y-%m-%dT%H:%M:%SZ")
        erros = []
        for repo in self.repos:
            for pagina in range(1, 6):
                try:
                    r = self.cli.get(
                        f"https://api.github.com/repos/{repo}/issues",
                        params={"state": "open", "per_page": 100, "page": pagina, "since": desde, "sort": "created"},
                    )
                    r.raise_for_status()
                except httpx.HTTPError as e:  # um repositório com erro não impede os outros
                    erros.append(f"{repo}: {e.__class__.__name__}")
                    break
                itens = r.json()
                for issue in itens:
                    vaga = interpretar_issue(repo, issue)
                    if vaga:
                        yield vaga
                if len(itens) < 100:
                    break
        if erros and len(erros) == len(self.repos):
            raise RuntimeError("; ".join(erros))
