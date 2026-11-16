"""Install the pinned upstream God's Eye View beside JARVIS."""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.gods_eye import CATALOG, REPOSITORY, REVISION, ROOT, executable

CATALOG_COMMAND = """
import { standaloneVoiceTools } from './server/standalone/voiceTools.js';
console.log(JSON.stringify(standaloneVoiceTools()));
"""


def install(root=ROOT):
    node, npm, git = executable("node"), executable("npm"), shutil.which("git")
    if not all((node, npm, git)):
        raise RuntimeError("Git ve Node.js (npm ile) kurulmalı. Kurulumdan sonra PowerShell’i yeniden aç.")
    version = subprocess.check_output([node, "--version"], text=True).strip()
    match = re.fullmatch(r"v(\d+)\.(\d+)\.(\d+)", version)
    if not match or not (int(match[1]) == 26 or (int(match[1]) == 24 and int(match[2]) >= 14)):
        raise RuntimeError(f"Node.js 24.14+ (24.x) veya 26.x gerekli. Algılanan sürüm {version}.")

    root.parent.mkdir(parents=True, exist_ok=True)
    if not root.exists():
        with tempfile.TemporaryDirectory(prefix="gev-install-", dir=root.parent) as staging:
            checkout = Path(staging) / "source"
            subprocess.run([git, "init", str(checkout)], check=True)
            subprocess.run([git, "fetch", "--depth=1", REPOSITORY, REVISION], cwd=checkout, check=True)
            subprocess.run([git, "checkout", "--detach", "FETCH_HEAD"], cwd=checkout, check=True)
            checkout.rename(root)
    revision = subprocess.check_output([git, "rev-parse", "HEAD"], cwd=root, text=True).strip()
    if revision != REVISION:
        raise RuntimeError(f"{root} farklı bir sürüm içeriyor. Kurulum için bu klasörü yeniden adlandır.")
    if subprocess.check_output([git, "status", "--porcelain", "--untracked-files=no"], cwd=root, text=True):
        raise RuntimeError(f"{root} içindeki kaynak dosyalar değiştirilmiş. Kurulum için bu klasörü yeniden adlandır.")

    stamp = root / CATALOG
    stamp.unlink(missing_ok=True)
    env = dict(os.environ, PUPPETEER_SKIP_DOWNLOAD="true")
    subprocess.run([npm, "ci", "--no-audit", "--no-fund"], cwd=root, env=env, check=True)
    tools = json.loads(subprocess.check_output(
        [node, "--input-type=module", "-e", CATALOG_COMMAND], cwd=root, encoding="utf-8",
    ))
    pending = stamp.with_suffix(".tmp")
    pending.write_text(json.dumps({"revision": revision, "tools": tools}), encoding="utf-8")
    pending.replace(stamp)
    print(f"God's Eye View hazır. {len(tools)} komut bulundu. JARVIS’te Ctrl+Shift+O ile aç.")


if __name__ == "__main__":
    try:
        install()
    except (OSError, subprocess.SubprocessError, ValueError, RuntimeError) as error:
        sys.exit(f"God's Eye View kurulumu durdu. {error}")
