"""Servidor MCP local (stdio) para o Claude ler vagas e gravar os textos de candidatura.

Conecte no app do Claude (desktop) ou no Claude Code e peça, por exemplo:
"use o job-finder e gere os textos das vagas confirmadas com /gupy e /linkedin".
Nenhuma API paga é chamada: quem escreve é o Claude da sua assinatura.
"""

from __future__ import annotations

import hashlib
from typing import Optional

from mcp.server.mcpserver import MCPServer

from . import servicos
from .coletores import VagaColetada
from .config import obter_config
from .db import sessao
from .modelos import Status
from .perfil import carregar_perfil
from .pipeline import processar_pendentes, salvar_vaga

INSTRUCOES = """Servidor do job-finder, o sistema de busca de vagas de Jean.
- Vagas confirmadas no app (status em_candidatura) precisam dos textos de candidatura: use as skills
  /gupy (texto formal, texto leve e exatamente 3 skills) e /linkedin (mensagem de até 300 caracteres
  ao recrutador) e grave com salvar_textos.
- Vagas da zona cinzenta (nota perto do corte) devem ser avaliadas com a skill /analisar e
  registradas com marcar_revisada.
- Fonte de verdade: o currículo e o perfil (ler_perfil). Nunca invente experiência e nunca apresente
  conhecimento como experiência profissional. A experiência na IPM Sistemas terminou em fevereiro de 2026."""

mcp = MCPServer(name="job-finder", instructions=INSTRUCOES)
_cfg = obter_config()


def _compacta(v: dict) -> dict:
    chaves = ("id", "titulo", "empresa", "cidade", "uf", "modelo", "senioridade", "nota", "status", "url", "fonte", "recrutador_nome")
    out = {k: v.get(k) for k in chaves}
    if "analise" in v:
        out["analise"] = v["analise"]
    if "candidatura" in v:
        c = v["candidatura"]
        out["tem_textos"] = bool(c.get("texto_formal") or c.get("mensagem_recrutador"))
    return out


@mcp.tool()
def listar_vagas_confirmadas(somente_sem_textos: bool = True) -> list[dict]:
    """Vagas que Jean confirmou no app e que aguardam os textos de candidatura."""
    with sessao(_cfg.db) as s:
        vagas = [_compacta(v) for v in servicos.listar(s, Status.EM_CANDIDATURA)]
    return [v for v in vagas if not (somente_sem_textos and v.get("tem_textos"))]


@mcp.tool()
def listar_vagas(status: str = "compativel", limite: int = 30) -> list[dict]:
    """Lista vagas por status: compativel, em_candidatura, candidatada, abaixo_da_nota,
    descartada_filtro, recusada, sem_descricao ou coletada. Vários separados por vírgula."""
    with sessao(_cfg.db) as s:
        return [_compacta(v) for v in servicos.listar(s, status.split(","), limite)]


@mcp.tool()
def listar_zona_cinzenta(limite: int = 20) -> list[dict]:
    """Vagas com nota perto do corte ainda não revisadas pelo Claude; avalie com /analisar."""
    perfil = carregar_perfil(_cfg.perfil)
    with sessao(_cfg.db) as s:
        return [_compacta(v) for v in servicos.zona_cinzenta(s, perfil.nota_corte, limite)]


@mcp.tool()
def ler_vaga(vaga_id: int) -> dict:
    """Descrição completa, requisitos extraídos, detalhe da nota e textos já gravados de uma vaga."""
    with sessao(_cfg.db) as s:
        v = s.get(servicos.Vaga, vaga_id)
        if not v:
            raise ValueError(f"vaga {vaga_id} não encontrada")
        return servicos.vaga_resumo(s, v, com_descricao=True)


@mcp.tool()
def ler_perfil() -> dict:
    """Perfil de Jean usado nos filtros e na nota (skills profissionais x conhecimento, formação, região)."""
    p = carregar_perfil(_cfg.perfil)
    return {
        "perfil_de_exemplo": p.exemplo,
        "aviso": "perfil de exemplo: peça o currículo a Jean antes de escrever textos" if p.exemplo else "",
        "skills_profissionais": [s.nome for s in p.skills if s.nivel == "profissional"],
        "skills_conhecimento": [s.nome for s in p.skills if s.nivel == "conhecimento"],
        "formacao": p.formacao,
        "ingles": p.ingles,
        "regiao": f"{p.cidade_base}/{p.uf_base}, raio de {p.raio_km:.0f} km para presencial e híbrido",
        "senioridades": p.senioridades_aceitas,
        "nota_corte": p.nota_corte,
    }


@mcp.tool()
def salvar_textos(
    vaga_id: int,
    texto_formal: Optional[str] = None,
    texto_leve: Optional[str] = None,
    skills_gupy: Optional[list[str]] = None,
    mensagem_recrutador: Optional[str] = None,
    texto_preferencial: Optional[str] = None,
) -> dict:
    """Grava os textos de candidatura (aparecem no painel Candidatar do app).
    skills_gupy: exatamente 3. mensagem_recrutador e texto_preferencial: até 300 caracteres."""
    for nome, t in (("mensagem_recrutador", mensagem_recrutador), ("texto_preferencial", texto_preferencial)):
        if t and len(t) > 300:
            raise ValueError(f"{nome} tem {len(t)} caracteres; o limite é 300")
    if skills_gupy is not None and len(skills_gupy) != 3:
        raise ValueError("skills_gupy deve ter exatamente 3 itens")
    with sessao(_cfg.db) as s:
        c = servicos.atualizar_candidatura(
            s, vaga_id, texto_formal=texto_formal, texto_leve=texto_leve, skills_gupy=skills_gupy,
            mensagem_recrutador=mensagem_recrutador, texto_preferencial=texto_preferencial,
        )
        return {"ok": True, "vaga_id": vaga_id, "candidatura_id": c.id}


@mcp.tool()
def marcar_revisada(vaga_id: int, veredito: str, observacao: str = "", nota_ajustada: Optional[float] = None) -> dict:
    """Registra a revisão do Claude. veredito: compativel (vai para a pilha), abaixo_da_nota,
    descartar ou manter. A observação aparece no cartão da vaga."""
    with sessao(_cfg.db) as s:
        v = servicos.revisar(s, vaga_id, veredito, observacao, nota_ajustada)
        return {"ok": True, "vaga_id": v.id, "status": v.status, "nota": v.nota}


@mcp.tool()
def adicionar_vaga(url: str, titulo: str, descricao: str, empresa: str = "", cidade: str = "", uf: str = "", modelo: str = "") -> dict:
    """Cadastra uma vaga colada por Jean (ex.: do LinkedIn) e já roda filtros e nota.
    modelo: presencial, hibrido, remoto ou vazio."""
    c = VagaColetada(fonte="manual", id_externo=hashlib.sha1(url.encode()).hexdigest()[:12], url=url, titulo=titulo,
                     empresa=empresa, cidade=cidade, uf=uf.upper(), modelo=modelo, descricao=descricao)
    with sessao(_cfg.db) as s:
        v = salvar_vaga(s, c)
        if not v:
            raise ValueError("vaga já cadastrada")
        vid = v.id
    processar_pendentes(_cfg, limite=5, origem="vaga_avulsa")
    with sessao(_cfg.db) as s:
        return _compacta(servicos.vaga_resumo(s, s.get(servicos.Vaga, vid)))


@mcp.tool()
def completar_descricao(vaga_id: int, descricao: str) -> dict:
    """Cola a descrição de uma vaga vinda de alerta de e-mail (status sem_descricao) e a analisa."""
    with sessao(_cfg.db) as s:
        servicos.definir_descricao(s, vaga_id, descricao)
    processar_pendentes(_cfg, limite=5, origem="vaga_avulsa")
    with sessao(_cfg.db) as s:
        return _compacta(servicos.vaga_resumo(s, s.get(servicos.Vaga, vaga_id)))


def main() -> None:
    mcp.run("stdio")


if __name__ == "__main__":
    main()
