"""Distância entre municípios (coordenadas do IBGE) para o filtro de presencial/híbrido."""

from __future__ import annotations

import csv
import math
from functools import lru_cache
from pathlib import Path

from .texto import normalizar

_CSV = Path(__file__).parent / "dados" / "municipios.csv"

UFS = {
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG", "PA",
    "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO",
}


@lru_cache(maxsize=1)
def _municipios() -> dict[tuple[str, str], tuple[float, float]]:
    d: dict[tuple[str, str], tuple[float, float]] = {}
    with _CSV.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            d[(normalizar(r["nome"]), r["uf"])] = (float(r["lat"]), float(r["lon"]))
    return d


def coordenadas(cidade: str, uf: str = "") -> tuple[float, float] | None:
    nome = normalizar(cidade)
    if not nome:
        return None
    uf = (uf or "").upper().strip()
    if uf:
        return _municipios().get((nome, uf))
    achados = [v for (n, _), v in _municipios().items() if n == nome]
    return achados[0] if len(achados) == 1 else None


def distancia_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(h))


def separar_cidade_uf(texto: str) -> tuple[str, str]:
    """'Blumenau - SC', 'Blumenau/SC', 'Blumenau, Santa Catarina' -> ('Blumenau', 'SC')."""
    if not texto:
        return "", ""
    partes = [p.strip() for p in texto.replace("/", ",").replace(" - ", ",").split(",") if p.strip()]
    if len(partes) >= 2 and partes[1].upper() in UFS:
        return partes[0], partes[1].upper()
    return (partes[0] if partes else ""), ""


def avaliar_local(cidade: str, uf: str, base: tuple[str, str], raio_km: float, extras: list[str]) -> tuple[bool | None, float | None]:
    """(True/False, distância) se a cidade é conhecida; (None, None) se não dá para saber."""
    for extra in extras:
        c, u = separar_cidade_uf(extra)
        if normalizar(c) == normalizar(cidade) and (not u or not uf or u == uf.upper()):
            return True, None
    origem = coordenadas(*base)
    destino = coordenadas(cidade, uf)
    if not origem or not destino:
        return None, None
    d = distancia_km(origem, destino)
    return d <= raio_km, round(d, 1)
