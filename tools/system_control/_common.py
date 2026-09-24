"""Helpers compartidos de los mixins de SystemControl."""

import functools
import time

from core.logger import log_info


def _timed(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        t0 = time.time()
        try:
            return fn(*args, **kwargs)
        finally:
            log_info(f"[TIMING] {fn.__qualname__} tardó {time.time() - t0:.1f}s")
    return wrapper

