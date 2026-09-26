#!/usr/bin/env python3
"""Vendor-side serial key generator for MUSTACOM BUSINESS MANAGER.

The application itself embeds a key generator in the Licence screen (admin
role); this CLI is the offline equivalent used by the vendor to answer
"Demander une licence" requests.

Usage:
    python tools/keygen.py --company "Client SARL" --user "M. Alaoui" \
        --machine ABCD1234EFGH --type professional --days 365 --devices 2

Override the master secret at build time so shipped builds do not share the
public development default:
    MUSTACOM_LICENSE_SECRET=<random> python tools/keygen.py ...

The same secret must be compiled into the build that will accept the key.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mustacom.core.license import (export_license_file, issue_license,  # noqa: E402
                                   normalize_key)


def main() -> int:
    parser = argparse.ArgumentParser(description="MUSTACOM serial key generator")
    parser.add_argument("--company", required=True)
    parser.add_argument("--user", default="")
    parser.add_argument("--machine", required=True,
                        help="machine ID shown on the customer's activation screen")
    parser.add_argument("--type", default="professional",
                        choices=("trial", "standard", "professional", "enterprise"))
    parser.add_argument("--days", type=int, default=365,
                        help="validity in days (0 = permanent)")
    parser.add_argument("--devices", type=int, default=1)
    parser.add_argument("--export", metavar="FILE.mlic", default="",
                        help="also write an offline activation file")
    args = parser.parse_args()

    payload, key, signature = issue_license(
        args.company, args.user, args.machine.strip().upper(), args.type,
        duration_days=args.days or None, max_devices=args.devices)

    print(f"Company   : {payload.company}")
    print(f"Type      : {payload.license_type}")
    print(f"Machine   : {payload.machine_id}")
    print(f"Issued    : {payload.issued_at}")
    print(f"Expires   : {payload.expires_at or 'permanent'}")
    print(f"Devices   : {payload.max_devices}")
    print(f"Serial key: {key}")
    print(f"Normalized: {normalize_key(key)}")

    if args.export:
        path = export_license_file(payload, signature, args.export)
        print(f"License file: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
