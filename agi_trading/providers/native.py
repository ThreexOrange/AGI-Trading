import json
import os
import shutil
import subprocess
from pathlib import Path

from ..security import TradingError, redact


def executable(provider, binary):
    native = Path(__file__).parent / provider / ".runtime" / (binary + (".exe" if os.name == "nt" else ""))
    if native.is_file():
        return str(native)
    local = Path(__file__).parent / provider / "node_modules" / ".bin" / binary
    if local.is_file():
        return str(local)
    found = shutil.which(binary)
    if not found:
        raise TradingError(f"{binary} is not installed. Run: python -m agi_trading bootstrap {provider}")
    return found


def run(provider, binary, args, timeout=45):
    # Args are assembled by typed adapters; never execute output.next or shell strings.
    command = [executable(provider, binary), *args]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout,
                                shell=False)
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
