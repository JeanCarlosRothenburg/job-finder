"""Alertas de vaga do LinkedIn e do Indeed lidos pelo IMAP do Gmail (senha de app).

Os e-mails trazem título, empresa e link, mas não a descrição completa. Essas vagas entram com
status `sem_descricao`: você cola a descrição na aba Alertas (ou pede ao Claude pelo MCP) e o
pipeline segue normalmente. Nada é raspado do LinkedIn ou do Indeed.
"""

from __future__ import annotations

import email
import imaplib
import html as _html
import re
from datetime import datetime, timedelta
from email.header import decode_header, make_header
from typing import Iterable

from .base import VagaColetada

REMETENTES = {
    "linkedin": ["jobalerts-noreply@linkedin.com", "jobs-noreply@linkedin.com"],
    "indeed": ["alert@indeed.com", "noreply@indeed.com", "donotreply@jobalert.indeed.com"],
}

_LINK_LINKEDIN = re.compile(r'<a[^>]+href="(https://(?:www\.)?linkedin\.com/(?:comm/)?jobs/view/(\d+)[^"]*)"[^>]*>(.*?)</a>', re.S | re.I)
_LINK_INDEED = re.compile(r'<a[^>]+href="(https://[^"]*indeed\.com[^"]*?(?:jk=|vjk=)([0-9a-f]{16})[^"]*)"[^>]*>(.*?)</a>', re.S | re.I)


def _texto(fragmento: str) -> str:
    t = re.sub(r"<[^>]+>", " ", fragmento)
    return re.sub(r"\s+", " ", _html.unescape(t)).strip()


def _corpo_html(msg: email.message.Message) -> str:
    for parte in msg.walk():
        if parte.get_content_type() == "text/html":
            carga = parte.get_payload(decode=True) or b""
            return carga.decode(parte.get_content_charset() or "utf-8", errors="replace")
    return ""


def interpretar_email(html: str, fonte: str) -> list[VagaColetada]:
    padrao = _LINK_LINKEDIN if fonte == "linkedin" else _LINK_INDEED
    vagas: dict[str, VagaColetada] = {}
    for m in padrao.finditer(html):
        url, ident, ancora = m.group(1), m.group(2), _texto(m.group(3))
        if not ancora or len(ancora) < 4:
            continue
        # o texto depois do link costuma trazer "Empresa · Cidade, UF (Remoto)"
        depois = _texto(html[m.end(): m.end() + 600])[:200]
        if ident in vagas:
            continue
        url_limpa = f"https://www.linkedin.com/jobs/view/{ident}/" if fonte == "linkedin" else f"https://br.indeed.com/viewjob?jk={ident}"
        empresa, cidade, uf, modelo = _empresa_local(depois)
        vagas[ident] = VagaColetada(
            fonte=fonte, id_externo=ident, url=url_limpa, titulo=ancora[:200], empresa=empresa,
            cidade=cidade, uf=uf, modelo=modelo, sem_descricao=True,
        )
    return list(vagas.values())


def _empresa_local(trecho: str) -> tuple[str, str, str, str]:
    from ..localidade import UFS
    from ..texto import normalizar

    n = normalizar(trecho)
    modelo = "remoto" if "remoto" in n or "remote" in n else "hibrido" if "hibrido" in n else "presencial" if "presencial" in n else ""
    partes = [p.strip() for p in re.split(r"\s[·|•]\s|\s-\s", trecho) if p.strip()]
    empresa = partes[0][:120] if partes else ""
    cidade = uf = ""
    m = re.search(r"([A-ZÀ-Ú][\wÀ-ú' ]+),\s*([A-Z]{2})\b", trecho)
    if m and m.group(2) in UFS:
        cidade, uf = m.group(1).strip(), m.group(2)
    return empresa, cidade, uf, modelo


class ColetorEmail:
    nome = "email"

    def __init__(self, host: str, usuario: str, senha: str, pasta: str = "INBOX", dias: int = 3):
        self.host, self.usuario, self.senha, self.pasta, self.dias = host, usuario, senha, pasta, dias

    def coletar(self) -> Iterable[VagaColetada]:
        if not (self.usuario and self.senha):
            return []
        desde = (datetime.now() - timedelta(days=self.dias)).strftime("%d-%b-%Y")
        encontrados: list[VagaColetada] = []
        with imaplib.IMAP4_SSL(self.host) as imap:
            imap.login(self.usuario, self.senha)
            imap.select(self.pasta, readonly=True)  # só leitura: não marca e-mails como lidos
            for fonte, remetentes in REMETENTES.items():
                for rem in remetentes:
                    _, dados = imap.search(None, f'(FROM "{rem}" SINCE {desde})')
                    for num in (dados[0] or b"").split():
                        _, msgdata = imap.fetch(num, "(RFC822)")
                        msg = email.message_from_bytes(msgdata[0][1])
                        assunto = str(make_header(decode_header(msg.get("Subject", ""))))
                        for v in interpretar_email(_corpo_html(msg), fonte):
                            v.etiquetas = [f"alerta: {assunto[:80]}"]
                            encontrados.append(v)
        return encontrados
