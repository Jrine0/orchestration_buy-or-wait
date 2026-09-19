"""Build code.zip at the repository root from code/, with a secret scan.

    python code/package.py

Excludes __pycache__, .env* files and personal notes (code/ref/INTERVIEW_PREP.md). Fails if any file,
or output.csv / log.txt next to it, contains something that looks like an Anthropic API key.
"""
from __future__ import annotations

import re
import sys
import zipfile
from pathlib import Path

CODE_DIR = Path(__file__).resolve().parent
REPO_ROOT = CODE_DIR.parent
KEY_PATTERN = re.compile(rb"sk-ant-[A-Za-z0-9_\-]{10,}")
EXCLUDED_NAMES = {"INTERVIEW_PREP.md"}


def included(p: Path) -> bool:
    return (p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"
            and not p.name.startswith(".env") and p.name not in EXCLUDED_NAMES)


def main() -> int:
    files = sorted(p for p in CODE_DIR.rglob("*") if included(p))
    suspects = [p for p in files if KEY_PATTERN.search(p.read_bytes())]
    for extra in (REPO_ROOT / "output.csv", REPO_ROOT / "log.txt"):
        if extra.exists() and KEY_PATTERN.search(extra.read_bytes()):
            suspects.append(extra)
    if suspects:
        print("refusing to package; possible API key in:", *suspects, sep="\n  ")
        return 1
    out = REPO_ROOT / "code.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for p in files:
            z.write(p, p.relative_to(REPO_ROOT).as_posix())
    with zipfile.ZipFile(out) as z:
        names = z.namelist()
    cases = sum(n.startswith("code/case_files/") for n in names)
    required = ["code/main.py", "code/README.md", "code/ARCHITECTURE.md", "code/requirements.txt",
                "code/evaluation/usage_report.md", "code/prompts/image_amount_extraction.md"]
    missing = [r for r in required if r not in names]
    print(f"wrote {out} ({len(names)} files, {out.stat().st_size // 1024} KB, {cases} case files); "
          f"secret scan clean; missing required: {missing or 'none'}")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
