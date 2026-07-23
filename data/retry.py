"""
Small retry helper. 3 attempts with exponential backoff on connection
errors, timeouts, and 5xx. Used by every scraper.
"""
import time
import random
import requests


def fetch(url: str, headers=None, timeout: int = 10, attempts: int = 3, **kwargs):
    """GET with retry. Returns the Response on success, None on total failure.
    Never raises — scrapers wrap this and degrade gracefully.
    """
    last_exc = None
    for i in range(attempts):
        try:
            r = requests.get(url, headers=headers, timeout=timeout, **kwargs)
            if r.status_code == 200:
                return r
            if 500 <= r.status_code < 600 and i < attempts - 1:
                time.sleep(0.6 * (2 ** i) + random.random() * 0.2)
                continue
            # 4xx — give up immediately (e.g. 403 from NSE for a bad session)
            return r if r.status_code < 500 else None
        except (requests.RequestException, ConnectionError, TimeoutError) as e:
            last_exc = e
            if i < attempts - 1:
                time.sleep(0.6 * (2 ** i) + random.random() * 0.2)
                continue
            return None
    return None
