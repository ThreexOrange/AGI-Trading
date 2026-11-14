import json
import os
import shutil
import subprocess
from pathlib import Path

from ..security import TradingError, redact, runtime_environment
from ..verification import require_review


def executable(provider, binary):
    directory = Path(__file__).parent / provider
    native = directory / ".runtime" / (binary + (".exe" if os.name == "nt" else ""))
    if native.is_file():
        return str(native)
    if os.name == "nt" and provider == "binance" and binary == "baw":
        local = directory / "node_modules/@binance/agentic-wallet/dist/index.js"
    else:
        local = directory / "node_modules/.bin" / binary
    if local.is_file():
        return str(local)
    # PATH binaries are not in the reviewed runtime fingerprint.
    raise TradingError(f"Reviewed local {binary} runtime is not installed. Run: python -m agi_trading bootstrap {provider}")


def run(provider, binary, args, timeout=45, *, json_lines=False):
    require_review()
    # Args are assembled by typed adapters; never execute output.next or shell strings.
    command = [executable(provider, binary), *args]
    if os.name == "nt" and command[0].endswith(".js"):
        node = shutil.which("node.exe")
        if not node:
            raise TradingError("Install Node.js >=20 to run the Binance CLI")
        command.insert(0, node)
    try:
        result = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                                encoding="utf-8", timeout=timeout, shell=False, env=runtime_environment(provider))
    except subprocess.TimeoutExpired:
        raise TradingError("Official CLI timed out; authentication may require a fresh login") from None
    try:
        if json_lines:
            lines = [line for line in result.stdout.splitlines() if line.strip()]
            try:
                data = json.loads(result.stdout)
            except ValueError:
                data = []
                for index, line in enumerate(lines):
                    try:
                        data.append(json.loads(line))
                    except ValueError:
                        # baw may print a multiline error after earlier events.
                        data = json.loads("\n".join(lines[index:]))
                        break
            if isinstance(data, dict) and "stream" in data:
                data = [data]
        else:
            data = json.loads(result.stdout)
    except ValueError:
        # Do not relay arbitrary native diagnostics, which may contain credentials.
        raise TradingError(f"{binary} returned non-JSON output (exit {result.returncode}); output withheld") from None
    if result.returncode != 0 or (isinstance(data, dict) and (data.get("success") is False or data.get("ok") is False)):
        raise TradingError(json.dumps(redact(data), ensure_ascii=False))
    if json_lines:
        if not isinstance(data, list) or any(not isinstance(event, dict) or "stream" not in event
                                             or "data" not in event for event in data):
            raise TradingError("Unexpected wallet tracker event")
        data = {"success": True, "data": data}
    return redact(data)
