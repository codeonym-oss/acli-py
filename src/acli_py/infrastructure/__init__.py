"""Infrastructure: everything that talks to the outside world.

The Jira REST client and what builds its payloads (`jira/`), settings and accounts
(`config.py`), API tokens (`credentials.py`) and the files the front ends keep (`storage.py`).
Only the composition root (`acli_py.bootstrap`) hands these to the other layers.
"""
