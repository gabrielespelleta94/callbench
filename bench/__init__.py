"""CallBench job queue: rounds of scenario runs stored in Postgres and run by workers.

- `bench.encolar`: create a round (version x scenarios x attempts) and queue its jobs.
- `bench.worker`: take jobs with `FOR UPDATE SKIP LOCKED` + a lease, run each scenario
  against a fresh bot and store the result; retry only infrastructure failures.
- `bench.cola`: the queue operations themselves (SQL), shared by both and by the tests.
"""
