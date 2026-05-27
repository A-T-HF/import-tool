"""Root conftest — macht import-tool/ für pytest importierbar.

Die eigentliche App liegt in import-tool/, die Tests dort importieren
direkt (from transformer import ...). Damit das von der Repo-Wurzel aus
funktioniert, wird import-tool/ in sys.path eingetragen.
"""

import os
import sys
import time
from pathlib import Path

# Plattform-Vertrag (siehe /api/new-time): Tests laufen in Europe/Berlin,
# damit zeitkritische Asserts unabhaengig von der Host-Zeitzone bleiben.
os.environ["TZ"] = "Europe/Berlin"
if hasattr(time, "tzset"):
    time.tzset()

sys.path.insert(0, str(Path(__file__).parent / "import-tool"))
