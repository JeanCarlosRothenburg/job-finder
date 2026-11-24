"""Conexão com o SQLite."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine

from . import modelos  # noqa: F401  (registra as tabelas)

_engines: dict[str, object] = {}


def obter_engine(caminho: str):
    if caminho not in _engines:
        if caminho != ":memory:":
            Path(caminho).parent.mkdir(parents=True, exist_ok=True)
        url = "sqlite://" if caminho == ":memory:" else f"sqlite:///{caminho}"
        kwargs: dict = {"connect_args": {"check_same_thread": False}}
        if caminho == ":memory:":
            from sqlalchemy.pool import StaticPool

            kwargs["poolclass"] = StaticPool
        engine = create_engine(url, **kwargs)

        @event.listens_for(engine, "connect")
        def _pragmas(conn, _):  # WAL deixa a API ler enquanto o agendador grava
            cur = conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

        SQLModel.metadata.create_all(engine)
        _engines[caminho] = engine
    return _engines[caminho]


def sessao(caminho: str) -> Session:
    return Session(obter_engine(caminho), expire_on_commit=False)
