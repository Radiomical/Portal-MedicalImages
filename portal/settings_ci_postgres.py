"""Ephemeral PostgreSQL CI database, never a deployment configuration."""
from .settings_test import *  # noqa: F403
DATABASES = {"default": {"ENGINE": "django.db.backends.postgresql", "NAME": "portal_ci", "USER": "portal_ci", "PASSWORD": "ci-only", "HOST": "127.0.0.1", "PORT": "5432"}}
