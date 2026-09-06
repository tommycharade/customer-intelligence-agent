import os
from pathlib import Path

import keyring

SERVICE = "Customer Intelligence Agent"


def data_directory():
    return Path(os.environ.get("CIA_DATA_DIR", Path.home() / "Library" / "Application Support" / SERVICE))


class Secrets:
    NAMES = {"openrouter": "OPENROUTER_API_KEY", "tavily": "TAVILY_API_KEY"}

    def get(self, name):
        if value := os.environ.get(self.NAMES[name]):
            return value
        try:
            return keyring.get_password(SERVICE, name)
        except keyring.errors.KeyringError:
            return None

    def set(self, name, value):
        if name not in self.NAMES:
            raise ValueError("Unknown credential")
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
