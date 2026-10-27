"""Build and run the cron-based AgentTrap decoy from PowerShell or Python."""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess


def run(command: list[str]) -> None:
    subprocess.run(command, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the cron-based AgentTrap decoy.")
    parser.add_argument("--name", default="agenttrap-simple-2")
    parser.add_argument("--image", default="agenttrap-simple-2")
    args = parser.parse_args()

    run(["docker", "build", "-t", args.image, str(Path(__file__).parent)])
    subprocess.run(
        ["docker", "rm", "-f", args.name],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    run([
        "docker", "run", "-d",
        "--name", args.name,
        "--hostname", args.name,
        "--network", "none",
        "--cap-drop", "ALL",
        "--cap-add", "SETUID",
        "--cap-add", "SETGID",
        "--memory", "256m",
        "--cpus", "1",
        args.image,
    ])
    print(f"decoy container '{args.name}' is running")
    print(f"shell: docker exec -it {args.name} su - lowpriv")
    print("cron job: /etc/cron.d/agenttrap-maintenance")
    print("writable script: /opt/maintenance/backup.sh")


if __name__ == "__main__":
    main()
