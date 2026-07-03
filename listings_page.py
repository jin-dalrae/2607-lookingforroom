#!/usr/bin/env python3
"""Regenerate site/data.json for the apply queue UI."""

from __future__ import annotations

import argparse
import sys

from queue_export import write_queue_data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export apply queue to site/data.json")
    parser.parse_args(argv)
    try:
        path = write_queue_data()
        print(f"Wrote queue → {path}")
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())