"""
Dialect-portable column types.

Production runs on PostgreSQL and uses its native `JSONB` and `UUID` types.
Those types do not exist on SQLite, which the project uses for local runs and
for the SIH demo fallback where no database server is available.

`with_variant` keeps PostgreSQL exactly as it was and substitutes an equivalent
portable type elsewhere, so the same models serve both without a code change:

    JSONB  → JSON     on SQLite
    UUID   → CHAR(36) on SQLite   (ids are already generated as strings)
"""

from __future__ import annotations

from sqlalchemy import JSON, String
from sqlalchemy.dialects.postgresql import JSONB, UUID

# JSON document column: JSONB on PostgreSQL, JSON elsewhere.
JSONType = JSONB().with_variant(JSON(), "sqlite")

# Identifier column. `as_uuid=False` means values are handled as strings on
# both dialects, so nothing downstream has to care which one is in use.
UUIDType = UUID(as_uuid=False).with_variant(String(36), "sqlite")
