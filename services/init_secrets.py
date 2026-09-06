"""One-shot Compose setup. Each service receives only its scoped token volume."""

import os
import secrets
from pathlib import Path

for name in ("gateway", "search", "crawl"):
    root = Path("/secrets") / name
    root.mkdir(parents=True, exist_ok=True)
    os.chown(root, 10001, 10001)
    root.chmod(0o700)
    file = root / "token"
    if not file.exists():
        file.write_text(secrets.token_urlsafe(48))
    file.chmod(0o600)
    os.chown(file, 10001, 10001)
for name in ("app", "gateway", "crawler"):
    directory = Path("/volumes") / name
    os.chown(directory, 10001, 10001)
    directory.chmod(0o700)
config = Path("/searx-config/settings.yml")
if not config.exists():
    config.write_text(
        Path("/settings-template.yml").read_text().replace("GENERATE_AT_STARTUP", secrets.token_urlsafe(48))
    )
config.chmod(0o644)
