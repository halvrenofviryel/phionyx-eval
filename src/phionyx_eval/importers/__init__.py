"""Cross-runtime evidence importers — F13 v0.6.0 W3.

Read foreign trace formats (Langfuse, LangSmith) and emit Phionyx-shaped
signed, hash-chained envelopes. Round-trip lossless for mappable fields;
unmapped-but-useful fields are preserved verbatim under
``subject.metadata.imported_extras`` so a future Phionyx-side exporter
could restore the foreign shape.

Each importer has its own envelope schema identifier
(``phionyx.imported_<source>_envelope.v1``) so consumers can dispatch on
provenance without re-parsing the payload.
"""

from __future__ import annotations

from .common import (
    ImportResult,
    MappingReport,
    build_imported_envelope,
)
from .langfuse import (
    LANGFUSE_SCHEMA,
    import_langfuse_trace,
)
from .langsmith import (
    LANGSMITH_SCHEMA,
    import_langsmith_run,
)

__all__ = [
    "ImportResult",
    "MappingReport",
    "build_imported_envelope",
    "LANGFUSE_SCHEMA",
    "import_langfuse_trace",
    "LANGSMITH_SCHEMA",
    "import_langsmith_run",
]
