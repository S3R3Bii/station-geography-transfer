"""Check protected dependencies against their pre-held canonical Git bytes."""

import hashlib
import json
import subprocess
from pathlib import Path


def verify(root="."):
    root = Path(root)
    manifest = json.loads((root / "FREEZE.json").read_text(encoding="utf-8"))
    assert manifest["held_outcomes_inspected"] is False
    for name, digest in manifest["dependencies"].items():
        data = (root / name).read_bytes()
        if not name.endswith(".gz"):
            data = data.replace(b"\r\n", b"\n")
        assert hashlib.sha256(data).hexdigest() == digest, name
        if (root / ".git").exists():
            for revision in [manifest["source_commit"], "HEAD"]:
                canonical = subprocess.check_output(
                    ["git", "show", revision + ":" + name], cwd=root
                )
                assert hashlib.sha256(canonical).hexdigest() == digest, (revision, name)
    return {
        "status": "PASS",
        "dependencies": len(manifest["dependencies"]),
        "source_commit": manifest["source_commit"],
    }


if __name__ == "__main__":
    print(json.dumps(verify()))
