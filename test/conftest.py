"""The skill's scripts are standalone command-line tools, not a package: put their folder on the
import path so the tests can import them as modules."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "telegram-bot-development" / "scripts"))
