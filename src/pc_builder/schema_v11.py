"""Миграция 11: именованные слоты состава сборки, включая пустые."""

import sqlite3


def migrate_schema_v11(connection: sqlite3.Connection) -> None:
    """Пересобирает таблицу состава без потери прежних позиций и количеств."""
    # The migration below uses an INNER JOIN to recover the slot category from
    # each component. Refuse to proceed if the legacy database already contains
    # dangling references; silently skipping those rows would lose build data.
    invalid = connection.execute("""SELECT bc.id FROM build_components bc
        LEFT JOIN builds b ON b.id=bc.build_id
        LEFT JOIN component_models cm ON cm.id=bc.component_id
        WHERE b.id IS NULL OR cm.id IS NULL LIMIT 1""").fetchone()
    if invalid is not None:
        raise sqlite3.IntegrityError(
            f"Нельзя применить миграцию v11: позиция сборки {invalid[0]} ссылается на отсутствующую сборку или комплектующее."
        )
    connection.execute("ALTER TABLE build_components RENAME TO build_components_v10")
    connection.execute("""CREATE TABLE build_components (
        id INTEGER PRIMARY KEY,
        build_id INTEGER NOT NULL REFERENCES builds(id) ON DELETE CASCADE,
        category TEXT NOT NULL CHECK(length(trim(category)) > 0),
        slot_index INTEGER NOT NULL CHECK(typeof(slot_index)='integer' AND slot_index >= 0),
        component_id INTEGER REFERENCES component_models(id) ON DELETE CASCADE,
        quantity INTEGER NOT NULL DEFAULT 1 CHECK(typeof(quantity)='integer' AND quantity >= 1),
        UNIQUE(build_id,category,slot_index)
    )""")
    connection.execute("""INSERT INTO build_components(id,build_id,category,slot_index,component_id,quantity)
        SELECT old.id,old.build_id,
            CASE WHEN cm.component_type IN ('hdd','ssd') THEN 'storage' ELSE cm.component_type END,
            ROW_NUMBER() OVER (
                PARTITION BY old.build_id,
                    CASE WHEN cm.component_type IN ('hdd','ssd') THEN 'storage' ELSE cm.component_type END
                ORDER BY old.id
            ) - 1,
            old.component_id,old.quantity
        FROM build_components_v10 old
        JOIN component_models cm ON cm.id=old.component_id
        ORDER BY old.build_id,cm.component_type,old.id""")
    connection.execute("DROP TABLE build_components_v10")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_build_components_component_id ON build_components(component_id)")

    # Набор пустых ячеек создаётся только один раз при создании сборки/миграции.
    # Поэтому удаление последнего динамического слота сохраняется между открытиями.
    connection.execute("""INSERT INTO build_components(build_id,category,slot_index,component_id,quantity)
        SELECT builds.id, defaults.category, defaults.slot_index, NULL, 1
        FROM builds
        CROSS JOIN (
            SELECT 'cpu' AS category,0 AS slot_index UNION ALL
            SELECT 'motherboard',0 UNION ALL SELECT 'psu',0 UNION ALL SELECT 'case',0 UNION ALL
            SELECT 'gpu',0 UNION ALL SELECT 'cpu_cooler',0 UNION ALL SELECT 'ram',0 UNION ALL
            SELECT 'storage',0
        ) defaults
        WHERE NOT EXISTS (
            SELECT 1 FROM build_components bc
            WHERE bc.build_id=builds.id AND bc.category=defaults.category
        )""")
    connection.execute("PRAGMA user_version=11")
