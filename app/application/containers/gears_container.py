from app.domain.gears.cap_101_core import execute as cap_101_exec
from app.domain.gears.cap_099_core import execute as cap_099_exec
from app.domain.gears.cap_096_core import execute as cap_096_exec
from app.domain.gears.cap_093_core import execute as cap_093_exec
from app.domain.gears.cap_092_core import execute as cap_092_exec
from app.domain.gears.cap_087_core import execute as cap_087_exec
from app.domain.gears.cap_080_core import execute as cap_080_exec
from app.domain.gears.cap_065_core import execute as cap_065_exec
from app.domain.gears.cap_064_core import execute as cap_064_exec
from app.domain.gears.cap_061_core import execute as cap_061_exec
from app.domain.gears.cap_057_core import execute as cap_057_exec
from app.domain.gears.cap_050_core import execute as cap_050_exec
from app.domain.gears.cap_045_core import execute as cap_045_exec
from app.domain.gears.cap_043_core import execute as cap_043_exec
from app.domain.gears.cap_032_core import execute as cap_032_exec
from app.domain.gears.cap_029_core import execute as cap_029_exec
from app.domain.gears.cap_028_core import execute as cap_028_exec
from app.domain.gears.cap_027_core import execute as cap_027_exec
from app.domain.gears.cap_023_core import execute as cap_023_exec
from app.domain.gears.cap_010_core import execute as cap_010_exec
from app.domain.gears.cap_009_core import execute as cap_009_exec
from app.domain.gears.cap_008_core import execute as cap_008_exec
from app.domain.gears.cap_006_core import execute as cap_006_exec
from app.domain.gears.cap_001_core import execute as cap_001_exec
# -*- coding: utf-8 -*-
class GearsContainer:
    def __init__(self):
        self.registry = {
            "CAP-101": cap_101_exec,
            "CAP-099": cap_099_exec,
            "CAP-096": cap_096_exec,
            "CAP-093": cap_093_exec,
            "CAP-092": cap_092_exec,
            "CAP-087": cap_087_exec,
            "CAP-080": cap_080_exec,
            "CAP-065": cap_065_exec,
            "CAP-064": cap_064_exec,
            "CAP-061": cap_061_exec,
            "CAP-057": cap_057_exec,
            "CAP-050": cap_050_exec,
            "CAP-045": cap_045_exec,
            "CAP-043": cap_043_exec,
            "CAP-032": cap_032_exec,
            "CAP-029": cap_029_exec,
            "CAP-028": cap_028_exec,
            "CAP-027": cap_027_exec,
            "CAP-023": cap_023_exec,
            "CAP-010": cap_010_exec,
            "CAP-009": cap_009_exec,
            "CAP-008": cap_008_exec,
            "CAP-006": cap_006_exec,
            "CAP-001": cap_001_exec,}
