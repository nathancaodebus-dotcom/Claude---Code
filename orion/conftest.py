"""Test-session-wide defaults, loaded by pytest before any test module.

core/config.py's module-level `config = Config()` singleton reads its
values from the environment once, at first import — and several test
modules (plus interfaces/web/app.py, which needs an importable module-level
FastAPI `app` object) end up constructing real Agent/Memory/Store instances
using that singleton. setdefault() so a real .env some contributor happens
to have locally still wins; this only fills in what's otherwise unset,
purely so the suite doesn't depend on ANTHROPIC_API_KEY being exported by
whoever runs pytest, and so importing interfaces/web/app.py during tests
never touches a real orion.db file on disk.
"""
import os

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
os.environ.setdefault("ORION_DB_PATH", ":memory:")
