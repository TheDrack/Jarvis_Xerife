from app.adapters.cap_095_core import execute as cap_095_exec
from app.adapters.cap_077_core import execute as cap_077_exec
from app.adapters.cap_072_core import execute as cap_072_exec
from app.adapters.cap_067_core import execute as cap_067_exec
from app.adapters.cap_062_core import execute as cap_062_exec
from app.adapters.cap_059_core import execute as cap_059_exec
from app.adapters.cap_047_core import execute as cap_047_exec
from app.adapters.cap_044_core import execute as cap_044_exec
from app.adapters.cap_040_core import execute as cap_040_exec
from app.adapters.cap_039_core import execute as cap_039_exec
# -*- coding: utf-8 -*-
class AdaptersContainer:
    def __init__(self):
        self.registry = {
            "CAP-095": cap_095_exec,
            "CAP-077": cap_077_exec,
            "CAP-072": cap_072_exec,
            "CAP-067": cap_067_exec,
            "CAP-062": cap_062_exec,
            "CAP-059": cap_059_exec,
            "CAP-047": cap_047_exec,
            "CAP-044": cap_044_exec,
            "CAP-040": cap_040_exec,
            "CAP-039": cap_039_exec,}
