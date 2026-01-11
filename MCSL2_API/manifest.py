from __future__ import annotations

from typing import List
from typing import Optional

try:
    from pydantic import BaseModel  # type: ignore
    from pydantic import Field  # type: ignore

    _HAS_PYDANTIC = True
except Exception:
    BaseModel = object  # type: ignore
    Field = None  # type: ignore
    _HAS_PYDANTIC = False


if _HAS_PYDANTIC:

    class PluginManifest(BaseModel):  # type: ignore[misc]
        id: str
        version: str
        dependencies: List[str] = Field(default_factory=list)  # type: ignore[call-arg]
        permissions: List[str] = Field(default_factory=list)  # type: ignore[call-arg]

        name: Optional[str] = None
        description: Optional[str] = None
        authors: List[str] = Field(default_factory=list)  # type: ignore[call-arg]

else:

    class PluginManifest:  # type: ignore[no-redef]
        def __init__(
            self,
            *,
            id: str,
            version: str,
            dependencies: Optional[List[str]] = None,
            permissions: Optional[List[str]] = None,
            name: Optional[str] = None,
            description: Optional[str] = None,
            authors: Optional[List[str]] = None,
        ) -> None:
            self.id = str(id)
            self.version = str(version)
            self.dependencies = list(dependencies or [])
            self.permissions = list(permissions or [])
            self.name = name
            self.description = description
            self.authors = list(authors or [])
