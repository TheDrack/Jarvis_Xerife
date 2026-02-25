from app.domain.gears.cap_032_core import execute as cap_032_exec
from app.domain.gears.cap_008_core import execute as cap_008_exec
from app.domain.gears.cap_007_core import execute as cap_007_exec
from app.domain.gears.cap_006_core import execute as cap_006_exec
from app.domain.gears.cap_005_core import execute as cap_005_exec
from app.domain.gears.cap_004_core import execute as cap_004_exec
from app.domain.gears.cap_003_core import execute as cap_003_exec
from app.domain.gears.cap_001_core import execute as cap_001_exec
# -*- coding: utf-8 -*-
class Container:
    def __init__(self):
        self.registry = {
            "CAP-032": cap_032_exec,
            "CAP-008": cap_008_exec,
            "CAP-007": cap_007_exec,
            "CAP-006": cap_006_exec,
            "CAP-005": cap_005_exec,
            "CAP-004": cap_004_exec,
            "CAP-003": cap_003_exec,
            "CAP-001": cap_001_exec,}
