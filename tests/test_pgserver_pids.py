"""Pruning of dead PIDs in .handle_pids.json (without starting Postgres)."""

import json
import os

import psutil

from app.db.config import podar_pids


def _pid_inexistente() -> int:
    pid = 4_000_000
    while psutil.pid_exists(pid):
        pid += 1
    return pid


def test_poda_pid_muerto_y_conserva_el_vivo(tmp_path):
    fichero = tmp_path / ".handle_pids.json"
    fichero.write_text(json.dumps([os.getpid(), _pid_inexistente()]))
    assert podar_pids(tmp_path) == [os.getpid()]
    assert json.loads(fichero.read_text()) == [os.getpid()]


def test_sin_fichero_o_corrupto(tmp_path):
    assert podar_pids(tmp_path) == []
    (tmp_path / ".handle_pids.json").write_text("{no es json")
    assert podar_pids(tmp_path) == []
