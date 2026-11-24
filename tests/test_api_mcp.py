import asyncio

from fastapi.testclient import TestClient

from job_finder.api import criar_app
from job_finder.coletores import VagaColetada
from job_finder.db import sessao
from job_finder.modelos import Status, Vaga
from job_finder.pipeline import processar_pendentes, salvar_vaga

from .conftest import DESCRICAO_BOA


def _semear(cfg):
    with sessao(cfg.db) as s:
        salvar_vaga(s, VagaColetada(fonte="gupy", id_externo="1", url="https://a.gupy.io/jobs/1",
                                    titulo="Desenvolvedor Back-end Java Pleno", empresa="ACME", modelo="remoto",
                                    descricao=DESCRICAO_BOA))
        salvar_vaga(s, VagaColetada(fonte="gupy", id_externo="2", url="https://a.gupy.io/jobs/2",
                                    titulo="Desenvolvedor Java Sênior", empresa="ACME", descricao=DESCRICAO_BOA + " Vaga sênior."))
        # duplicada entre fontes (mesma empresa e título)
        assert salvar_vaga(s, VagaColetada(fonte="github:x/y", id_externo="9", url="u",
                                           titulo="Desenvolvedor Back-end Java Pleno", empresa="ACME")) is None
    return processar_pendentes(cfg)


def test_pipeline_heuristica(cfg):
    contagem = _semear(cfg)
    assert contagem == {Status.COMPATIVEL: 1, Status.DESCARTADA_FILTRO: 1}
    with sessao(cfg.db) as s:
        v = s.get(Vaga, 1)
        assert v.nota >= 8 and v.contrato == "clt"


def test_fluxo_api(cfg):
    _semear(cfg)
    cli = TestClient(criar_app(cfg, agendar=False))
    assert cli.get("/").status_code == 200
    r = cli.get("/api/resumo").json()
    assert r["perfil_exemplo"] and not r["ollama"]["ok"]
    pilha = cli.get("/api/vagas").json()
    assert [v["id"] for v in pilha] == [1]
    assert "Java" in pilha[0]["analise"]["atende_profissional"]

    assert cli.post("/api/vagas/1/decisao", json={"decisao": "confirmar"}).json()["status"] == "em_candidatura"
    assert cli.post("/api/vagas/1/desfazer").json()["status"] == "compativel"
    cli.post("/api/vagas/1/decisao", json={"decisao": "confirmar"})
    r = cli.patch("/api/vagas/1/candidatura", json={"texto_formal": "Olá", "skills_gupy": ["Java", "SQL", "Git"]})
    assert r.status_code == 200
    assert cli.patch("/api/vagas/1/candidatura", json={"skills_gupy": ["a", "b", "c", "d"]}).status_code == 400
    assert "/gupy" in cli.get("/api/vagas/1/para-claude").text
    v = cli.post("/api/vagas/1/enviada", json={"observacoes": "teste"}).json()
    assert v["status"] == "candidatada" and v["candidatura"]["enviada_em"]
    feitas = cli.get("/api/vagas?status=candidatada").json()
    assert feitas[0]["candidatura"]["canal"] == "gupy"
    assert cli.post("/api/vagas/1/decisao", json={"decisao": "recusar"}).status_code == 400


def test_vaga_manual_e_alerta(cfg):
    cli = TestClient(criar_app(cfg, agendar=False))
    r = cli.post("/api/vagas/manual", json={"url": "https://x/1", "titulo": "Desenvolvedor Back-end Java Júnior",
                                            "empresa": "B", "modelo": "remoto", "descricao": DESCRICAO_BOA})
    assert r.json()["status"] == "compativel"
    assert cli.post("/api/vagas/manual", json={"url": "https://x/1", "titulo": "t"}).status_code == 409
    with sessao(cfg.db) as s:
        v = salvar_vaga(s, VagaColetada(fonte="linkedin", id_externo="5", url="https://l/5",
                                        titulo="Desenvolvedor Full Stack Pleno", empresa="C", sem_descricao=True))
        assert v.status == Status.SEM_DESCRICAO
    r = cli.post(f"/api/vagas/{v.id}/descricao", json={"descricao": DESCRICAO_BOA})
    assert r.json()["status"] in ("compativel", "abaixo_da_nota")


def test_mcp(cfg, monkeypatch):
    _semear(cfg)
    from job_finder import mcp_server, servicos

    monkeypatch.setattr(mcp_server, "_cfg", cfg)
    with sessao(cfg.db) as s:
        servicos.decidir(s, 1, "confirmar")
    assert [v["id"] for v in mcp_server.listar_vagas_confirmadas()] == [1]
    assert "Java" in mcp_server.ler_vaga(1)["descricao"]
    assert mcp_server.ler_perfil()["perfil_de_exemplo"]
    mcp_server.salvar_textos(1, texto_formal="F", texto_leve="L", skills_gupy=["Java", "SQL", "Git"], mensagem_recrutador="Olá!")
    assert mcp_server.listar_vagas_confirmadas() == []
    try:
        mcp_server.salvar_textos(1, mensagem_recrutador="x" * 301)
        raise AssertionError("devia falhar")
    except ValueError:
        pass
    r = mcp_server.marcar_revisada(2, "manter", "ok")
    assert r["status"] == "descartada_filtro"
    nomes = [t.name for t in asyncio.run(mcp_server.mcp.list_tools())]
    assert "salvar_textos" in nomes
