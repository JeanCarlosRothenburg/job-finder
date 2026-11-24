from types import SimpleNamespace

from job_finder.filtros import anos_exigidos, pos_filtro, pre_filtro, senioridade_do_texto
from job_finder.localidade import avaliar_local, coordenadas
from job_finder.nota import calcular_nota

from .conftest import DESCRICAO_BOA


def vaga(**kw):
    base = dict(titulo="Desenvolvedor Back-end Java Pleno", empresa="ACME", cidade="", uf="", modelo="remoto",
                senioridade="", descricao=DESCRICAO_BOA, etiquetas=[], contrato="")
    base.update(kw)
    return SimpleNamespace(**base)


def test_senioridade_e_anos():
    assert senioridade_do_texto("Desenvolvedor Jr") == "junior"
    assert senioridade_do_texto("Dev Back-end Sênior") == "senior"
    assert senioridade_do_texto("Engenheiro de Software") == ""
    assert anos_exigidos("Mínimo de 5 anos de experiência com Java") == 5
    assert anos_exigidos("sem experiência") is None


def test_pre_filtro_titulo_e_senioridade(perfil):
    assert pre_filtro(vaga(), perfil).aprovada
    assert not pre_filtro(vaga(titulo="Desenvolvedor Java Sênior"), perfil).aprovada
    assert not pre_filtro(vaga(titulo="Analista de QA"), perfil).aprovada
    assert not pre_filtro(vaga(titulo="Estágio em Desenvolvimento"), perfil).aprovada
    r = pre_filtro(vaga(titulo="Desenvolvedor Full Stack"), perfil)
    assert r.aprovada and "senioridade não informada" in r.avisos


def test_pre_filtro_localidade(perfil):
    assert pre_filtro(vaga(modelo="hibrido", cidade="Blumenau", uf="SC"), perfil).aprovada
    assert pre_filtro(vaga(modelo="presencial", cidade="Rio do Sul", uf="SC"), perfil).aprovada
    r = pre_filtro(vaga(modelo="presencial", cidade="São Paulo", uf="SP"), perfil)
    assert not r.aprovada and "km" in r.motivo
    assert pre_filtro(vaga(modelo="remoto", cidade="São Paulo", uf="SP"), perfil).aprovada


def test_pre_filtro_ingles(perfil):
    assert not pre_filtro(vaga(descricao=DESCRICAO_BOA + "\nInglês fluente."), perfil).aprovada
    texto_en = "We are looking for a developer to join our team and work with the best. " * 6
    assert not pre_filtro(vaga(descricao=texto_en), perfil).aprovada


def test_distancias():
    assert coordenadas("Presidente Getúlio", "SC")
    ok, d = avaliar_local("Ibirama", "SC", ("Presidente Getúlio", "SC"), 70, [])
    assert ok and d < 30
    ok, d = avaliar_local("Florianópolis", "SC", ("Presidente Getúlio", "SC"), 70, [])
    assert ok is False and d > 100
    ok, _ = avaliar_local("Florianópolis", "SC", ("Presidente Getúlio", "SC"), 70, ["Florianópolis/SC"])
    assert ok


def test_nota_completa(perfil):
    reqs = [
        {"nome": "Java", "tipo": "obrigatorio", "peso": 3},
        {"nome": "PostgreSQL", "tipo": "obrigatorio", "peso": 2},
        {"nome": "Git", "tipo": "obrigatorio", "peso": 1},
        {"nome": "Docker", "tipo": "diferencial", "peso": 1},
    ]
    nota, det = calcular_nota(reqs, perfil)
    # O = 1,0; D = 0,5 -> 10 × (0,8 + 0,1) = 9,0
    assert nota == 9.0
    assert "Java" in det["atende_profissional"] and "Docker (diferencial)" in det["atende_conhecimento"]


def test_nota_trava_obrigatorio_central(perfil):
    reqs = [{"nome": "Golang", "tipo": "obrigatorio", "peso": 3}] + [
        {"nome": n, "tipo": "obrigatorio", "peso": 3} for n in ("Java", "SQL", "Git", "JavaScript", "APIs REST")
    ]
    nota, det = calcular_nota(reqs, perfil)
    assert det["travada"] and nota == 7.0


def test_nota_ingles_e_formacao(perfil):
    nota, det = calcular_nota([{"nome": "Inglês técnico", "tipo": "obrigatorio", "peso": 1},
                               {"nome": "Graduação em Ciência da Computação", "tipo": "obrigatorio", "peso": 1}], perfil)
    assert nota == 10.0
    nota, _ = calcular_nota([{"nome": "Inglês avançado", "tipo": "obrigatorio", "peso": 1}], perfil)
    assert nota == 0.0


def test_pos_filtro(perfil):
    ext = {"cargo_area": "backend", "senioridade": "pleno", "anos_experiencia_min": 2, "modelo_trabalho": "remoto",
           "ingles": "tecnico", "vaga_em_ingles": False, "fuso_exterior": False, "contrato": "clt"}
    assert pos_filtro(vaga(), ext, perfil).aprovada
    assert not pos_filtro(vaga(), {**ext, "senioridade": "senior"}, perfil).aprovada
    assert not pos_filtro(vaga(), {**ext, "fuso_exterior": True}, perfil).aprovada
    assert not pos_filtro(vaga(), {**ext, "cargo_area": "outro"}, perfil).aprovada
    assert not pos_filtro(vaga(modelo=""), {**ext, "modelo_trabalho": "presencial", "cidade": "Curitiba", "uf": "PR"}, perfil).aprovada
