import json
import os
from pathlib import Path

import keyring

SERVICE = "Customer Intelligence Agent"


def data_directory():
    return Path(os.environ.get("CIA_DATA_DIR", Path.home() / "Library" / "Application Support" / SERVICE))


class Secrets:
    NAMES = {"openrouter": "OPENROUTER_API_KEY"}

    def get(self, name):
        if value := os.environ.get(self.NAMES[name]):
            return value
        if os.environ.get("CIA_SECRET_BACKEND") == "file":
            path = data_directory() / "credentials.json"
            return json.loads(path.read_text()).get(name) if path.exists() else None
        try:
            return keyring.get_password(SERVICE, name)
        except keyring.errors.KeyringError:
            return None

    def set(self, name, value):
        if name not in self.NAMES:
            raise ValueError("Unknown credential")
        if os.environ.get("CIA_SECRET_BACKEND") == "file":
            path = data_directory() / "credentials.json"
            values = json.loads(path.read_text()) if path.exists() else {}
            if value:
                values[name] = value
            else:
                values.pop(name, None)
            temporary = path.with_suffix(".tmp")
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(descriptor, "w") as output:
                json.dump(values, output)
            temporary.replace(path)
            return
        if value:
            keyring.set_password(SERVICE, name, value)
        else:
            try:
                keyring.delete_password(SERVICE, name)
            except keyring.errors.PasswordDeleteError:
                pass

    def status(self):
        return {
            name: {"configured": bool(self.get(name)), "environment": bool(os.environ.get(env))}
            for name, env in self.NAMES.items()
        }
