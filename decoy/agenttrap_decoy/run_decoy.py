"""Build and launch the AgentTrap CHT decoy."""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", default="agenttrap-decoy")
    parser.add_argument("--image", default="agenttrap-decoy")
    parser.add_argument("--replace", action="store_true")
    parser.add_argument("--no-build", action="store_true")
    args = parser.parse_args()

    existing = subprocess.run(
        ["docker", "container", "inspect", args.name],
        capture_output=True,
    ).returncode == 0
    if existing and not args.replace:
        parser.error(f"container {args.name!r} exists; use --replace")
    if not args.no_build:
        subprocess.run(
            ["docker", "build", "-t", args.image, str(Path(__file__).parent)],
            check=True,
        )
    if existing:
        subprocess.run(["docker", "rm", "-f", args.name], check=True)
    subprocess.run([
        "docker", "run", "-d", "--name", args.name, "--hostname", args.name,
        "--network", "none", "--cap-drop", "ALL",
        "--cap-add", "SETUID", "--cap-add", "SETGID",
        "--memory", "256m", "--cpus", "1", "--pids-limit", "64", args.image,
    ], check=True)
    print(f"Container ready: {args.name}")


if __name__ == "__main__":
    main()
