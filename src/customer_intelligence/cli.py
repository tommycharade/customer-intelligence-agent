import argparse
import threading
import webbrowser

import uvicorn

from .main import create_app


def main():
    parser = argparse.ArgumentParser(description="Start Customer Intelligence on this Mac")
    parser.add_argument("command", nargs="?", choices=["serve"], default="serve")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    app = create_app()
    url = f"http://127.0.0.1:{args.port}/auth?token={app.state.launch_token}"
    print(
        f"\nCustomer Intelligence is opening on your Mac.\nPrivate launch link: {url}\nKeep this terminal open. Press Ctrl+C to stop.\n",
        flush=True,
    )
    if not args.no_browser:
        threading.Timer(1.5, webbrowser.open, args=(url,)).start()
    uvicorn.run(app, host="127.0.0.1", port=args.port, access_log=False)


if __name__ == "__main__":
    main()
