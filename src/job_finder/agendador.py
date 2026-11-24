"""Agendador (APScheduler) que roda coleta + análise dentro do processo do backend."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler

from .config import Config
from .pipeline import ciclo

log = logging.getLogger(__name__)


def iniciar_agendador(cfg: Config) -> BackgroundScheduler | None:
    if cfg.intervalo_horas <= 0:
        log.info("agendador desligado (JOBFINDER_INTERVALO_HORAS=0)")
        return None
    sched = BackgroundScheduler(timezone="America/Sao_Paulo")
    sched.add_job(
        lambda: log.info("ciclo: %s", ciclo(cfg)),
        "interval",
        hours=cfg.intervalo_horas,
        id="ciclo",
        next_run_time=datetime.now() + timedelta(minutes=1),
        max_instances=1,
        coalesce=True,
    )
    sched.start()
    log.info("agendador ligado: coleta a cada %s h", cfg.intervalo_horas)
    return sched
