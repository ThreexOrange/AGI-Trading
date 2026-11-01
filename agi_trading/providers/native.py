import json
import os
import subprocess
from pathlib import Path

from ..security import TradingError, redact, runtime_environment
from ..verification import require_review


def executable(provider, binary):
    native = Path(__file__).parent / provider / ".runtime" / (binary + (".exe" if os.name == "nt" else ""))
    if native.is_file():
        return str(native)
    local = Path(__file__).parent / provider / "node_modules" / ".bin" / binary
    if local.is_file():
        return str(local)
    # PATH binaries are not in the reviewed runtime fingerprint.
    raise TradingError(f"Reviewed local {binary} runtime is not installed. Run: python -m agi_trading bootstrap {provider}")


def run(provider, binary, args, timeout=45):
    require_review()
    # Args are assembled by typed adapters; never execute output.next or shell strings.
    command = [executable(provider, binary), *args]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout,
                                shell=False, env=runtime_environment(provider))
    except subprocess.TimeoutExpired:
        raise TradingError("Official CLI timed out; authentication may require a fresh login") from None
    try:
        data = json.loads(result.stdout)
    except ValueError:
        # Do not relay arbitrary native diagnostics, which may contain credentials.
        raise TradingError(f"{binary} returned non-JSON output (exit {result.returncode}); output withheld") from None
    if result.returncode != 0 or (isinstance(data, dict) and (data.get("success") is False or data.get("ok") is False)):
        raise TradingError(json.dumps(redact(data), ensure_ascii=False))
    return redact(data)
