"""
Executable module entry point for Quality Lab.
Allows running via: python -m quality_lab
"""

import sys
from quality_lab.cli import main

if __name__ == "__main__":
    sys.exit(main())
