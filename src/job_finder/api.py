"""API FastAPI e interface web (servida em /)."""

from __future__ import annotations

import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import servicos
from .coletores import VagaColetada
from .config import Config, obter_config
from .db import sessao
from .extracao import ollama_disponivel
from .modelos import Status
from .perfil import carregar_perfil
from .pipeline import ciclo, processar_em_andamento, processar_pendentes, recalcular_notas, salvar_vaga

WEB = Path(__file__).parent / "web"


class Decisao(BaseModel):
    decisao: str


class Enviada(BaseModel):
    canal: str = ""
    observacoes: str = ""


class Textos(BaseModel):
    texto_formal: Optional[str] = None
    texto_leve: Optional[str] = None
    skills_gupy: Optional[list[str]] = None
    mensagem_recrutador: Optional[str] = None
    texto_preferencial: Optional[str] = None
    observacoes: Optional[str] = None
    canal: Optional[str] = None


class Descricao(BaseModel):
    descricao: str


class VagaManual(BaseModel):
    url: str
    titulo: str
    empresa: str = ""
    descricao: str = ""
    cidade: str = ""
    uf: str = ""
    modelo: str = ""


def criar_app(cfg: Config | None = None, agendar: bool = True) -> FastAPI:
    cfg = cfg or obter_config()

    @asynccontextmanager
    async def ciclo_de_vida(app: FastAPI):
        sched = None
        if agendar:
            from .agendador import iniciar_agendador

            sched = iniciar_agendador(cfg)
        yield
        if sched:
            sched.shutdown(wait=False)

    app = FastAPI(title="job-finder", version="0.1.0", lifespan=ciclo_de_vida)
    app.state.cfg = cfg

    def _erro(fn):
        try:
            return fn()
        except servicos.ErroServico as e:
            raise HTTPException(400, str(e)) from e

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(WEB / "index.html")

    @app.get("/api/resumo")
    def resumo():
        perfil = carregar_perfil(cfg.perfil)
        ok, msg = ollama_disponivel(cfg.ollama_url, cfg.ollama_modelo)
        with sessao(cfg.db) as s:
            r = servicos.resumo(s)
        r.update(
            perfil_exemplo=perfil.exemplo,
            nota_corte=perfil.nota_corte,
            ollama={"ok": ok, "mensagem": msg, "modelo": cfg.ollama_modelo},
            processando=processar_em_andamento(),
        )
        return r

    @app.get("/api/vagas")
    def vagas(status: str = Status.COMPATIVEL, limite: int = 200):
        with sessao(cfg.db) as s:
            return servicos.listar(s, status.split(","), limite)

    @app.get("/api/vagas/{vaga_id}")
    def vaga(vaga_id: int):
        with sessao(cfg.db) as s:
            v = s.get(servicos.Vaga, vaga_id)
            if not v:
                raise HTTPException(404, "vaga não encontrada")
            return servicos.vaga_resumo(s, v, com_descricao=True)

    @app.post("/api/vagas/{vaga_id}/decisao")
    def decisao(vaga_id: int, corpo: Decisao):
        with sessao(cfg.db) as s:
            return _erro(lambda: servicos.vaga_resumo(s, servicos.decidir(s, vaga_id, corpo.decisao)))

    @app.post("/api/vagas/{vaga_id}/desfazer")
    def desfazer(vaga_id: int):
        with sessao(cfg.db) as s:
            return _erro(lambda: servicos.vaga_resumo(s, servicos.desfazer(s, vaga_id)))

    @app.post("/api/vagas/{vaga_id}/enviada")
    def enviada(vaga_id: int, corpo: Enviada):
        with sessao(cfg.db) as s:
            return _erro(lambda: servicos.vaga_resumo(s, servicos.marcar_enviada(s, vaga_id, corpo.canal, corpo.observacoes)))

    @app.patch("/api/vagas/{vaga_id}/candidatura")
    def textos(vaga_id: int, corpo: Textos):
        with sessao(cfg.db) as s:
            return _erro(lambda: servicos.atualizar_candidatura(s, vaga_id, **corpo.model_dump(exclude_none=True)).model_dump())

    @app.post("/api/vagas/{vaga_id}/descricao")
    def descricao(vaga_id: int, corpo: Descricao):
        with sessao(cfg.db) as s:
            _erro(lambda: servicos.definir_descricao(s, vaga_id, corpo.descricao))
        processar_pendentes(cfg, limite=5)
        with sessao(cfg.db) as s:
            return servicos.vaga_resumo(s, s.get(servicos.Vaga, vaga_id))

    @app.get("/api/vagas/{vaga_id}/para-claude", response_class=PlainTextResponse)
    def para_claude(vaga_id: int):
        with sessao(cfg.db) as s:
            return _erro(lambda: servicos.texto_para_claude(s, vaga_id))

    @app.post("/api/vagas/manual")
    def manual(corpo: VagaManual):
        import hashlib

        c = VagaColetada(fonte="manual", id_externo=hashlib.sha1(corpo.url.encode()).hexdigest()[:12],
                         **corpo.model_dump())
        with sessao(cfg.db) as s:
            v = salvar_vaga(s, c)
            if not v:
                raise HTTPException(409, "vaga já cadastrada")
            vid = v.id
        processar_pendentes(cfg, limite=5)
        with sessao(cfg.db) as s:
            return servicos.vaga_resumo(s, s.get(servicos.Vaga, vid))

    @app.post("/api/coletar")
    def disparar_ciclo():
        if processar_em_andamento():
            return {"iniciado": False, "mensagem": "já existe um ciclo em andamento"}
        threading.Thread(target=ciclo, args=(cfg,), daemon=True).start()
        return {"iniciado": True}

    @app.post("/api/recalcular")
    def recalcular():
        return {"vagas": recalcular_notas(cfg)}

    app.mount("/static", StaticFiles(directory=WEB), name="static")
    return app
