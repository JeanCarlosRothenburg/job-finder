"""Coletores de vagas. Cada fonte tem a mesma interface: `coletar()` devolve VagaColetada."""

from __future__ import annotations

from ..config import Config
from ..perfil import Perfil
from .base import VagaColetada
from .email_alertas import ColetorEmail
from .github import ColetorGitHub
from .gupy import ColetorGupy

__all__ = ["VagaColetada", "coletores_ativos"]


def coletores_ativos(cfg: Config, perfil: Perfil) -> list:
    coletores = [
        ColetorGupy(perfil.termos_busca),
        ColetorGitHub(perfil.repositorios_github, token=cfg.github_token),
    ]
    if cfg.imap_usuario and cfg.imap_senha:
        coletores.append(ColetorEmail(cfg.imap_host, cfg.imap_usuario, cfg.imap_senha, cfg.imap_pasta))
    return coletores
