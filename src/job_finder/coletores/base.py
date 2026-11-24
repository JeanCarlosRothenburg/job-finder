"""Interface comum dos coletores de vagas."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable, Protocol

USER_AGENT = "job-finder/0.1 (uso pessoal; poucas consultas por dia)"


@dataclass
class VagaColetada:
    fonte: str
    id_externo: str
    url: str
    titulo: str
    empresa: str = ""
    cidade: str = ""
    uf: str = ""
    modelo: str = ""  # presencial | hibrido | remoto | ""
    descricao: str = ""
    senioridade: str = ""
    contrato: str = ""
    salario: str = ""
    etiquetas: list[str] = field(default_factory=list)
    publicada_em: datetime | None = None
    recrutador_nome: str = ""
    recrutador_url: str = ""
    sem_descricao: bool = False


class Coletor(Protocol):
    nome: str

    def coletar(self) -> Iterable[VagaColetada]: ...


def parse_data(valor: str | None) -> datetime | None:
    if not valor:
        return None
    try:
        d = datetime.fromisoformat(valor.replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:
        return None
