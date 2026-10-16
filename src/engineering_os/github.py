"""Bounded GitHub reads via authenticated gh; never logs subprocess stderr."""

import json
import subprocess
import time


class GitHub:
    def __init__(self, sleep=time.sleep):
        self.sleep = sleep

    def read(self, endpoint: str):
        if not endpoint.startswith(("repos/", "users/", "user", "rate_limit")):
            raise ValueError("Unsupported read endpoint")
        for attempt in range(3):
            result = subprocess.run(
                ["gh", "api", "--method", "GET", endpoint],
                capture_output=True,
                text=True,
                timeout=45,
            )
            if result.returncode == 0:
                return json.loads(result.stdout)
            transient = any(s in result.stderr for s in ("HTTP 502", "HTTP 503", "HTTP 504"))
            if not transient or attempt == 2:
                raise RuntimeError(
                    "GitHub read failed; check authentication, permissions or rate limit"
                )
            self.sleep(2**attempt)
        raise RuntimeError("Retry budget exhausted")

    def activity(self, owner: str):
        quota = self.read("rate_limit")["resources"]["core"]
        if quota["remaining"] < 100:
            raise RuntimeError("API reserve reached; retry after quota reset")
        events = self.read(f"users/{owner}/events?per_page=100")
        counts: dict[str, int] = {}
        for event in events:
            kind = event["type"]
            counts[kind] = counts.get(kind, 0) + 1
        return {
            "sample_size": len(events),
            "event_counts": counts,
            "scope": "Most recent 100 visible events; not contribution graph totals",
        }
