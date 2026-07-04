from typing import TYPE_CHECKING, Any

from ._version import __version__ as __version__

__all__ = [
    "AlloyRAG",
    "QueryParam",
    "RoleLLMConfig",
    "RoleSpec",
    "ROLES",
    "__version__",
]

if TYPE_CHECKING:
    from .alloyrag import (
        AlloyRAG as AlloyRAG,
        QueryParam as QueryParam,
        ROLES as ROLES,
        RoleLLMConfig as RoleLLMConfig,
        RoleSpec as RoleSpec,
    )


_LAZY_EXPORTS = {"AlloyRAG", "QueryParam", "RoleLLMConfig", "RoleSpec", "ROLES"}


def __getattr__(name: str) -> Any:
    if name in _LAZY_EXPORTS:
        from .alloyrag import AlloyRAG, QueryParam, RoleLLMConfig, RoleSpec, ROLES

        values = {
            "AlloyRAG": AlloyRAG,
            "QueryParam": QueryParam,
            "RoleLLMConfig": RoleLLMConfig,
            "RoleSpec": RoleSpec,
            "ROLES": ROLES,
        }
        value = values[name]
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__author__ = "Zirui Guo"
__url__ = "https://github.com/SikioN/AlloyRAG"
