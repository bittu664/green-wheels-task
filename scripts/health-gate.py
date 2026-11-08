"""Require readiness within 10 seconds of the API container starting."""

import subprocess
import time
from datetime import datetime
from urllib.error import URLError
from urllib.request import urlopen


def compose(*args):
    return subprocess.check_output(
        ["docker", "compose", *args],
        text=True,
    ).strip()


def main():
    compose(
        "up",
        "-d",
        "--no-deps",
        "--no-build",
        "--force-recreate",
        "api",
    )

    container = compose("ps", "-aq", "api")

    started = subprocess.check_output(
        ["docker", "inspect", "-f", "{{.State.StartedAt}}", container],
        text=True,
    ).strip()

    started_at = datetime.fromisoformat(
        started.replace("Z", "+00:00")
    ).timestamp()

    deadline = started_at + 10
    last_error = "No successful response received"

    while (remaining := deadline - time.time()) > 0:
        try:
            with urlopen(
                "http://127.0.0.1:8000/health",
                timeout=min(remaining, 0.5),
            ) as response:
                if response.status == 200 and time.time() <= deadline:
                    elapsed = time.time() - started_at
                    print(f"Readiness gate passed after {elapsed:.2f} seconds")
                    return

                last_error = f"HTTP {response.status}"

        except (URLError, OSError) as exc:
            last_error = f"{type(exc).__name__}: {exc}"

        time.sleep(min(0.15, max(0, deadline - time.time())))

    print(f"Last readiness failure: {last_error}", flush=True)

    subprocess.run(
        ["docker", "compose", "ps", "-a"],
        check=False,
    )
    subprocess.run(
        ["docker", "compose", "logs", "--tail=100", "api", "db"],
        check=False,
    )

    raise SystemExit(
        "Readiness gate failed: /health did not return 200 "
        "within 10 seconds of container start"
    )


if __name__ == "__main__":
    main()