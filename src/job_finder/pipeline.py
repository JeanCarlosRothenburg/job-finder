"""Coleta, deduplicação, filtros, extração e nota."""

from __future__ import annotations

import logging
import threading
from dataclasses import asdict

from sqlmodel import Session, select

from .coletores import VagaColetada, coletores_ativos
from .config import Config
from .db import sessao
from .extracao import VERSAO_PROMPT, extrair_heuristica, extrair_ollama, ollama_disponivel
from .filtros import _titulo_ok, pos_filtro, pre_filtro
from .modelos import Analise, FonteExecucao, Status, Vaga, agora
from .nota import calcular_nota
from .perfil import Perfil, carregar_perfil
from .texto import chave_dedup, hash_texto

log = logging.getLogger(__name__)
_trava = threading.Lock()


# ------------------------------------------------------------------ gravação
def salvar_vaga(s: Session, c: VagaColetada) -> Vaga | None:
    """Grava a vaga se ela for nova. Devolve None para duplicadas."""
    existe = s.exec(select(Vaga).where(Vaga.fonte == c.fonte, Vaga.id_externo == c.id_externo)).first()
    if existe:
        return None
    chave = chave_dedup(c.empresa, c.titulo) if c.empresa else ""
    hd = hash_texto(c.descricao)
    if chave and s.exec(select(Vaga).where(Vaga.chave_dedup == chave)).first():
        return None  # mesma vaga publicada em outra fonte
    if hd and len(c.descricao) > 200 and s.exec(select(Vaga).where(Vaga.hash_descricao == hd)).first():
        return None
    dados = asdict(c)
    sem_desc = dados.pop("sem_descricao")
    vaga = Vaga(**dados, chave_dedup=chave, hash_descricao=hd,
                status=Status.SEM_DESCRICAO if sem_desc and not c.descricao else Status.COLETADA)
    s.add(vaga)
    s.commit()
    s.refresh(vaga)
    return vaga


def coletar(cfg: Config, perfil: Perfil, nomes: list[str] | None = None) -> dict[str, int | str]:
    resultado: dict[str, int | str] = {}
    for coletor in coletores_ativos(cfg, perfil):
        if nomes and coletor.nome not in nomes:
            continue
        with sessao(cfg.db) as s:
            execucao = FonteExecucao(fonte=coletor.nome)
            s.add(execucao)
            s.commit()
            novas = 0
            try:
                for c in coletor.coletar():
                    # Completa a descrição (uma requisição a mais) só se o título passa no filtro
                    if hasattr(coletor, "completar_descricao") and not _titulo_ok(c.titulo, perfil):
                        if not s.exec(select(Vaga).where(Vaga.fonte == c.fonte, Vaga.id_externo == c.id_externo)).first():
                            coletor.completar_descricao(c)
                    if salvar_vaga(s, c):
                        novas += 1
                resultado[coletor.nome] = novas
            except Exception as e:  # noqa: BLE001 - uma fonte com erro não derruba as outras
                log.exception("coletor %s falhou", coletor.nome)
                execucao.erros = f"{e.__class__.__name__}: {e}"[:1000]
                resultado[coletor.nome] = f"erro: {execucao.erros}"
            execucao.vagas_novas = novas
            execucao.terminada_em = agora()
            s.add(execucao)
            s.commit()
    return resultado


# ------------------------------------------------------------------ análise
def analisar_vaga(s: Session, vaga: Vaga, perfil: Perfil, cfg: Config, usar_ollama: bool) -> Vaga:
    r1 = pre_filtro(vaga, perfil)
    if not r1.aprovada:
        vaga.status, vaga.motivo_descarte = Status.DESCARTADA_FILTRO, r1.motivo
        s.add(vaga)
        s.commit()
        return vaga

    modelo_llm = cfg.ollama_modelo
    try:
        extracao = extrair_ollama(vaga, cfg.ollama_url, cfg.ollama_modelo) if usar_ollama else None
    except Exception as e:  # noqa: BLE001
        log.warning("Ollama falhou na vaga %s (%s); usando heurística", vaga.id, e)
        extracao = None
    if extracao is None:
        extracao, modelo_llm = extrair_heuristica(vaga), "heuristica"

    _registrar(s, vaga, extracao, modelo_llm, perfil, r1.avisos)
    return vaga


def _registrar(s: Session, vaga: Vaga, extracao: dict, modelo_llm: str, perfil: Perfil, avisos: list[str]) -> None:
    for campo, chave in (("senioridade", "senioridade"), ("contrato", "contrato")):
        if not getattr(vaga, campo) and extracao.get(chave) not in ("nao_informado", None):
            setattr(vaga, campo, extracao[chave])
    if not vaga.modelo and extracao.get("modelo_trabalho") not in ("nao_informado", None):
        vaga.modelo = extracao["modelo_trabalho"]
    vaga.cidade = vaga.cidade or extracao.get("cidade", "")
    vaga.uf = vaga.uf or extracao.get("uf", "")
    vaga.idioma_exigido = extracao.get("ingles", "")
    vaga.recrutador_nome = vaga.recrutador_nome or extracao.get("recrutador_nome", "")

    r2 = pos_filtro(vaga, extracao, perfil)
    nota, detalhe = calcular_nota(extracao.get("requisitos", []), perfil)
    detalhe["avisos"] = sorted(set(avisos + r2.avisos))
    detalhe["incompleta"] = not extracao.get("requisitos")
    s.add(Analise(vaga_id=vaga.id, modelo_llm=modelo_llm, versao_prompt=VERSAO_PROMPT,
                  extracao_json=extracao, nota=nota, detalhe_nota_json=detalhe))
    vaga.nota = nota
    if not r2.aprovada:
        vaga.status, vaga.motivo_descarte = Status.DESCARTADA_FILTRO, r2.motivo
    elif nota >= perfil.nota_corte:
        vaga.status, vaga.motivo_descarte = Status.COMPATIVEL, ""
    else:
        vaga.status, vaga.motivo_descarte = Status.ABAIXO_DA_NOTA, f"nota {nota} < {perfil.nota_corte}"
    s.add(vaga)
    s.commit()


def processar_pendentes(cfg: Config, perfil: Perfil | None = None, limite: int = 200) -> dict[str, int]:
    perfil = perfil or carregar_perfil(cfg.perfil)
    usar_ollama, _ = ollama_disponivel(cfg.ollama_url, cfg.ollama_modelo)
    contagem: dict[str, int] = {}
    with sessao(cfg.db) as s:
        pendentes = s.exec(select(Vaga).where(Vaga.status == Status.COLETADA).limit(limite)).all()
        for vaga in pendentes:
            analisar_vaga(s, vaga, perfil, cfg, usar_ollama)
            contagem[vaga.status] = contagem.get(vaga.status, 0) + 1
    return contagem


def recalcular_notas(cfg: Config, perfil: Perfil | None = None) -> int:
    """Recalcula filtros e notas com a última extração (sem LLM), depois de mudar o perfil."""
    perfil = perfil or carregar_perfil(cfg.perfil)
    n = 0
    with sessao(cfg.db) as s:
        vagas = s.exec(select(Vaga).where(Vaga.status.in_([Status.COMPATIVEL, Status.ABAIXO_DA_NOTA, Status.DESCARTADA_FILTRO]))).all()
        for vaga in vagas:
            ultima = s.exec(select(Analise).where(Analise.vaga_id == vaga.id).order_by(Analise.id.desc())).first()
            r1 = pre_filtro(vaga, perfil)
            if not r1.aprovada:
                vaga.status, vaga.motivo_descarte = Status.DESCARTADA_FILTRO, r1.motivo
                s.add(vaga)
                s.commit()
            elif ultima:
                _registrar(s, vaga, ultima.extracao_json, ultima.modelo_llm, perfil, r1.avisos)
            else:
                vaga.status = Status.COLETADA
                s.add(vaga)
                s.commit()
            n += 1
    return n


def ciclo(cfg: Config) -> dict:
    """Uma rodada completa (usada pelo agendador): coleta e análise."""
    if not _trava.acquire(blocking=False):
        return {"ignorado": "já existe um ciclo em andamento"}
    try:
        perfil = carregar_perfil(cfg.perfil)
        return {"coleta": coletar(cfg, perfil), "analise": processar_pendentes(cfg, perfil)}
    finally:
        _trava.release()


def processar_em_andamento() -> bool:
    return _trava.locked()
