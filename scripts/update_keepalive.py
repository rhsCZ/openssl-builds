#!/usr/bin/env python3
"""Update keepalive state to keep scheduled workflows active."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", required=True)
    args = parser.parse_args()

    current_time = datetime.now(ZoneInfo("Europe/Prague"))
    state_path = Path(args.state)
    state_path.parent.mkdir(parents=True, exist_ok=True)

    state = {
        "last_keepalive_at": current_time.strftime("%d.%m.%Y %H:%M:%S %z")
    }

    state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
