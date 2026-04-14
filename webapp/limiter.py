"""
Shared rate-limiter instance.
Import this in main.py (to attach to the app) and in route modules (for decorators).
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
