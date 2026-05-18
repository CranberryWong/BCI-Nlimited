"""Compatibility entry for the new BCI local data-flow server.

The original single-file Flask/OSC/XDF script has been split into the
`server/` package. Keep this filename so existing launch instructions still
work while new development uses `python -m server.app` or `bci-server`.
"""

from server.app import main


if __name__ == "__main__":
    main()

