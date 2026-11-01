"""Output filtering and strict, decimal-based input validation."""
import os
import re
from decimal import Decimal, InvalidOperation


class TradingError(Exception):
    pass


SENSITIVE = {
    "accesstoken", "refreshtoken", "apikey", "secretkey", "apisecret", "secret",
    "passphrase", "password", "privatekey", "mnemonic", "seedphrase", "clientid",
    "sessiontoken", "sessionkey", "sessioncert", "teeid", "sateeid", "encryptedsessionsk",
    "signingkey", "authorization", "accesssign", "xbapisign", "rawtx", "rawtxdata",
    "accountid", "currentaccountid",
}


def redact(value):
    if isinstance(value, dict):
        return {k: "[REDACTED]" if re.sub(r"[^a-z0-9]", "", k.lower()) in SENSITIVE
                else redact(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(v) for v in value]
    if isinstance(value, str):
        for k, v in os.environ.items():
            if len(v) >= 4 and any(part in k.upper() for part in
                                   ("API_KEY", "SECRET", "PASSPHRASE", "PASSWORD", "TOKEN")):
                value = value.replace(v, "[REDACTED]")
        value = re.sub(r"-----BEGIN [^-]*PRIVATE KEY-----.*?-----END [^-]*PRIVATE KEY-----",
                       "[REDACTED PRIVATE KEY]", value, flags=re.S)
        value = re.sub(r"(?i)(bearer\s+)[\w.\-/+=]+", r"\1[REDACTED]", value)
        value = re.sub(r'(?i)((?:access[_-]?token|refresh[_-]?token|api[_-]?key|secret[_-]?key|passphrase|client[_-]?id)[\"\s:=]+)[^\s,\"&}]+',
                       r'\1[REDACTED]', value)
    return value


def positive(value, name="amount"):
    text = str(value)
    if not re.fullmatch(r"\d{1,20}(?:\.\d{1,18})?", text):
        raise TradingError(f"{name} must be a positive decimal string, without exponent notation")
    try:
        number = Decimal(text)
    except InvalidOperation as exc:
        raise TradingError(f"Invalid {name}") from exc
    if not number.is_finite() or number <= 0:
        raise TradingError(f"{name} must be finite and greater than zero")
    return number


def identifier(value, name="identifier"):
    if not re.fullmatch(r"[A-Za-z0-9_.:/-]{1,160}", value) or value.startswith("-"):
        raise TradingError(f"Invalid {name}")
    return value


def symbol(value):
    value = value.upper()
    if not re.fullmatch(r"[A-Z0-9]{3,30}", value):
        raise TradingError("Invalid symbol")
    return value


def require_env(names):
    missing = [n for n in names if not os.environ.get(n)]
    if missing:
        raise TradingError("Missing environment variables: " + ", ".join(missing))
    return [os.environ[n] for n in names]
