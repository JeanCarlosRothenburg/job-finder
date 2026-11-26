"""Coletor da Gupy: JSON público usado pelo portal de vagas (não é API oficial e pode mudar).

Desde nov/2026 o portal usa `https://portal.gupy.io/api/job-search/jobs?jobName=...&limit=...&offset=...`
(os antigos `/api/v1/jobs` e `portal.api.gupy.io/api/job` respondem 404). A resposta traz a
descrição completa e `pagination.total`. O coletor tenta, em ordem, os endereços de `ENDPOINTS`
(ou o de `GUPY_ENDPOINT`, se definido) e usa o primeiro que responder.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Iterable

import httpx

from ..texto import limpar_html
from .base import USER_AGENT, VagaColetada, parse_data

log = logging.getLogger(__name__)

ENDPOINTS = [
    "https://portal.gupy.io/api/job-search/jobs",
    "https://portal.api.gupy.io/api/job",
    "https://portal.api.gupy.io/api/v1/jobs",
    "https://employability-portal.gupy.io/api/v1/jobs",
]

MODELOS = {"remote": "remoto", "hybrid": "hibrido", "on-site": "presencial", "onsite": "presencial"}


def _parse_item(item: dict) -> VagaColetada:
    modelo = MODELOS.get(str(item.get("workplaceType", "")).lower(), "")
    if not modelo and item.get("isRemoteWork"):
        modelo = "remoto"
    empresa = (item.get("careerPageName") or item.get("companyName") or "").strip().rstrip(">").strip()
    url = item.get("jobUrl") or item.get("careerPageUrl") or ""
    tipo = str(item.get("type", ""))
    contrato = "clt" if "effective" in tipo else "pj" if "legal_entity" in tipo else ""
    if "internship" in tipo or "trainee" in tipo:
        contrato = tipo
    return VagaColetada(
        fonte="gupy",
        id_externo=str(item.get("id")),
        url=url,
        titulo=(item.get("name") or "").strip(),
        empresa=empresa.strip(),
        cidade=(item.get("city") or "").strip(),
        uf=_uf(item.get("state") or ""),
        modelo=modelo,
        descricao=limpar_html(item.get("description") or ""),
        contrato=contrato,
        publicada_em=parse_data(item.get("publishedDate")),
    )


_ESTADOS = {
    "acre": "AC", "alagoas": "AL", "amapa": "AP", "amazonas": "AM", "bahia": "BA", "ceara": "CE",
    "distrito federal": "DF", "espirito santo": "ES", "goias": "GO", "maranhao": "MA", "mato grosso": "MT",
    "mato grosso do sul": "MS", "minas gerais": "MG", "para": "PA", "paraiba": "PB", "parana": "PR",
    "pernambuco": "PE", "piaui": "PI", "rio de janeiro": "RJ", "rio grande do norte": "RN",
    "rio grande do sul": "RS", "rondonia": "RO", "roraima": "RR", "santa catarina": "SC",
    "sao paulo": "SP", "sergipe": "SE", "tocantins": "TO",
}


def _uf(estado: str) -> str:
    from ..texto import normalizar

    e = estado.strip()
    if len(e) == 2:
        return e.upper()
    return _ESTADOS.get(normalizar(e), "")


def extrair_descricao_pagina(html: str) -> str:
    """Pega a descrição completa do __NEXT_DATA__ da página da vaga (portal de carreira)."""
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if m:
        try:
            dados = json.loads(m.group(1))
            job = dados.get("props", {}).get("pageProps", {}).get("job", {}) or {}
            partes = [job.get(k) for k in ("description", "responsibilities", "prerequisites", "relevantExperiences")]
            texto = "\n\n".join(limpar_html(p) for p in partes if p)
            if texto:
                return texto
        except json.JSONDecodeError:
            pass
    return limpar_html(html)[:15000]


class ColetorGupy:
    nome = "gupy"

    def __init__(self, termos: list[str], limite_por_termo: int = 200, pausa: float = 1.0, cliente: httpx.Client | None = None):
        self.termos = termos or ["desenvolvedor"]
        self.limite = limite_por_termo
        self.pausa = pausa
        self.cli = cliente or httpx.Client(timeout=30, headers={"User-Agent": USER_AGENT}, follow_redirects=True)
        self.endpoint: str | None = os.getenv("GUPY_ENDPOINT") or None

    def _buscar(self, termo: str, offset: int) -> dict:
        candidatos = [self.endpoint] if self.endpoint else ENDPOINTS
        ultimo_erro: Exception | None = None
        for url in candidatos:
            try:
                r = self.cli.get(url, params={"jobName": termo, "offset": offset, "limit": min(self.limite, 100)},
                                 headers={"Accept": "application/json", "Referer": "https://portal.gupy.io/"})
                if r.status_code == 404:
                    continue
                r.raise_for_status()
                self.endpoint = url
                return r.json()
            except httpx.HTTPError as e:
                ultimo_erro = e
        raise RuntimeError(f"nenhum endpoint da Gupy respondeu (último erro: {ultimo_erro})")

    def completar_descricao(self, vaga: VagaColetada) -> None:
        if len(vaga.descricao) >= 300 or not vaga.url:
            return
        try:
            r = self.cli.get(vaga.url)
            if r.status_code == 200:
                vaga.descricao = extrair_descricao_pagina(r.text) or vaga.descricao
        except httpx.HTTPError as e:
            log.warning("gupy: não li a página %s: %s", vaga.url, e)
        time.sleep(self.pausa)

    def coletar(self) -> Iterable[VagaColetada]:
        vistos: set[str] = set()
        for termo in self.termos:
            offset = 0
            while offset < self.limite:
                dados = self._buscar(termo, offset)
                itens = dados.get("data", []) or []
                for item in itens:
                    vaga = _parse_item(item)
                    if vaga.id_externo in vistos or not vaga.titulo:
                        continue
                    vistos.add(vaga.id_externo)
                    yield vaga
                total = (dados.get("pagination") or {}).get("total") or 0
                offset += len(itens)
                time.sleep(self.pausa)
                if not itens or offset >= total:
                    break
