"""Container entrypoint: keep the private launch token out of service logs."""

import secrets

import uvicorn

from .config import data_directory
from .main import create_app

if __name__ == "__main__":
    path = data_directory() / "launch.token"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(secrets.token_urlsafe(48))
    path.chmod(0o600)
    uvicorn.run(create_app(auth_token=path.read_text()), host="0.0.0.0", port=8765, access_log=False)
