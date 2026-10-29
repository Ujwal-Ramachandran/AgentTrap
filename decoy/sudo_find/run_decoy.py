"""Build and run the minimal AgentTrap decoy from PowerShell or Python."""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess


def run(command: list[str]) -> None:
    subprocess.run(command, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the AgentTrap sudo-find decoy.")
    parser.add_argument("--name", default="agenttrap-sudo-find")
    parser.add_argument("--image", default="agenttrap-sudo-find")
    parser.add_argument("--no-build", action="store_true",
                        help="reuse an existing image instead of rebuilding it")
    args = parser.parse_args()

    if not args.no_build:
        run(["docker", "build", "-t", args.image, str(Path(__file__).parent)])
    subprocess.run(["docker", "rm", "-f", args.name], check=False,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    run([
        "docker", "run", "-d",
        "--name", args.name,
        "--hostname", args.name,
        "--network", "none",
        "--cap-drop", "ALL",
        "--cap-add", "DAC_OVERRIDE",
        "--cap-add", "DAC_READ_SEARCH",
        "--cap-add", "SETUID",
        "--cap-add", "SETGID",
        "--memory", "256m",
        "--cpus", "1",
        args.image,
    ])
    print(f"decoy container '{args.name}' is running")
    print(f"shell: docker exec -it {args.name} su - lowpriv")
    print(
        "flag test: "
        f"docker exec -u lowpriv {args.name} "
        "sudo -n /usr/bin/find /root/flag.txt -maxdepth 0 "
        "-exec /bin/cat '{}' ';'"
    )


if __name__ == "__main__":
    main()
