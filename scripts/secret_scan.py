"""Scan staged (or tracked) Git content for credential-shaped secrets.

Usage:
    python scripts/secret_scan.py            # scan currently staged diff
    python scripts/secret_scan.py --tree     # scan every tracked file

Exit codes: 0 = clean, 1 = at least one candidate hit.

The scanner is deliberately conservative: anything matching the allowlist
(placeholders, documentation-format dummy tokens, docker-compose variable
interpolation) is reported as clean, and every hit is printed with context so a
human can make the final call before committing.
"""
from __future__ import annotations

import io
import re
import subprocess
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

PATTERNS: dict[str, re.Pattern[str]] = {
    "telegram bot token": re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{30,}\b"),
    "jwt": re.compile(r"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
    "private key block": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "aws access key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "slack token": re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
    "google api key": re.compile(r"AIza[0-9A-Za-z_-]{35}"),
    "github token": re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}"),
    "postgres dsn with credentials": re.compile(
        r"postgres(?:ql)?(?:\+[a-z]+)?://[^\s:/@]+:[^\s@]{4,}@"
    ),
    "assigned secret literal": re.compile(
        r"(?im)^\s*[A-Za-z_]*(?:password|secret|token|apikey|api_key)[A-Za-z_]*"
        r"\s*[:=]\s*[\"'][^\"']{16,}[\"']"
    ),
}

# Known-benign contexts. Each hit is also printed for human review.
ALLOW_SUBSTRINGS = (
    "change-me",
    "placeholder",
    "example",
    "test-",
    "fake",
    # docker-compose dev defaults are pure variable interpolation and the app
    # refuses to boot in production without real secrets.
    "${postgres_",
    # Telegram's canonical documentation-format dummy token used by the test
    # suite via monkeypatch; it authenticates against nothing.
    "123456789:abcdefghijklmnopqrstuvwxyz-1234567890",
)


def git_files(staged_only: bool) -> list[str]:
    if staged_only:
        out = subprocess.run(
            ["git", "diff", "--cached", "--name-only"], capture_output=True, text=True
        )
        if out.stdout.strip():
            return out.stdout.split()
        # Nothing staged: fall back to the whole tree so a bare run is useful.
    out = subprocess.run(["git", "ls-files"], capture_output=True, text=True)
    return out.stdout.split()


def read_blob(rel: str) -> str | None:
    res = subprocess.run(["git", "show", f":{rel}"], capture_output=True)
    if res.returncode != 0:
        return None
    return res.stdout.decode("utf-8", errors="replace")


def main() -> int:
    staged_only = "--tree" not in sys.argv
    files = git_files(staged_only)
    mode = "staged" if staged_only and files else "tracked tree"
    print(f"scanning {len(files)} files ({mode})")

    hits = 0
    for rel in files:
        text = read_blob(rel)
        if text is None:
            continue
        for name, rx in PATTERNS.items():
            for m in rx.finditer(text):
                ctx = text[max(0, m.start() - 70): m.end() + 50]
                ctx = " ".join(ctx.split())
                if any(a in ctx.lower() for a in ALLOW_SUBSTRINGS):
                    continue
                print(f"HIT [{name}] in {rel}:\n    ...{ctx}...")
                hits += 1

    print(f"\nTOTAL SECRET HITS: {hits}")
    if hits:
        print("Review every hit above. Real secrets must be moved to environment")
        print("variables and rotated; adjust the allowlist only for known dummies.")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
