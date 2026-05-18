"""Root conftest — macht import-tool/ für pytest importierbar.

Die eigentliche App liegt in import-tool/, die Tests dort importieren
direkt (from transformer import ...). Damit das von der Repo-Wurzel aus
funktioniert, wird import-tool/ in sys.path eingetragen.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "import-tool"))
