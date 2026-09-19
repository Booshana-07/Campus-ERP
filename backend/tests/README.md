# Phase 3A + 3B test harnesses

Three standalone suites. All run with **plain `python3` and no installed
dependencies** — `shim.py` supplies the small slice of FastAPI / Pydantic /
SQLAlchemy that the code under test touches, so you can run them without
starting a server or touching your real database.

```bash
cd backend
python3 tests/test_migration.py   # migration is additive, idempotent, non-destructive
python3 tests/test_auth.py        # 41 Phase 3A signup / login / status / token / role cases
python3 tests/test_phase3b.py     # 49 Phase 3B approval / permission / emergency / audit cases
```

They import the **real** `app/security.py`, `app/deps.py`, `app/audit.py`,
`app/pdf_export.py`, `app/migrate.py` and the routers — nothing under test is
reimplemented here.

`test_migration.py` builds a throwaway SQLite file (`_phase2_sim.db`) shaped
like a Phase 2 install, migrates it, and asserts every row survives unchanged.
It never touches `campus_emergency.db`.
