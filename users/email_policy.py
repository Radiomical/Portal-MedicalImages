"""Explicit account-email policy: lowercase + surrounding-space trim.

Blank emails are not login identifiers. Legacy collisions fail closed until
resolved; never pick an arbitrary account. This does not change API disclosure.
"""
from django.contrib.auth.models import User
from django.db.models.functions import Lower, Trim


def normalized_users(email):
    normalized = email.strip().lower()
    return User.objects.annotate(normalized_email=Lower(Trim('email'))).filter(normalized_email=normalized) if normalized else User.objects.none()


def email_user(email):
    users = list(normalized_users(email)[:2])
    return users[0] if len(users) == 1 else None
