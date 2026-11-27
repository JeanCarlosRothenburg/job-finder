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
        _migrar(engine)
        _engines[caminho] = engine
    return _engines[caminho]


def _migrar(engine) -> None:
    """Acrescenta colunas novas em bancos criados por versões anteriores (SQLite não faz isso sozinho)."""
    from sqlalchemy import inspect, text

    insp = inspect(engine)
    with engine.begin() as conn:
        for tabela in SQLModel.metadata.sorted_tables:
            if not insp.has_table(tabela.name):
                continue
            existentes = {c["name"] for c in insp.get_columns(tabela.name)}
            for col in tabela.columns:
                if col.name not in existentes:
                    tipo = col.type.compile(dialect=engine.dialect)
                    conn.execute(text(f'ALTER TABLE "{tabela.name}" ADD COLUMN "{col.name}" {tipo}'))


def sessao(caminho: str) -> Session:
    return Session(obter_engine(caminho), expire_on_commit=False)
