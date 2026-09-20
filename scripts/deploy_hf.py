"""Deploy AgentTrace to a Hugging Face Space, using Python only.

No git and no local Docker required -- Spaces builds the image server side.

    pip install huggingface_hub
    python scripts/deploy_hf.py --space your-username/agenttrace --token hf_xxx

The token needs WRITE permission: https://huggingface.co/settings/tokens
Set GEMINI_API_KEY as a Space secret (Settings -> Variables and secrets) or
pass --gemini-key to have this script set it for you.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SPACE_HEADER = """---
title: AgentTrace
emoji: 🔎
colorFrom: indigo
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
short_description: Agentic RAG over PDFs with a live, step-by-step reasoning trace
---

"""

# Everything that is not needed to build the image server side.
IGNORE = [
    ".git*",
    ".env",
    ".env.*",
    "**/node_modules/**",
    "frontend/dist/**",
    "backend/static/**",
    "data/index/**",
    "data/uploads/**",
    "**/__pycache__/**",
    "**/*.pyc",
    "tests/**",
    "docs/**",
    ".pytest_cache/**",
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--space", required=True, help="Space id, e.g. alice/agenttrace")
    parser.add_argument("--token", default=os.getenv("HF_TOKEN"), help="HF write token, or set HF_TOKEN")
    parser.add_argument("--gemini-key", default=None, help="Also set GEMINI_API_KEY as a Space secret")
    parser.add_argument("--private", action="store_true", help="Create the Space as private")
    args = parser.parse_args()

    if not args.token:
        print("A write token is required: --token hf_... or export HF_TOKEN", file=sys.stderr)
        return 2

    try:
        from huggingface_hub import HfApi
    except ImportError:
        print("pip install huggingface_hub", file=sys.stderr)
        return 1

    api = HfApi(token=args.token)

    api.create_repo(
        repo_id=args.space,
        repo_type="space",
        space_sdk="docker",
        private=args.private,
        exist_ok=True,
    )
    print(f"space ready: https://huggingface.co/spaces/{args.space}")

    # Spaces reads its configuration from YAML frontmatter in README.md, so the
    # Space gets its own copy of the project README with that block prepended.
    space_readme = ROOT / ".hf_readme.md"
    space_readme.write_text(
        SPACE_HEADER + (ROOT / "README.md").read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    try:
        api.upload_folder(
            folder_path=str(ROOT),
            repo_id=args.space,
            repo_type="space",
            ignore_patterns=IGNORE + ["README.md", ".hf_readme.md"],
            commit_message="Deploy AgentTrace",
        )
        api.upload_file(
            path_or_fileobj=str(space_readme),
            path_in_repo="README.md",
            repo_id=args.space,
            repo_type="space",
            commit_message="Space configuration",
        )
    finally:
        space_readme.unlink(missing_ok=True)

    if args.gemini_key:
        api.add_space_secret(repo_id=args.space, key="GEMINI_API_KEY", value=args.gemini_key)
        print("GEMINI_API_KEY set as a Space secret")
    else:
        print(
            "\nNow set GEMINI_API_KEY under Settings -> Variables and secrets, "
            "or re-run with --gemini-key."
        )

    print(f"\nBuilding. Watch it at https://huggingface.co/spaces/{args.space}?logs=build")
    print("First build takes 3-5 minutes (faiss and the npm install dominate).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
