"""Configuração por variáveis de ambiente, com leitura opcional de um arquivo .env."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def carregar_env(caminho: str | Path = ".env") -> None:
    """Lê um .env simples (CHAVE=valor) sem sobrescrever variáveis já definidas."""
    p = Path(caminho)
    if not p.is_file():
        return
    for linha in p.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        valor = valor.strip().strip('"').strip("'")
        os.environ.setdefault(chave.strip(), valor)


@dataclass
class Config:
    db: str = field(default_factory=lambda: os.getenv("JOBFINDER_DB", "dados/job_finder.db"))
    perfil: str = field(default_factory=lambda: os.getenv("JOBFINDER_PERFIL", "perfil.yaml"))
    ollama_url: str = field(default_factory=lambda: os.getenv("OLLAMA_URL", "http://localhost:11434"))
    ollama_modelo: str = field(default_factory=lambda: os.getenv("OLLAMA_MODELO", "qwen3:4b"))
    intervalo_horas: float = field(
        default_factory=lambda: float(os.getenv("JOBFINDER_INTERVALO_HORAS", "3") or 0)
    )
    github_token: str = field(default_factory=lambda: os.getenv("GITHUB_TOKEN", ""))
    imap_host: str = field(default_factory=lambda: os.getenv("IMAP_HOST", "imap.gmail.com"))
    imap_usuario: str = field(default_factory=lambda: os.getenv("IMAP_USUARIO", ""))
    imap_senha: str = field(default_factory=lambda: os.getenv("IMAP_SENHA_APP", ""))
    imap_pasta: str = field(default_factory=lambda: os.getenv("IMAP_PASTA", "INBOX"))


def obter_config() -> Config:
    carregar_env()
    return Config()
