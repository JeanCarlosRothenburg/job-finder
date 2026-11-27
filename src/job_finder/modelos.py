"""Tabelas do SQLite. A vaga tem um único status que anda numa máquina de estados."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Optional

from sqlalchemy import Column, JSON, UniqueConstraint
from sqlmodel import Field, SQLModel


def agora() -> datetime:
    return datetime.now(timezone.utc)


class Status(StrEnum):
    COLETADA = "coletada"
    SEM_DESCRICAO = "sem_descricao"  # alertas de e-mail: falta colar a descrição
    DESCARTADA_FILTRO = "descartada_filtro"
    ABAIXO_DA_NOTA = "abaixo_da_nota"
    COMPATIVEL = "compativel"
    RECUSADA = "recusada"
    EM_CANDIDATURA = "em_candidatura"
    CANDIDATADA = "candidatada"


class Vaga(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("fonte", "id_externo"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    fonte: str = Field(index=True)
    id_externo: str
    url: str
    titulo: str
    empresa: str = ""
    cidade: str = ""
    uf: str = ""
    modelo: str = ""  # presencial | hibrido | remoto | "" (não informado)
    senioridade: str = ""
    idioma_exigido: str = ""
    contrato: str = ""
    salario: str = ""
    descricao: str = ""
    hash_descricao: str = Field(default="", index=True)
    chave_dedup: str = Field(default="", index=True)
    recrutador_nome: str = ""
    recrutador_url: str = ""
    etiquetas: list = Field(default_factory=list, sa_column=Column(JSON))
    publicada_em: Optional[datetime] = None
    coletada_em: datetime = Field(default_factory=agora)
    status: str = Field(default=Status.COLETADA, index=True)
    motivo_descarte: str = ""
    nota: Optional[float] = Field(default=None, index=True)
    revisada_claude: bool = False
    observacao_claude: str = ""
    processada_em: Optional[datetime] = None  # quando o filtro/nota decidiu o status
    ciclo_id: Optional[int] = Field(default=None, index=True)


class Ciclo(SQLModel, table=True):
    """Uma rodada de processamento: agendada, manual (botão/CLI), vaga avulsa ou recálculo."""

    id: Optional[int] = Field(default=None, primary_key=True)
    origem: str  # agendado | manual | vaga_avulsa | recalculo
    iniciado_em: datetime = Field(default_factory=agora)
    terminado_em: Optional[datetime] = None
    vagas_processadas: int = 0


class Analise(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    vaga_id: int = Field(foreign_key="vaga.id", index=True)
    modelo_llm: str
    versao_prompt: str
    extracao_json: dict = Field(default_factory=dict, sa_column=Column(JSON))
    nota: float
    detalhe_nota_json: dict = Field(default_factory=dict, sa_column=Column(JSON))
    criada_em: datetime = Field(default_factory=agora)


class Candidatura(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    vaga_id: int = Field(foreign_key="vaga.id", index=True, unique=True)
    decisao: str  # confirmada | recusada
    canal: str = ""  # gupy | email | ats | linkedin | indeed | manual
    texto_formal: str = ""
    texto_leve: str = ""
    skills_gupy: list = Field(default_factory=list, sa_column=Column(JSON))
    mensagem_recrutador: str = ""
    texto_preferencial: str = ""
    observacoes: str = ""
    decidida_em: datetime = Field(default_factory=agora)
    enviada_em: Optional[datetime] = None


class FonteExecucao(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    fonte: str
    iniciada_em: datetime = Field(default_factory=agora)
    terminada_em: Optional[datetime] = None
    vagas_novas: int = 0
    erros: str = ""
