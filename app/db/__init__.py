"""Database layer: configuration, connection and models."""

import asyncio
import sys

# async psycopg does not work with the ProactorEventLoop that Windows uses by default
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
