"""Developer entrypoints; service and launch credentials are never printed."""

import argparse
import os
import subprocess
import time
import webbrowser

import httpx

from customer_intelligence.config import data_directory


def compose_read(service, path):
    return subprocess.check_output(
        ["docker", "compose", "exec", "-T", service, "cat", path], text=True
    ).strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["connect-native", "open", "research"])
    parser.add_argument("--domain")
    parser.add_argument("--company-name")
    args = parser.parse_args()
    if args.action == "connect-native":
        value = compose_read("gateway", "/run/client-auth/token")
        path = data_directory() / "gateway.token"
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w") as file:
            file.write(value)
        print("The Mac app is connected to the local research gateway. Use Settings → Check connections.")
        return
    base = "http://127.0.0.1:" + os.environ.get("CIA_DOCKER_PORT", "8766")
    credential = compose_read("intelligence", "/data/launch.token")
    if args.action == "open":
        webbrowser.open(base + "/auth?token=" + credential)
        print("Opened the local Docker application.")
        return
    if not args.domain:
        parser.error("--domain is required for research")
    with httpx.Client(base_url=base, follow_redirects=True, headers={"Origin": base}, timeout=30) as client:
        client.get("/auth", params={"token": credential}).raise_for_status()
        response = client.post(
            "/api/runs", json={"target_domain": args.domain, "company_name": args.company_name}
        )
        if not response.is_success:
            raise SystemExit(response.json().get("detail", "Research could not start."))
        run = response.json()
        print("Started research. Run ID:", run["id"])
        while run["status"] == "running":
            print(run["stage"], flush=True)
            time.sleep(5)
            run = client.get("/api/runs/" + run["id"]).json()
        print(run["status"], run.get("error") or run["stage"])
        for account_id in run["account_ids"]:
            print(client.get(f"/api/accounts/{account_id}/export").text)


if __name__ == "__main__":
    main()
