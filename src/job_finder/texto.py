"""Normalização de texto usada em filtros, deduplicação e casamento de skills."""

from __future__ import annotations

import hashlib
import re
import unicodedata


def sem_acentos(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def normalizar(s: str) -> str:
    """Minúsculas, sem acentos, só letras, dígitos e os símbolos de stacks (+ # .)."""
    s = sem_acentos(s or "").lower()
    s = re.sub(r"[^a-z0-9+#.]+", " ", s)
    return re.sub(r"\s+", " ", s).strip(" .")


def contem_termo(texto_norm: str, termo: str) -> bool:
    """Procura o termo como palavra inteira no texto já normalizado."""
    t = normalizar(termo)
    if not t:
        return False
    # "." só separa palavras no fim de frase: "js" não casa dentro de "node.js"
    return re.search(rf"(?<![a-z0-9+#.]){re.escape(t)}(?![a-z0-9+#]|\.[a-z0-9])", texto_norm) is not None


def hash_texto(s: str) -> str:
    return hashlib.sha1(normalizar(s).encode()).hexdigest()[:16] if s else ""


def chave_dedup(empresa: str, titulo: str) -> str:
    return hashlib.sha1(f"{normalizar(empresa)}|{normalizar(titulo)}".encode()).hexdigest()[:16]


def limpar_html(html: str) -> str:
    """Converte HTML simples em texto, preservando quebras de linha."""
    if not html:
        return ""
    s = re.sub(r"(?is)<(script|style).*?</\1>", " ", html)
    s = re.sub(r"(?i)<br\s*/?>|</p>|</li>|</h\d>|</div>", "\n", s)
    s = re.sub(r"(?i)<li[^>]*>", "\n- ", s)
    s = re.sub(r"<[^>]+>", " ", s)
    import html as _h

    s = _h.unescape(s)
    s = re.sub(r"[ \t\r\f\v]+", " ", s)
    s = re.sub(r"\n\s*\n+", "\n\n", s)
    return s.strip()
