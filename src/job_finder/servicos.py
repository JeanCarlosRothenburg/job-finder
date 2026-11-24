"""Operações sobre vagas e candidaturas, usadas pela API web e pelo servidor MCP."""

from __future__ import annotations

from typing import Any

from sqlmodel import Session, func, select

from .modelos import Analise, Candidatura, FonteExecucao, Status, Vaga, agora


class ErroServico(ValueError):
    pass


def _vaga(s: Session, vaga_id: int) -> Vaga:
    vaga = s.get(Vaga, vaga_id)
    if not vaga:
        raise ErroServico(f"vaga {vaga_id} não encontrada")
    return vaga


def ultima_analise(s: Session, vaga_id: int) -> Analise | None:
    return s.exec(select(Analise).where(Analise.vaga_id == vaga_id).order_by(Analise.id.desc())).first()


def candidatura_de(s: Session, vaga_id: int) -> Candidatura | None:
    return s.exec(select(Candidatura).where(Candidatura.vaga_id == vaga_id)).first()


def vaga_resumo(s: Session, vaga: Vaga, com_descricao: bool = False) -> dict[str, Any]:
    d = vaga.model_dump(exclude={"descricao", "hash_descricao", "chave_dedup"})
    if com_descricao:
        d["descricao"] = vaga.descricao
    a = ultima_analise(s, vaga.id)
    if a:
        det = a.detalhe_nota_json or {}
        d["analise"] = {
            "modelo_llm": a.modelo_llm,
            "atende_profissional": det.get("atende_profissional", []),
            "atende_conhecimento": det.get("atende_conhecimento", []),
            "nao_atende": det.get("nao_atende", []),
            "avisos": det.get("avisos", []),
            "travada": det.get("travada", False),
            "incompleta": det.get("incompleta", False),
        }
        if com_descricao:
            d["analise"]["requisitos"] = det.get("requisitos", [])
            d["analise"]["extracao"] = a.extracao_json
    c = candidatura_de(s, vaga.id)
    if c:
        d["candidatura"] = c.model_dump()
    return d


def listar(s: Session, status: str | list[str], limite: int = 200) -> list[dict]:
    estados = [status] if isinstance(status, str) else status
    q = select(Vaga).where(Vaga.status.in_(estados))
    if Status.CANDIDATADA in estados:
        q = q.join(Candidatura, Candidatura.vaga_id == Vaga.id, isouter=True).order_by(Candidatura.enviada_em.desc())
    else:
        q = q.order_by(Vaga.nota.desc().nulls_last(), Vaga.publicada_em.desc().nulls_last(), Vaga.id.desc())
    return [vaga_resumo(s, v) for v in s.exec(q.limit(limite)).all()]


def resumo(s: Session) -> dict:
    contagem = dict(s.exec(select(Vaga.status, func.count()).group_by(Vaga.status)).all())
    execucoes = s.exec(select(FonteExecucao).order_by(FonteExecucao.id.desc()).limit(10)).all()
    return {"contagem": contagem, "ultimas_coletas": [e.model_dump() for e in execucoes]}


def decidir(s: Session, vaga_id: int, decisao: str) -> Vaga:
    vaga = _vaga(s, vaga_id)
    if vaga.status != Status.COMPATIVEL:
        raise ErroServico(f"a vaga está em '{vaga.status}', não na pilha")
    if decisao not in ("confirmar", "recusar"):
        raise ErroServico("decisão deve ser 'confirmar' ou 'recusar'")
    c = candidatura_de(s, vaga_id) or Candidatura(vaga_id=vaga_id, decisao="")
    c.decisao = "confirmada" if decisao == "confirmar" else "recusada"
    c.decidida_em = agora()
    c.canal = c.canal or _canal_padrao(vaga)
    vaga.status = Status.EM_CANDIDATURA if decisao == "confirmar" else Status.RECUSADA
    s.add_all([c, vaga])
    s.commit()
    return vaga


def _canal_padrao(vaga: Vaga) -> str:
    if vaga.fonte == "gupy":
        return "gupy"
    if vaga.fonte in ("linkedin", "indeed"):
        return vaga.fonte
    return "manual"


def desfazer(s: Session, vaga_id: int) -> Vaga:
    """Volta a vaga para a pilha (desfazer swipe ou desistir no meio da candidatura)."""
    vaga = _vaga(s, vaga_id)
    if vaga.status not in (Status.EM_CANDIDATURA, Status.RECUSADA):
        raise ErroServico(f"não dá para desfazer uma vaga em '{vaga.status}'")
    c = candidatura_de(s, vaga_id)
    if c and not (c.texto_formal or c.mensagem_recrutador):
        s.delete(c)
    elif c:
        c.decisao = ""
        s.add(c)
    vaga.status = Status.COMPATIVEL
    s.add(vaga)
    s.commit()
    return vaga


def marcar_enviada(s: Session, vaga_id: int, canal: str = "", observacoes: str = "") -> Vaga:
    vaga = _vaga(s, vaga_id)
    if vaga.status != Status.EM_CANDIDATURA:
        raise ErroServico(f"a vaga está em '{vaga.status}'; confirme-a antes")
    c = candidatura_de(s, vaga_id) or Candidatura(vaga_id=vaga_id, decisao="confirmada")
    c.enviada_em = agora()
    c.canal = canal or c.canal or _canal_padrao(vaga)
    if observacoes:
        c.observacoes = observacoes
    vaga.status = Status.CANDIDATADA
    s.add_all([c, vaga])
    s.commit()
    return vaga


CAMPOS_TEXTO = ("texto_formal", "texto_leve", "skills_gupy", "mensagem_recrutador", "texto_preferencial", "observacoes", "canal")


def atualizar_candidatura(s: Session, vaga_id: int, **campos) -> Candidatura:
    vaga = _vaga(s, vaga_id)
    c = candidatura_de(s, vaga_id)
    if not c:
        if vaga.status not in (Status.EM_CANDIDATURA, Status.COMPATIVEL, Status.CANDIDATADA):
            raise ErroServico(f"a vaga está em '{vaga.status}'")
        c = Candidatura(vaga_id=vaga_id, decisao="confirmada" if vaga.status != Status.COMPATIVEL else "")
    for k, v in campos.items():
        if k in CAMPOS_TEXTO and v is not None:
            setattr(c, k, v)
    if c.skills_gupy and len(c.skills_gupy) > 3:
        raise ErroServico("a Gupy aceita exatamente 3 skills")
    s.add(c)
    s.commit()
    s.refresh(c)
    return c


def revisar(s: Session, vaga_id: int, veredito: str, observacao: str = "", nota: float | None = None) -> Vaga:
    """Revisão do Claude (/analisar) para vagas na zona cinzenta."""
    vaga = _vaga(s, vaga_id)
    destinos = {"compativel": Status.COMPATIVEL, "abaixo_da_nota": Status.ABAIXO_DA_NOTA, "descartar": Status.DESCARTADA_FILTRO, "manter": vaga.status}
    if veredito not in destinos:
        raise ErroServico(f"veredito deve ser um de {list(destinos)}")
    if vaga.status in (Status.EM_CANDIDATURA, Status.CANDIDATADA) and veredito != "manter":
        raise ErroServico("a candidatura já foi iniciada; use 'manter'")
    vaga.status = destinos[veredito]
    if veredito == "descartar":
        vaga.motivo_descarte = f"Claude: {observacao}"[:500]
    if nota is not None:
        vaga.nota = round(float(nota), 1)
    vaga.revisada_claude = True
    vaga.observacao_claude = observacao
    s.add(vaga)
    s.commit()
    return vaga


def zona_cinzenta(s: Session, perfil_corte: float, limite: int = 30) -> list[dict]:
    q = (
        select(Vaga)
        .where(Vaga.status.in_([Status.ABAIXO_DA_NOTA, Status.COMPATIVEL]), Vaga.revisada_claude == False)  # noqa: E712
        .where(Vaga.nota >= perfil_corte - 1, Vaga.nota < perfil_corte + 0.5)
        .order_by(Vaga.nota.desc())
        .limit(limite)
    )
    return [vaga_resumo(s, v) for v in s.exec(q).all()]


def definir_descricao(s: Session, vaga_id: int, descricao: str) -> Vaga:
    from .texto import hash_texto

    vaga = _vaga(s, vaga_id)
    if len(descricao.strip()) < 50:
        raise ErroServico("cole a descrição completa da vaga")
    vaga.descricao = descricao.strip()
    vaga.hash_descricao = hash_texto(vaga.descricao)
    vaga.status = Status.COLETADA
    s.add(vaga)
    s.commit()
    return vaga


def texto_para_claude(s: Session, vaga_id: int) -> str:
    """Plano B sem MCP: texto pronto para colar numa conversa com o Claude."""
    vaga = _vaga(s, vaga_id)
    a = ultima_analise(s, vaga_id)
    det = (a.detalhe_nota_json if a else {}) or {}
    linhas = [
        f"/gupy {vaga.titulo} na empresa {vaga.empresa}",
        "",
        f"Link: {vaga.url}",
        f"Local: {vaga.cidade}/{vaga.uf} ({vaga.modelo or 'modelo não informado'})",
        f"Nota do job-finder: {vaga.nota}",
        f"Atendo com experiência: {', '.join(det.get('atende_profissional', [])) or '-'}",
        f"Atendo só com conhecimento: {', '.join(det.get('atende_conhecimento', [])) or '-'}",
        f"Não atendo: {', '.join(det.get('nao_atende', [])) or '-'}",
        "",
        "Descrição da vaga:",
        vaga.descricao,
    ]
    return "\n".join(linhas)
