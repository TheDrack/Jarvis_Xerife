import warnings

def frozen_cap(name):
    warnings.warn(
        f"Capability {name} está congelada e não deve ser usada",
        DeprecationWarning
    )