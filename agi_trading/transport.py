"""HTTPS JSON transport. Fixed hosts, no redirects, no automatic write retries."""
import json
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit

from .security import TradingError

HOSTS = {
    "api.bybit.com", "api-testnet.bybit.com", "api.bybit.tr", "api.bybit.kz",
    "api.bybitgeorgia.ge", "api.bybit.ae", "api.bybit.eu", "api.bybit.id",
    "api.manepa.jp", "api.spark-fintech.com", "api.bitget.com",
}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise TradingError("HTTP redirect refused; credentials were not forwarded")


class Transport:
    # Shared within one Python process, across all adapter instances.
    _lock = threading.Lock()
    _last_call = 0.0

    def request(self, method, url, headers=None, body=None):
        parsed = urlsplit(url)
        if (parsed.scheme != "https" or parsed.hostname not in HOSTS
                or parsed.username or parsed.password or parsed.port not in (None, 443)):
            raise TradingError("API host is not allowed")
        with self._lock:
            delay = 0.35 - (time.monotonic() - Transport._last_call)
            if delay > 0:
                time.sleep(delay)
            Transport._last_call = time.monotonic()
        req = urllib.request.Request(url, data=body, method=method,
                                     headers={"User-Agent": "AGI-Trading/0.1.0", **(headers or {})})
        try:
            with urllib.request.build_opener(NoRedirect).open(req, timeout=20) as response:
                raw = response.read(2_000_001)
        except urllib.error.HTTPError as exc:
            # No response bodies: upstream error pages sometimes echo request credentials.
            raise TradingError(f"HTTP {exc.code} from {parsed.hostname}; not retried") from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise TradingError(f"Network request failed at {parsed.hostname}; not retried") from None
        if len(raw) > 2_000_000:
            raise TradingError("API response exceeded size limit")
        try:
            result = json.loads(raw)
        except (ValueError, UnicodeError):
            raise TradingError("API returned invalid JSON") from None
        if not isinstance(result, dict):
            raise TradingError("API returned an unexpected envelope")
        return result
