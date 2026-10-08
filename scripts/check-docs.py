#!/usr/bin/env python3
"""Checks this repo's docs hold together. Run it directly or via CI:

    python3 scripts/check-docs.py

Two checks, for the two ways these docs have actually gone wrong:

1. Internal links. Every relative link resolves to a file that exists, and every
   `#anchor` matches a heading in the file it points at. Headings get renamed and
   the links pointing at them rot silently.

2. Deployment drift. ARCHITECTURE.md repeats the testnet factory id, escrow WASM
   hash and settlement token. The contract repo's deployments/testnet.env is the
   source of truth, and after a redeploy these docs were left pointing at a
   superseded factory. If that file can't be fetched (offline, or the repo moved),
   this warns instead of failing, so a network blip never turns the build red.
"""

from __future__ import annotations

import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TESTNET_ENV = "https://raw.githubusercontent.com/TrustedEscrow/trustedescrow-contract/main/deployments/testnet.env"
# Keys in testnet.env, and the doc that repeats their values.
PINNED = {"FACTORY_ID", "ESCROW_WASM_HASH", "TOKEN"}
DEPLOYMENT_DOC = "ARCHITECTURE.md"


def slug(heading: str) -> str:
    """GitHub's heading anchors: lowercase, drop punctuation, spaces to hyphens."""
    text = re.sub(r"[`*_]", "", heading.strip().lower())
    text = re.sub(r"[^a-z0-9 \-]", "", text)
    return re.sub(r"\s+", "-", text).strip("-")


def check_links(docs: list[Path]) -> list[str]:
    anchors = {
        d.name: {slug(m.group(2)) for m in re.finditer(r"^(#{1,6})\s+(.+)$", d.read_text(), re.M)}
        for d in docs
    }
    problems: list[str] = []
    for doc in docs:
        for match in re.finditer(r"\[([^\]]*)\]\(([^)]+)\)", doc.read_text()):
            target = match.group(2).strip()
            if target.startswith(("http://", "https://", "mailto:", "#!")):
                continue
            path, _, fragment = target.partition("#")
            resolved = (doc.parent / path) if path else doc
            if not resolved.exists():
                problems.append(f"{doc.name}: link to a file that does not exist -> {target}")
                continue
            if fragment and resolved.name.endswith(".md") and fragment not in anchors.get(resolved.name, set()):
                problems.append(f"{doc.name}: link to a heading that does not exist -> {target}")
    return problems


def check_deployment(doc: Path) -> tuple[list[str], list[str]]:
    """Returns (problems, warnings)."""
    try:
        with urllib.request.urlopen(TESTNET_ENV, timeout=20) as response:
            env_text = response.read().decode()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return [], [f"could not fetch {TESTNET_ENV} ({exc}); skipped the deployment check"]

    deployed = {}
    for line in env_text.splitlines():
        key, _, value = line.partition("=")
        if key.strip() in PINNED and value.strip():
            deployed[key.strip()] = value.strip()

    missing = PINNED - deployed.keys()
    if missing:
        return [], [f"{', '.join(sorted(missing))} absent from testnet.env; skipped those"]

    text = doc.read_text()
    problems = [
        f"{doc.name} does not mention the deployed {key} ({value}). "
        "The contract repo was redeployed and these docs still point at the old one."
        for key, value in deployed.items()
        if value not in text
    ]
    return problems, []


def main() -> int:
    docs = sorted(ROOT.glob("*.md"))
    if not docs:
        print("no markdown files found", file=sys.stderr)
        return 1

    problems = check_links(docs)
    deployment_problems, warnings = check_deployment(ROOT / DEPLOYMENT_DOC)
    problems += deployment_problems

    for warning in warnings:
        print(f"warning: {warning}")
    for problem in problems:
        print(f"error: {problem}", file=sys.stderr)

    print(f"checked {len(docs)} markdown files")
    if problems:
        print(f"{len(problems)} problem(s) found", file=sys.stderr)
        return 1
    print("docs OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
