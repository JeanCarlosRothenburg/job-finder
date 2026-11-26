import httpx

from job_finder.coletores.email_alertas import interpretar_email
from job_finder.coletores.github import interpretar_issue
from job_finder.coletores.gupy import ColetorGupy, extrair_descricao_pagina


def test_issue_github():
    issue = {
        "number": 123, "title": "[Blumenau/SC] Desenvolvedor Back-end Pleno @ Empresa X",
        "html_url": "https://github.com/backend-br/vagas/issues/123", "body": "Requisitos: Java",
        "labels": [{"name": "Pleno"}, {"name": "Híbrido"}, {"name": "CLT"}], "created_at": "2026-11-20T10:00:00Z",
    }
    v = interpretar_issue("backend-br/vagas", issue)
    assert (v.cidade, v.uf, v.modelo, v.senioridade, v.contrato) == ("Blumenau", "SC", "hibrido", "pleno", "clt")
    assert v.empresa == "Empresa X" and v.titulo == "Desenvolvedor Back-end Pleno"
    assert interpretar_issue("r", {**issue, "pull_request": {}}) is None


def test_gupy_com_endpoint_simulado():
    def responder(req: httpx.Request):
        if req.url.path == "/api/job-search/jobs":
            assert req.url.params["jobName"] == "desenvolvedor"
            return httpx.Response(200, json={"pagination": {"total": 1, "limit": 100, "offset": 0}, "data": [{
                "id": 9, "name": "Desenvolvedor Full Stack Júnior", "careerPageName": "Empresa Y>",
                "city": "Indaial", "state": "Santa Catarina", "workplaceType": "hybrid",
                "type": "vacancy_type_effective", "jobUrl": "https://y.gupy.io/jobs/9",
                "publishedDate": "2026-11-22T12:00:00.000Z", "description": "<p>Vaga</p>",
            }]})
        return httpx.Response(404)

    col = ColetorGupy(["desenvolvedor"], pausa=0, cliente=httpx.Client(transport=httpx.MockTransport(responder)))
    vagas = list(col.coletar())
    assert len(vagas) == 1
    v = vagas[0]
    assert (v.uf, v.modelo, v.contrato, v.empresa) == ("SC", "hibrido", "clt", "Empresa Y")
    assert col.endpoint == "https://portal.gupy.io/api/job-search/jobs"


def test_descricao_next_data():
    html = '<script id="__NEXT_DATA__" type="application/json">{"props":{"pageProps":{"job":{"description":"<p>Sobre</p>","prerequisites":"<ul><li>Java</li></ul>"}}}}</script>'
    assert "Java" in extrair_descricao_pagina(html)


def test_email_linkedin():
    html = """<table><tr><td><a href="https://www.linkedin.com/comm/jobs/view/4012345678/?trk=eml">Desenvolvedor Back-end Pleno</a>
    <p>Empresa Z · Blumenau, SC (Híbrido)</p></td></tr></table>"""
    vagas = interpretar_email(html, "linkedin")
    assert len(vagas) == 1
    v = vagas[0]
    assert v.id_externo == "4012345678" and v.sem_descricao and v.url.endswith("/4012345678/")
    assert v.uf == "SC" and v.modelo == "hibrido"


def test_descricao_enxuta_corta_beneficios():
    from job_finder.extracao import _descricao_enxuta

    texto = "Requisitos\n" + "- PHP e Vue.js\n" * 60 + "Nossos benefícios\nVale refeição\n"
    assert "benef" not in _descricao_enxuta(texto)
    assert len(_descricao_enxuta("x" * 9000)) == 3500
