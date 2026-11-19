#!/usr/bin/env python3
"""Enter Soulseek credentials privately and restart the prepared local service."""

import getpass
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import warnings


def main():
    if not sys.stdin.isatty():
        raise SystemExit("Run this command yourself in Terminal; credentials require a private prompt.")
    root = Path(__file__).resolve().parents[1] / ".local" / "ai-control"
    config_path = root / "data" / "slskd.yml"
    if not config_path.exists():
        raise SystemExit("The local installation has not been prepared yet.")
    config = json.loads(config_path.read_text())
    if config.get("soulseek", {}).get("username"):
        raise SystemExit("An account is already configured. Ask to update it after checking active transfers.")
    username = input("Soulseek username: ").strip()
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        password = getpass.getpass("Soulseek password (hidden): ")
    if not username or not password:
        raise SystemExit("Username and password are both required; nothing changed.")
    config["soulseek"] = {"username": username, "password": password, "listen_port": 50300}
    config["flags"]["no_connect"] = False
    # Replace atomically so the running configuration watcher cannot read a partial file.
    fd, temporary = tempfile.mkstemp(dir=config_path.parent, prefix=".slskd-")
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump(config, handle, indent=2)
            handle.write("\n")
        os.replace(temporary, config_path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    result = subprocess.run(
        ["/bin/launchctl", "kickstart", "-k", f"gui/{os.getuid()}/local.slskd"],
        check=False,
    )
    print("Credentials saved privately. They were not sent to chat.")
    if result.returncode:
        raise SystemExit("Service restart failed. Ask me to inspect launchd; do not paste the config file.")
    print("Service restarted and will attempt to connect. Ask me to verify the login.")
    print("Web username:", config["web"]["authentication"]["username"])
    print("Web password:", config["web"]["authentication"]["password"])


if __name__ == "__main__":
    main()
