#!/usr/bin/env python3
"""The coordinator loop this script stopped was removed in OPS-333.

There is no lease to release. Exit 2 so a caller cannot treat silence as
success. The harness rewrite is OPS-334. The old loop is recoverable from
tag pre-harness-rewrite (c114b2e).
"""
import sys


def main(argv=None):
    print(
        "error: the coordinator loop was removed in OPS-333; there is no lease to release. "
        "Recoverable from tag pre-harness-rewrite (c114b2e). The harness rewrite is OPS-334.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
