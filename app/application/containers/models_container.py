from app.domain.models.cap_100_core import execute as cap_100_exec
from app.domain.models.cap_034_core import execute as cap_034_exec
from app.domain.models.cap_033_core import execute as cap_033_exec
from app.domain.models.cap_023_core import execute as cap_023_exec
from app.domain.models.cap_002_core import execute as cap_002_exec
# -*- coding: utf-8 -*-
class Container:
    def __init__(self):
        self.registry = {
            "CAP-100": cap_100_exec,
            "CAP-034": cap_034_exec,
            "CAP-033": cap_033_exec,
            "CAP-023": cap_023_exec,
            "CAP-002": cap_002_exec,}
