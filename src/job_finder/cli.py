"""Linha de comando: job-finder serve | coletar | processar | recalcular | mcp | testar-ollama."""

from __future__ import annotations

import argparse
import json
import logging


def main(argv: list[str] | None = None) -> None:
    from .config import obter_config

    p = argparse.ArgumentParser(prog="job-finder", description="Busca e pontua vagas; candidatura semiautomática.")
    sub = p.add_subparsers(dest="cmd", required=True)
    sv = sub.add_parser("serve", help="sobe a interface web, a API e o agendador")
    sv.add_argument("--host", default="127.0.0.1")
    sv.add_argument("--port", type=int, default=8000)
    sv.add_argument("--sem-agendador", action="store_true")
    co = sub.add_parser("coletar", help="coleta vagas agora (sem analisar)")
    co.add_argument("--fonte", action="append", help="gupy, github ou email (pode repetir)")
    sub.add_parser("processar", help="filtra, extrai requisitos e calcula a nota das vagas coletadas")
    sub.add_parser("ciclo", help="coleta e processa (o mesmo que o agendador faz)")
    sub.add_parser("recalcular", help="recalcula filtros e notas depois de editar o perfil.yaml")
    sub.add_parser("mcp", help="servidor MCP (stdio) para o Claude")
    sub.add_parser("testar-ollama", help="verifica se o Ollama e o modelo estão prontos")
    sub.add_parser("testar-fontes", help="consulta cada fonte sem gravar nada e mostra o resultado")
    a = p.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    cfg = obter_config()

    if a.cmd == "serve":
        import uvicorn

        from .api import criar_app

        uvicorn.run(criar_app(cfg, agendar=not a.sem_agendador), host=a.host, port=a.port)
    elif a.cmd == "mcp":
        logging.getLogger().handlers.clear()  # stdout é do protocolo MCP
        from .mcp_server import main as mcp_main

        mcp_main()
    elif a.cmd == "testar-ollama":
        from .extracao import ollama_disponivel

        ok, msg = ollama_disponivel(cfg.ollama_url, cfg.ollama_modelo)
        print(("OK: " if ok else "PROBLEMA: ") + msg)
        raise SystemExit(0 if ok else 1)
    elif a.cmd == "testar-fontes":
        from itertools import islice

        from .coletores import coletores_ativos
        from .perfil import carregar_perfil

        for col in coletores_ativos(cfg, carregar_perfil(cfg.perfil)):
            try:
                amostra = list(islice(col.coletar(), 5))
                extra = f" (endpoint: {col.endpoint})" if getattr(col, "endpoint", None) else ""
                print(f"[ok] {col.nome}: {len(amostra)} vagas na amostra{extra}")
                for v in amostra:
                    print(f"     - {v.titulo} | {v.empresa} | {v.modelo or '?'} {v.cidade}/{v.uf}")
            except Exception as e:  # noqa: BLE001
                print(f"[erro] {col.nome}: {e}")
    else:
        from . import pipeline
        from .perfil import carregar_perfil

        perfil = carregar_perfil(cfg.perfil)
        if perfil.exemplo:
            print("Aviso: usando perfil.exemplo.yaml; crie o perfil.yaml a partir do seu currículo.")
        if a.cmd == "coletar":
            r = pipeline.coletar(cfg, perfil, a.fonte)
        elif a.cmd == "processar":
            r = pipeline.processar_pendentes(cfg, perfil)
        elif a.cmd == "ciclo":
            r = pipeline.ciclo(cfg)
        else:
            r = {"vagas_recalculadas": pipeline.recalcular_notas(cfg, perfil)}
        print(json.dumps(r, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
