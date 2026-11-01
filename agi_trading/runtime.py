import os
import hashlib
import json
import platform
import shutil
import subprocess
import urllib.request
import tempfile
from urllib.parse import urlsplit
from pathlib import Path

from .providers import CATALOG, exchange
from .providers.native import executable
from .security import TradingError, runtime_environment
from .verification import require_review


class ReleaseRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        allowed = {"github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com"}
        parsed = urlsplit(newurl)
        if parsed.scheme != "https" or parsed.hostname not in allowed or parsed.username or parsed.password:
            raise TradingError("Untrusted release download redirect")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def install_okx():
    require_review()
    folder = Path(__file__).parent / "providers" / "okx"
    manifest = json.loads((folder / "release.json").read_text())
    machine = platform.machine().lower()
    arch = {"amd64": "x86_64", "arm64": "aarch64", "armv7l": "armv7"}.get(machine, machine)
    targets = {"Linux": "unknown-linux-gnu", "Darwin": "apple-darwin", "Windows": "pc-windows-msvc.exe"}
    target = targets.get(platform.system())
    if not target:
        raise TradingError("Unsupported OKX binary platform")
    if arch == "armv7" and platform.system() == "Linux":
        target = "unknown-linux-gnueabihf"
    name = f"onchainos-{arch}-{target}"
    asset = next((a for a in manifest["assets"] if a["name"] == name), None)
    if not asset:
        raise TradingError("Unsupported OKX binary architecture")
    url = asset["url"]
    if not url.startswith("https://github.com/okx/onchainos-skills/releases/download/" + manifest["version"] + "/"):
        raise TradingError("Invalid official release URL")
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "AGI-Trading/0.1.0"})
        with urllib.request.build_opener(ReleaseRedirect).open(request, timeout=45) as response:
            data = response.read(50_000_001)
    except (OSError, ValueError):
        raise TradingError("Official OKX binary download failed; check access to GitHub releases") from None
    if len(data) > 50_000_000 or hashlib.sha256(data).hexdigest() != asset["sha256"]:
        raise TradingError("Official OKX binary checksum mismatch; refusing installation")
    runtime = folder / ".runtime"
    runtime.mkdir(exist_ok=True, mode=0o700)
    binary = runtime / ("onchainos.exe" if platform.system() == "Windows" else "onchainos")
    with tempfile.NamedTemporaryFile(dir=runtime, delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(data)
    try:
        temporary.chmod(0o700)
        temporary.replace(binary)
    finally:
        temporary.unlink(missing_ok=True)
    return {"provider": "okx", "cli_installed": True, "version": manifest["version"],
            "sha256_verified": True, "next": "Installed runtime changed: collect audit evidence and review again before wallet access",
            "note": "Official binary only; no skills, workflows, A2A or credentials installed"}


def doctor():
    result = {"python": platform.python_version(), "node_available": bool(shutil.which("node")),
              "npm_available": bool(shutil.which("npm")), "live_enabled": os.environ.get("AGI_TRADING_ENABLE_LIVE") == "1",
              "secret_persistence": "external secret injection required; this project is not a credential vault",
              "providers": {}}
    for name, item in CATALOG.items():
        entry = {"backend": item["backend"]}
        if item["binary"]:
            try:
                executable(name, item["binary"])
                entry["cli_installed"] = True
            except TradingError:
                entry["cli_installed"] = False
            entry["auth"] = "Use login/verify; session validity must be checked after environment recovery"
        else:
            entry["credentials"] = {}
            for network in ("testnet", "live"):
                adapter = exchange(name, network)
                entry["credentials"][network] = {k: bool(os.environ.get(k)) for k in adapter.credential_names}
        result["providers"][name] = entry
    return result


def bootstrap(provider):
    require_review()
    if provider == "okx":
        return install_okx()
    if provider == "bybit":
        return {"provider": provider, "installed": True, "note": "Built-in stdlib REST adapter; no extra dependency required"}
    npm = shutil.which("npm")
    if not npm:
        raise TradingError("Install Node.js >=20 and npm, then retry")
    folder = Path(__file__).parent / "providers" / provider
    command = [npm, "ci", "--ignore-scripts", "--no-audit", "--no-fund", "--prefix", str(folder)]
    # stdout is reserved for machine-readable JSON. Avoid relaying npm diagnostics.
    try:
        process = subprocess.run(command, capture_output=True, text=True, timeout=240, shell=False,
                                 env=runtime_environment("npm"))
    except subprocess.TimeoutExpired:
        raise TradingError("Dependency installation timed out; retry bootstrap") from None
    if process.returncode:
        raise TradingError("npm ci failed; check registry connectivity. Package output withheld to protect credentials")
    result = {"provider": provider, "dependencies_installed": True, "lifecycle_scripts_disabled": True,
              "next": "Collect audit evidence and review the installed dependencies before account access"}
    return result
