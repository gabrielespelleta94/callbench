"""Helper for the chaos test: a real worker process that takes a job and hangs.

    python tests/worker_que_muere.py <database url> <worker name> <lease seconds>

It prints TOMADO once the job is claimed and keeps renewing the lease until the test
kills it (no cleanup runs, like a crashed or unplugged machine).
"""

import sys
import time

from bench import cola, worker


def colgado(trabajo):
    print("TOMADO", trabajo.id, flush=True)
    time.sleep(3600)
    return []


if __name__ == "__main__":
    url, nombre, lease = sys.argv[1], sys.argv[2], float(sys.argv[3])
    worker.procesar_uno(cola.motor(url), nombre, colgado, lease_s=lease)
