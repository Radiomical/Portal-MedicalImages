"""Ephemeral PostgreSQL CI database, never a deployment configuration."""
from .settings_test import *  # noqa: F403
DATABASES = {"default": {"ENGINE": "django.db.backends.postgresql", "NAME": "portal_ci", "USER": "portal_ci", "PASSWORD": "ci-only", "HOST": "127.0.0.1", "PORT": "5432"}}
# Sync every synthetic test table together, so PostgreSQL can resolve users ->
# auth foreign keys. This is test-only, not a production migration strategy.
MIGRATION_MODULES = {name: None for name in ["admin", "auth", "contenttypes", "sessions", "authtoken", "blog", "users"]}
