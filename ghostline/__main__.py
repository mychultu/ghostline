"""
ghostline.__main__
==================

Lets you run the cli with:

    python3 -m ghostline run <name>
"""

import sys
from .cli import main

if __name__ == "__main__":
    sys.exit(main())
