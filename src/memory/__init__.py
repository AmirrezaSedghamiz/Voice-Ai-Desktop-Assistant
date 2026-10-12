"""
Persistent Local Memory Subsystem (SQLite + FTS5).
Provides structured fact storage, durable notes, lexical full-text search,
and bounded user profile injection with zero GPU/VRAM overhead.
"""

from src.memory.store import (
    CURRENT_SCHEMA_VERSION,
    DatabaseIntegrityError,
    DatabaseStorageError,
    FactRecord,
    FtsNotAvailableError,
    FtsQuerySyntaxError,
    MemoryDeleteResult,
    MemorySearchHit,
    MemoryStore,
    MemoryStoreError,
    MemoryValidationError,
    MemoryWriteResult,
    NoteRecord,
    ProfileInjectionPayload,
    SchemaMigrationError,
)

__all__ = [
    "CURRENT_SCHEMA_VERSION",
    "DatabaseIntegrityError",
    "DatabaseStorageError",
    "FactRecord",
    "FtsNotAvailableError",
    "FtsQuerySyntaxError",
    "MemoryDeleteResult",
    "MemorySearchHit",
    "MemoryStore",
    "MemoryStoreError",
    "MemoryValidationError",
    "MemoryWriteResult",
    "NoteRecord",
    "ProfileInjectionPayload",
    "SchemaMigrationError",
]
