"""Run a command on the project-owned HAOS serial console (already logged in as root).

Use only with the disposable FHC VM. Never point this at an operating VM.
"""

import argparse
import socket
import time
from pathlib import Path


def run(command, timeout=10):
    path = Path.home() / ".local/share/fast-home-control-test/serial.sock"
    with socket.socket(socket.AF_UNIX) as connection:
        connection.settimeout(0.5)
        connection.connect(str(path))
        connection.sendall(command.encode() + b"\n")
        deadline = time.monotonic() + timeout
        data = b""
        while time.monotonic() < deadline:
            try:
                chunk = connection.recv(65536)
                if not chunk:
                    break
                data += chunk
                if data.endswith(b"# "):
                    break
            except TimeoutError:
                pass
        return data.decode(errors="replace")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command")
    parser.add_argument("--timeout", type=int, default=10)
    args = parser.parse_args()
    print(run(args.command, args.timeout))
