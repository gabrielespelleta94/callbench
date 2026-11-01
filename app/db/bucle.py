"""Event loop compatible with async psycopg on Windows.

Uvicorn, without --reload, uses ProactorEventLoop and psycopg does not support it.
Point it at this one with:  uvicorn app.main:app --loop app.db.bucle:selector_loop
"""

import asyncio


def selector_loop() -> asyncio.AbstractEventLoop:
    return asyncio.SelectorEventLoop()
