import pytest

from job_finder.config import Config
from job_finder.perfil import PERFIL_EXEMPLO, carregar_perfil


@pytest.fixture
def perfil():
    return carregar_perfil(PERFIL_EXEMPLO)


@pytest.fixture
def cfg(tmp_path):
    return Config(db=str(tmp_path / "teste.db"), perfil=str(PERFIL_EXEMPLO), ollama_url="http://127.0.0.1:9", intervalo_horas=0)


DESCRICAO_BOA = """Estamos buscando uma pessoa Desenvolvedora Back-end Java para o nosso time.

Requisitos:
- Experiência com Java e Spring Boot
- Conhecimento em SQL e PostgreSQL
- Git e APIs REST
- Inglês técnico

Diferenciais:
- Docker
- React

Contratação CLT, trabalho remoto."""
