"""Entry point for the ArcGIS Pro add-in:  propy noisebox_cli.py <command> ...   (see noisebox/cli.py)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from noisebox.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
