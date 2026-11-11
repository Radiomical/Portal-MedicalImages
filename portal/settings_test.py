"""Synthetic, network-free test configuration."""
import os
os.environ["SECRET_KEY"] = "synthetic-test-only-value-not-for-deployment-0123456789"
os.environ["DB_ENGINE"] = "sqlite"
os.environ["SQLITE_PATH"] = ":memory:"
os.environ["SECURE_COOKIES"] = "false"
os.environ["SECURE_SSL_REDIRECT"] = "false"
os.environ["EMAIL_BACKEND"] = "django.core.mail.backends.locmem.EmailBackend"
from .settings import *  # noqa: F403,E402
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
ALLOWED_HOSTS = ["testserver", "localhost"]
