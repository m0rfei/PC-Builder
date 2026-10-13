"""Миграция 4: количество и архивный статус переносятся на модель."""

import sqlite3

from .database import DatabaseError


def migrate_schema_v4(connection: sqlite3.Connection) -> None:
    """Переносит сведения экземпляров в component_models, не удаляя старые строки."""
    invalid = connection.execute(
        """SELECT id FROM component_instances
           WHERE ownership_status NOT IN ('owned', 'archived')
              OR (ownership_status = 'owned' AND archived_at IS NOT NULL)
              OR (ownership_status = 'archived' AND archived_at IS NULL)
           LIMIT 1"""
    ).fetchone()
    if invalid:
        raise DatabaseError(
            f"Нельзя перенести модель: экземпляр {invalid[0]} имеет противоречивый статус или дату архивации."
        )

    connection.execute(
        """ALTER TABLE component_models ADD COLUMN quantity INTEGER NOT NULL DEFAULT 1
           CHECK (typeof(quantity) = 'integer' AND quantity >= 1)"""
    )
    connection.execute(
        """ALTER TABLE component_models ADD COLUMN status TEXT NOT NULL DEFAULT 'owned'
           CHECK (status IN ('owned', 'archived'))"""
    )
    connection.execute("ALTER TABLE component_models ADD COLUMN archived_at TEXT")

    connection.execute(
        """UPDATE component_models
           SET quantity = CASE
                 WHEN (SELECT COUNT(*) FROM component_instances i WHERE i.model_id = component_models.id) = 0 THEN 1
                 ELSE (SELECT COUNT(*) FROM component_instances i WHERE i.model_id = component_models.id)
               END,
               status = CASE
                 WHEN (SELECT COUNT(*) FROM component_instances i WHERE i.model_id = component_models.id) > 0
                  AND (SELECT COUNT(*) FROM component_instances i
                       WHERE i.model_id = component_models.id AND i.ownership_status = 'archived')
                      = (SELECT COUNT(*) FROM component_instances i WHERE i.model_id = component_models.id)
                 THEN 'archived' ELSE 'owned'
               END,
               archived_at = CASE
                 WHEN (SELECT COUNT(*) FROM component_instances i WHERE i.model_id = component_models.id) > 0
                  AND (SELECT COUNT(*) FROM component_instances i
                       WHERE i.model_id = component_models.id AND i.ownership_status = 'archived')
                      = (SELECT COUNT(*) FROM component_instances i WHERE i.model_id = component_models.id)
                 THEN (SELECT MAX(i.archived_at) FROM component_instances i WHERE i.model_id = component_models.id)
                 ELSE NULL
               END"""
    )

    connection.execute(
        """CREATE TRIGGER component_models_archive_state_insert
           BEFORE INSERT ON component_models
           WHEN NOT ((NEW.status = 'owned' AND NEW.archived_at IS NULL)
                  OR (NEW.status = 'archived' AND NEW.archived_at IS NOT NULL))
           BEGIN SELECT RAISE(ABORT, 'component status and archive date do not match'); END"""
    )
    connection.execute(
        """CREATE TRIGGER component_models_archive_state_update
           BEFORE UPDATE OF status, archived_at ON component_models
           WHEN NOT ((NEW.status = 'owned' AND NEW.archived_at IS NULL)
                  OR (NEW.status = 'archived' AND NEW.archived_at IS NOT NULL))
           BEGIN SELECT RAISE(ABORT, 'component status and archive date do not match'); END"""
    )
    connection.execute("PRAGMA user_version = 4")
