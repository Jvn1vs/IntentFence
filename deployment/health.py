from __future__ import annotations

import argparse

import httpx


def main() -> None:
    parser = argparse.ArgumentParser(description="Check a running IntentFence API")
    parser.add_argument("--url", default="http://127.0.0.1:8000/health")
    args = parser.parse_args()
    response = httpx.get(args.url, timeout=5)
    response.raise_for_status()
    print(response.json())


if __name__ == "__main__":
    main()
