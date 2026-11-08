"""Start the Compose API and enforce a deadline from Docker's start timestamp."""
import subprocess
import time
from datetime import datetime
from urllib.error import URLError
from urllib.request import urlopen


def compose(*args):
    return subprocess.check_output(["docker", "compose", *args], text=True).strip()


def main():
    compose("up", "-d", "--no-deps", "--no-build", "--force-recreate", "api")
    container = compose("ps", "-aq", "api")
    started = subprocess.check_output(
        ["docker", "inspect", "-f", "{{.State.StartedAt}}", container], text=True,
    ).strip()
    deadline = datetime.fromisoformat(started.replace("Z", "+00:00")).timestamp() + 10
    while (remaining := deadline - time.time()) > 0:
        try:
            with urlopen("http://127.0.0.1:8000/health", timeout=min(remaining, .5)) as response:
                if response.status == 200 and time.time() <= deadline:
                    print("Readiness gate passed")
                    return
        except (URLError, TimeoutError):
            pass
        time.sleep(.15)
    subprocess.run(["docker", "compose", "logs", "--tail=100", "api"], check=False)
    raise SystemExit("Readiness gate failed: /health did not return 200 within 10 seconds")


if __name__ == "__main__":
    main()
