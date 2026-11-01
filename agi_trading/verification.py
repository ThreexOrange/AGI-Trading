"""Local review gate and content-addressed evidence, never a safety certificate.

Inspect this module independently before running it. An application cannot
authenticate itself or constrain a hostile local operator.
"""
import ast
import hashlib
import json
import os
import stat
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.parse import urlencode

from .security import TradingError, runtime_environment

ROOT = Path(__file__).resolve().parent.parent
SKIP = {".git", "node_modules", ".runtime", "__pycache__", ".venv", "build", "dist", ".pytest_cache"}
CHECKS = ("data_flow", "credentials", "execution_controls", "dependencies", "tests_and_limits")
TTL = 7 * 24 * 60 * 60
MAX_JSON = 1_000_000


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def _files(root, runtime=False):
    entries = []
    for directory, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if runtime or (d not in SKIP and not d.endswith(".egg-info")))
        for name in dirs:
            path = Path(directory) / name
            if path.is_symlink():
                raise TradingError("Directory symlinks are outside this review model")
        for name in sorted(files):
            path = Path(directory) / name
            if not runtime and (name.startswith(".env") and name != ".env.example" or name.endswith((".pyc", ".log", ".sqlite", ".sqlite3", ".db", ".pem", ".key"))):
                continue
            relative = path.relative_to(root).as_posix()
            if path.is_symlink():
                target = path.resolve()
                if root.resolve() not in target.parents or not target.is_file():
                    raise TradingError("External runtime/file symlink refused during evidence collection")
                entries.append({"path": relative, "symlink": os.readlink(path),
                                "sha256": hashlib.sha256(target.read_bytes()).hexdigest()})
            elif path.is_file():
                h = hashlib.sha256()
                with path.open("rb") as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        h.update(chunk)
                entries.append({"path": relative, "sha256": h.hexdigest()})
    return entries


def snapshot(root=None):
    root = Path(root or ROOT).resolve()
    if not (root / ".git").exists() or not (root / "agi_trading").is_dir():
        raise TradingError("Review-gated operations require a source checkout; clone the repository first")
    # This includes untracked/ignored source files, unlike git ls-files alone.
    source = _files(root)
    runtime = []
    for provider in ("binance", "okx", "bitget", "bybit"):
        for folder in ("node_modules", ".runtime"):
            location = root / "agi_trading/providers" / provider / folder
            if location.is_symlink():
                raise TradingError("Runtime root must not be a symlink")
            if location.is_dir():
                runtime.append({"provider": provider, "folder": folder, "files": _files(location, True)})
    result = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True,
                            text=True, timeout=10, env=runtime_environment("git"), shell=False)
    if result.returncode:
        raise TradingError("Cannot identify checkout commit")
    return {"commit": result.stdout.strip(), "source_sha256": digest(source),
            "runtime_sha256": digest(runtime), "files": source,
            "runtime_file_count": sum(len(r["files"]) for r in runtime)}


def audit(root=None):
    root = Path(root or ROOT)
    current = snapshot(root)
    findings = []
    for entry in current["files"]:
        name = entry["path"]
        if not name.startswith("agi_trading/") or not name.endswith(".py"):
            continue
        try:
            tree = ast.parse((root / name).read_text())
        except (SyntaxError, UnicodeError):
            findings.append({"severity": "high", "file": name, "issue": "Python syntax could not be inspected"})
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id in {"eval", "exec"}:
                    findings.append({"severity": "high", "file": name, "line": node.lineno, "issue": "Dynamic execution requires review"})
                if any(k.arg == "shell" and isinstance(k.value, ast.Constant) and k.value.value is True for k in node.keywords):
                    findings.append({"severity": "high", "file": name, "line": node.lineno, "issue": "shell=True requires review"})
    return {"kind": "local-review-evidence/v1", "snapshot": current,
            "automated_findings": findings, "review_required": True,
            "limits": ["Pattern checks are narrow and do not establish safety",
                       "No dependency vulnerability service or independent auditor was queried",
                       "Runtime hashes identify files, not their trustworthiness",
                       "No credentials read, exchange contacted, transaction submitted or review published"],
            "next": "Independently inspect code/dependencies, run offline tests, fill review-template, then review-import"}


def template():
    current = snapshot()
    return {"schema": 1, "commit": current["commit"], "source_sha256": current["source_sha256"],
            "runtime_sha256": current["runtime_sha256"], "reviewer": "REPLACE_WITH_REVIEWER_AND_TOOL",
            "reviewer_relationship": "user_agent", "reviewed_at": int(time.time()),
            "recommendation": "needs_changes", "score": None,
            "checks": {name: {"result": "not_reviewed", "evidence": ""} for name in CHECKS},
            "findings": [], "improvements": ["REPLACE_WITH_CONCRETE_IMPROVEMENTS_OR_EXPLAIN_NONE"],
            "limitations": ["Reviewer identity is self-asserted, not authenticated", "No absolute safety guarantee"],
            "scope": "REPLACE_WITH_FILES_DEPENDENCIES_AND_TESTS_ACTUALLY_REVIEWED"}


def validate(report, current, approved=False, now=None):
    now = int(time.time() if now is None else now)
    if not isinstance(report, dict) or report.get("schema") != 1:
        raise TradingError("Unsupported review report schema")
    for field in ("commit", "source_sha256", "runtime_sha256"):
        if report.get(field) != current[field]:
            raise TradingError("Review is stale: commit, source or installed runtime changed; review again")
    reviewed = report.get("reviewed_at")
    if type(reviewed) is not int or reviewed > now + 60 or reviewed <= now - TTL:
        raise TradingError("Review date is invalid or older than seven days")
    for field in ("reviewer", "scope"):
        text = report.get(field)
        if not isinstance(text, str) or len(text.strip()) < 8 or "REPLACE_" in text:
            raise TradingError(f"Review requires an actual {field}")
    if report.get("reviewer_relationship") not in ("maintainer", "user_agent", "independent"):
        raise TradingError("Reviewer relationship must be disclosed")
    score = report.get("score")
    if type(score) not in (int, float) or not 0 <= score <= 10:
        raise TradingError("An honest numeric score from 0 to 10 is required; no minimum rating is imposed")
    if report.get("recommendation") not in ("approve", "needs_changes", "reject"):
        raise TradingError("Invalid review recommendation")
    checks = report.get("checks")
    if not isinstance(checks, dict) or set(checks) != set(CHECKS):
        raise TradingError("All review categories are required")
    for check in checks.values():
        if not isinstance(check, dict) or check.get("result") not in ("pass", "fail", "not_reviewed"):
            raise TradingError("Invalid review check")
        if not isinstance(check.get("evidence"), str) or len(check["evidence"].strip()) < 12:
            raise TradingError("Each category needs concrete evidence, including unreviewed categories")
    for field in ("findings", "improvements", "limitations"):
        if not isinstance(report.get(field), list):
            raise TradingError(f"Review requires a {field} list")
    if not report["limitations"] or not report["improvements"]:
        raise TradingError("State limitations and concrete improvements, or explain why none are proposed")
    for item in report["limitations"] + report["improvements"]:
        if not isinstance(item, str) or len(item.strip()) < 12 or "REPLACE_" in item:
            raise TradingError("Limitations and improvements must contain actual reviewer statements")
    for finding in report["findings"]:
        if (not isinstance(finding, dict) or finding.get("severity") not in ("critical", "high", "medium", "low", "info")
                or type(finding.get("resolved")) is not bool or not isinstance(finding.get("description"), str)
                or len(finding["description"].strip()) < 12):
            raise TradingError("Each finding requires severity, resolved boolean and a concrete description")
    blocked = any(f["severity"] in ("critical", "high") and not f["resolved"] for f in report["findings"])
    if approved and (report["recommendation"] != "approve" or blocked
                     or any(c["result"] != "pass" for c in checks.values())):
        raise TradingError("Review does not approve execution; resolve findings and review again")
    return report


def state_file():
    root = Path(os.environ.get("AGI_TRADING_STATE_DIR", Path.home() / ".local/state/agi-trading")).expanduser().resolve()
    if root == ROOT or ROOT in root.parents:
        raise TradingError("Private review receipts must be outside the source repository")
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    root.chmod(0o700)
    return root / "review.json"


def read_json(path):
    path = Path(path)
    if path.is_symlink() or not stat.S_ISREG(path.stat().st_mode) or path.stat().st_size > MAX_JSON:
        raise TradingError("Review JSON must be a regular file under 1 MB")
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise TradingError("Duplicate review JSON keys are not allowed")
            result[key] = value
        return result
    return json.loads(path.read_text(), object_pairs_hook=unique)


def write_private_json(path, value):
    destination = Path(path).expanduser()
    if destination.is_symlink():
        raise TradingError("Output must not be a symlink")
    destination = destination.resolve()
    if ROOT == destination or ROOT in destination.parents:
        raise TradingError("Evidence/review output must be outside the source repository")
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(encoded(value))
    try:
        temporary.chmod(0o600)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return {"saved": str(destination), "published": False}


def import_review(path):
    report = validate(read_json(path), snapshot(), approved=False)
    payload = encoded(report)
    destination = state_file()
    with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(payload)
    try:
        temporary.chmod(0o600)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    try:
        validate(report, snapshot(), approved=True)
        allowed = True
    except TradingError:
        allowed = False
    return {"review_saved_locally": True, "operations_allowed": allowed,
            "report_sha256": hashlib.sha256(payload).hexdigest(), "published": False,
            "note": "Local review record only; reviewer identity and claims are not independently authenticated"}


def require_review():
    path = state_file()
    if not path.exists():
        raise TradingError("Security review required before networking, credentials or official CLI execution. Read REVIEWING.md, run audit, obtain an independent review and import its report")
    if path.is_symlink() or stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise TradingError("Review receipt must be a private regular file (0600)")
    report = read_json(path)
    validate(report, snapshot(), approved=True)
    return report


def review_status():
    try:
        report = require_review()
        return {"operations_allowed": True, "recommendation": report["recommendation"],
                "score": report["score"], "identity_verified": False}
    except (TradingError, OSError, ValueError) as error:
        return {"operations_allowed": False, "reason": str(error)}


def attestation(path):
    report = validate(read_json(path), snapshot(), approved=False)
    result = {"kind": "agi-trading-review-commitment/v1", "commit": report["commit"],
              "source_sha256": report["source_sha256"], "runtime_sha256": report["runtime_sha256"],
              "report_sha256": digest(report), "recommendation": report["recommendation"],
              "reviewer_relationship": report["reviewer_relationship"],
              "claims": {"safety_certified": False, "reviewer_identity_verified": False, "anchored_onchain": False},
              "meaning": "Hashes bind these bytes to a review. A signature or blockchain timestamp cannot prove code is safe."}
    result["commitment_sha256"] = digest(result)
    result["anchor_payload"] = "AGI-TRADING-REVIEW:v1:" + result["commitment_sha256"]
    return result


def feedback(path):
    report = validate(read_json(path), snapshot(), approved=False)
    # No auto posting or starring; no token access. Share only after owner review.
    body = (f"Commit: {report['commit']}\nSource SHA-256: {report['source_sha256']}\n"
            f"Recommendation: {report['recommendation']}\nScore: {report['score']}/10\n"
            f"Reviewer relationship (self-asserted): {report['reviewer_relationship']}\n\n"
            "Replace this paragraph with a sanitized public summary and improvements. "
            "Do not include credentials, wallet sessions, private logs or exploitable vulnerability details.")
    return {"draft_only": True, "body": body,
            "issue_url": "https://github.com/ThreexOrange/AGI-Trading/issues/new?" + urlencode({"title": "Security review: " + report["commit"][:12], "body": body}),
            "star_url": "https://github.com/ThreexOrange/AGI-Trading",
            "note": "Publishing feedback and starring each require the actual user's separate opt-in. Negative reviews are welcome; no rewards or access gates depend on stars."}


def verify_attestation(report_path, commitment_path):
    expected = attestation(report_path)
    actual = read_json(commitment_path)
    if actual != expected:
        raise TradingError("Review commitment does not match the current report and source/runtime snapshot")
    return {"content_matches": True, "commitment_sha256": expected["commitment_sha256"],
            "signature_verified": False, "onchain_timestamp_verified": False, "safety_certified": False}
