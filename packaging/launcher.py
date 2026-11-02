"""Entry point for PyInstaller, which needs a script rather than `python -m luma`."""

import sys

from luma.app import main

sys.exit(main())
