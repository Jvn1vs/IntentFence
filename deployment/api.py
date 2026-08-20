"""Compatibility entrypoint for the documented deployment layout."""

from intentfence.api import app, run

__all__ = ["app", "run"]


if __name__ == "__main__":
    run()
