from __future__ import annotations

import argparse
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

from .google_calendar import SCOPES


def run_auth_flow(*, client_secret_json: Path, token_path: Path, port: int = 8080) -> None:
    token_path.parent.mkdir(parents=True, exist_ok=True)
    flow = InstalledAppFlow.from_client_secrets_file(str(client_secret_json), SCOPES)
    creds = flow.run_local_server(
        host="localhost",
        bind_addr="0.0.0.0",
        port=port,
        open_browser=False,
    )
    token_path.write_text(creds.to_json())


def main() -> None:
    p = argparse.ArgumentParser(
        description="One-time Google OAuth for Calendar API (writes token json)."
    )
    p.add_argument(
        "--client-secret",
        required=True,
        help="Path to OAuth client secret JSON (mounted into container).",
    )
    p.add_argument(
        "--token",
        required=True,
        help="Path to write google token JSON (usually under /data).",
    )
    p.add_argument("--port", type=int, default=8080, help="Local server port for OAuth callback.")
    args = p.parse_args()

    run_auth_flow(
        client_secret_json=Path(args.client_secret),
        token_path=Path(args.token),
        port=args.port,
    )


if __name__ == "__main__":
    main()
