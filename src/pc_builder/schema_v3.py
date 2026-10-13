"""DDL миграции 3: отдельные типизированные таблицы спецификаций."""

import sqlite3


COMPONENT_SPEC_TABLES = {
    "motherboard": "motherboard_specs",
    "cpu": "cpu_specs",
    "ram": "ram_specs",
    "gpu": "gpu_specs",
    "psu": "psu_specs",
    "ssd": "ssd_specs",
    "hdd": "hdd_specs",
    "cpu_cooler": "cpu_cooler_specs",
    "case_fan": "case_fan_specs",
    "case": "case_specs",
}

PCI_EXPRESS_VERSIONS = ("1.0", "2.0", "3.0", "4.0", "5.0", "6.0")
FORM_FACTORS = ("atx", "micro_atx", "mini_itx", "extended_atx", "mini_dtx", "dtx", "ssi_eeb")
RAM_TYPES = ("ddr2", "ddr3", "ddr3l", "ddr4", "ddr5")


def _enum_check(column: str, values: tuple[str, ...]) -> str:
    choices = ", ".join("'" + value + "'" for value in values)
    return f"{column} IS NULL OR {column} IN ({choices})"


def create_schema_v3(connection: sqlite3.Connection) -> None:
    """Создаёт типовые таблицы и проверки; вызывается внутри транзакции."""
    pcie = _enum_check("pcie_version", PCI_EXPRESS_VERSIONS)
    form = _enum_check("form_factor", FORM_FACTORS)
    ram_type = _enum_check("ram_type", RAM_TYPES)

    tables = [
        f"""CREATE TABLE cpu_specs (
            model_id INTEGER PRIMARY KEY REFERENCES component_models(id) ON DELETE RESTRICT,
            socket TEXT,
            cores INTEGER CHECK (cores IS NULL OR (typeof(cores) = 'integer' AND cores > 0)),
            threads INTEGER CHECK (threads IS NULL OR (typeof(threads) = 'integer' AND threads > 0)),
            base_clock_mhz REAL CHECK (base_clock_mhz IS NULL OR (typeof(base_clock_mhz) IN ('integer','real') AND base_clock_mhz > 0)),
            boost_clock_mhz REAL CHECK (boost_clock_mhz IS NULL OR (typeof(boost_clock_mhz) IN ('integer','real') AND boost_clock_mhz > 0)),
            tdp_w REAL CHECK (tdp_w IS NULL OR (typeof(tdp_w) IN ('integer','real') AND tdp_w >= 0)),
            has_integrated_gpu INTEGER CHECK (has_integrated_gpu IS NULL OR has_integrated_gpu IN (0, 1))
        )""",
        f"""CREATE TABLE motherboard_specs (
            model_id INTEGER PRIMARY KEY REFERENCES component_models(id) ON DELETE RESTRICT,
            socket TEXT,
            chipset TEXT,
            form_factor TEXT CHECK ({form}),
            ram_type TEXT CHECK ({ram_type}),
            ram_slots INTEGER CHECK (ram_slots IS NULL OR (typeof(ram_slots) = 'integer' AND ram_slots >= 0)),
            max_ram_gb REAL CHECK (max_ram_gb IS NULL OR (typeof(max_ram_gb) IN ('integer','real') AND max_ram_gb > 0)),
            max_ram_clock_mhz REAL CHECK (max_ram_clock_mhz IS NULL OR (typeof(max_ram_clock_mhz) IN ('integer','real') AND max_ram_clock_mhz > 0)),
            m2_slots INTEGER CHECK (m2_slots IS NULL OR (typeof(m2_slots) = 'integer' AND m2_slots >= 0)),
            sata_ports INTEGER CHECK (sata_ports IS NULL OR (typeof(sata_ports) = 'integer' AND sata_ports >= 0)),
            pcie_version TEXT CHECK ({pcie})
        )""",
        f"""CREATE TABLE ram_specs (
            model_id INTEGER PRIMARY KEY REFERENCES component_models(id) ON DELETE RESTRICT,
            ram_type TEXT CHECK ({ram_type}),
            capacity_gb REAL CHECK (capacity_gb IS NULL OR (typeof(capacity_gb) IN ('integer','real') AND capacity_gb > 0)),
            frequency_mhz REAL CHECK (frequency_mhz IS NULL OR (typeof(frequency_mhz) IN ('integer','real') AND frequency_mhz > 0)),
            form_factor TEXT CHECK (form_factor IS NULL OR form_factor IN ('dimm','so_dimm','micro_dimm','udimm','rdimm','lrdimm'))
        )""",
        f"""CREATE TABLE gpu_specs (
            model_id INTEGER PRIMARY KEY REFERENCES component_models(id) ON DELETE RESTRICT,
            vram_gb REAL CHECK (vram_gb IS NULL OR (typeof(vram_gb) IN ('integer','real') AND vram_gb > 0)),
            vram_type TEXT CHECK (vram_type IS NULL OR vram_type IN ('gddr3','gddr5','gddr5x','gddr6','gddr6x','gddr7','hbm','hbm2','hbm2e','hbm3','hbm3e')),
            length_mm REAL CHECK (length_mm IS NULL OR (typeof(length_mm) IN ('integer','real') AND length_mm >= 0)),
            thickness_mm REAL CHECK (thickness_mm IS NULL OR (typeof(thickness_mm) IN ('integer','real') AND thickness_mm >= 0)),
            slot_width REAL CHECK (slot_width IS NULL OR (typeof(slot_width) IN ('integer','real') AND slot_width >= 0)),
            power_w REAL CHECK (power_w IS NULL OR (typeof(power_w) IN ('integer','real') AND power_w >= 0)),
            recommended_psu_w REAL CHECK (recommended_psu_w IS NULL OR (typeof(recommended_psu_w) IN ('integer','real') AND recommended_psu_w >= 0))
        )""",
        f"""CREATE TABLE psu_specs (
            model_id INTEGER PRIMARY KEY REFERENCES component_models(id) ON DELETE RESTRICT,
            rated_power_w REAL CHECK (rated_power_w IS NULL OR (typeof(rated_power_w) IN ('integer','real') AND rated_power_w >= 0)),
            form_factor TEXT CHECK (form_factor IS NULL OR form_factor IN ('atx','sfx','sfx_l','tfx','flex_atx','1u','2u','proprietary')),
            efficiency_rating TEXT CHECK (efficiency_rating IS NULL OR efficiency_rating IN ('80_plus','80_plus_bronze','80_plus_silver','80_plus_gold','80_plus_platinum','80_plus_titanium')),
            pcie_6_2pin_count INTEGER CHECK (pcie_6_2pin_count IS NULL OR (typeof(pcie_6_2pin_count) = 'integer' AND pcie_6_2pin_count >= 0)),
            eps_4_4pin_count INTEGER CHECK (eps_4_4pin_count IS NULL OR (typeof(eps_4_4pin_count) = 'integer' AND eps_4_4pin_count >= 0)),
            native_12vhpwr INTEGER CHECK (native_12vhpwr IS NULL OR native_12vhpwr IN (0,1)),
            native_12v2x6 INTEGER CHECK (native_12v2x6 IS NULL OR native_12v2x6 IN (0,1)),
            sata_power_count INTEGER CHECK (sata_power_count IS NULL OR (typeof(sata_power_count) = 'integer' AND sata_power_count >= 0))
        )""",
        f"""CREATE TABLE ssd_specs (
            model_id INTEGER PRIMARY KEY REFERENCES component_models(id) ON DELETE RESTRICT,
            capacity_gb REAL CHECK (capacity_gb IS NULL OR (typeof(capacity_gb) IN ('integer','real') AND capacity_gb > 0)),
            form_factor TEXT CHECK (form_factor IS NULL OR form_factor IN ('2_5_in','m2_2230','m2_2242','m2_2260','m2_2280','m2_22110','u2','u3','add_in_card')),
            interface_type TEXT CHECK (interface_type IS NULL OR interface_type IN ('sata','pcie_nvme')),
            pcie_version TEXT CHECK ({pcie}),
            power_w REAL CHECK (power_w IS NULL OR (typeof(power_w) IN ('integer','real') AND power_w >= 0))
        )""",
        f"""CREATE TABLE hdd_specs (
            model_id INTEGER PRIMARY KEY REFERENCES component_models(id) ON DELETE RESTRICT,
            capacity_gb REAL CHECK (capacity_gb IS NULL OR (typeof(capacity_gb) IN ('integer','real') AND capacity_gb > 0)),
            form_factor TEXT CHECK (form_factor IS NULL OR form_factor IN ('2_5_in','3_5_in')),
            interface_type TEXT CHECK (interface_type IS NULL OR interface_type IN ('sata','sas','ide')),
            power_w REAL CHECK (power_w IS NULL OR (typeof(power_w) IN ('integer','real') AND power_w >= 0))
        )""",
        f"""CREATE TABLE cpu_cooler_specs (
            model_id INTEGER PRIMARY KEY REFERENCES component_models(id) ON DELETE RESTRICT,
            cooling_type TEXT CHECK (cooling_type IS NULL OR cooling_type IN ('air','liquid')),
            height_mm REAL CHECK (height_mm IS NULL OR (typeof(height_mm) IN ('integer','real') AND height_mm >= 0)),
            power_w REAL CHECK (power_w IS NULL OR (typeof(power_w) IN ('integer','real') AND power_w >= 0))
        )""",
        f"""CREATE TABLE case_fan_specs (
            model_id INTEGER PRIMARY KEY REFERENCES component_models(id) ON DELETE RESTRICT,
            size_mm REAL CHECK (size_mm IS NULL OR (typeof(size_mm) IN ('integer','real') AND size_mm > 0)),
            thickness_mm REAL CHECK (thickness_mm IS NULL OR (typeof(thickness_mm) IN ('integer','real') AND thickness_mm >= 0)),
            connector_type TEXT CHECK (connector_type IS NULL OR connector_type IN ('3_pin','4_pin_pwm','molex_4pin','sata_power','proprietary','other')),
            power_w REAL CHECK (power_w IS NULL OR (typeof(power_w) IN ('integer','real') AND power_w >= 0)),
            max_rpm INTEGER CHECK (max_rpm IS NULL OR (typeof(max_rpm) = 'integer' AND max_rpm >= 0))
        )""",
        f"""CREATE TABLE case_specs (
            model_id INTEGER PRIMARY KEY REFERENCES component_models(id) ON DELETE RESTRICT,
            max_gpu_length_mm REAL CHECK (max_gpu_length_mm IS NULL OR (typeof(max_gpu_length_mm) IN ('integer','real') AND max_gpu_length_mm >= 0)),
            max_cpu_cooler_height_mm REAL CHECK (max_cpu_cooler_height_mm IS NULL OR (typeof(max_cpu_cooler_height_mm) IN ('integer','real') AND max_cpu_cooler_height_mm >= 0)),
            max_psu_length_mm REAL CHECK (max_psu_length_mm IS NULL OR (typeof(max_psu_length_mm) IN ('integer','real') AND max_psu_length_mm >= 0)),
            drive_2_5_bays INTEGER CHECK (drive_2_5_bays IS NULL OR (typeof(drive_2_5_bays) = 'integer' AND drive_2_5_bays >= 0)),
            drive_3_5_bays INTEGER CHECK (drive_3_5_bays IS NULL OR (typeof(drive_3_5_bays) = 'integer' AND drive_3_5_bays >= 0))
        )""",
    ]
    for statement in tables:
        connection.execute(statement)

    children = [
        """CREATE TABLE gpu_power_connectors (
            model_id INTEGER NOT NULL REFERENCES gpu_specs(model_id) ON DELETE CASCADE,
            connector_type TEXT NOT NULL CHECK (connector_type IN ('pcie_6pin','pcie_8pin','12vhpwr','12v_2x6')),
            quantity INTEGER NOT NULL CHECK (typeof(quantity) = 'integer' AND quantity > 0),
            PRIMARY KEY (model_id, connector_type)
        )""",
        """CREATE TABLE cpu_cooler_supported_sockets (
            model_id INTEGER NOT NULL REFERENCES cpu_cooler_specs(model_id) ON DELETE CASCADE,
            socket TEXT NOT NULL CHECK (length(trim(socket)) > 0),
            PRIMARY KEY (model_id, socket)
        )""",
        """CREATE TABLE case_supported_form_factors (
            model_id INTEGER NOT NULL REFERENCES case_specs(model_id) ON DELETE CASCADE,
            form_factor TEXT NOT NULL CHECK (form_factor IN ('atx','micro_atx','mini_itx','extended_atx','mini_dtx','dtx','ssi_eeb')),
            PRIMARY KEY (model_id, form_factor)
        )""",
        """CREATE TABLE case_radiator_support (
            model_id INTEGER NOT NULL REFERENCES case_specs(model_id) ON DELETE CASCADE,
            size_mm INTEGER NOT NULL CHECK (typeof(size_mm) = 'integer' AND size_mm > 0),
            PRIMARY KEY (model_id, size_mm)
        )""",
    ]
    for statement in children:
        connection.execute(statement)

    allowed_types = ", ".join("'" + component_type + "'" for component_type in COMPONENT_SPEC_TABLES)
    connection.execute(
        f"""CREATE TRIGGER component_models_type_insert
            BEFORE INSERT ON component_models
            WHEN NEW.component_type NOT IN ({allowed_types})
            BEGIN SELECT RAISE(ABORT, 'unsupported component type'); END"""
    )
    connection.execute(
        f"""CREATE TRIGGER component_models_type_update
            BEFORE UPDATE OF component_type ON component_models
            WHEN NEW.component_type NOT IN ({allowed_types})
            BEGIN SELECT RAISE(ABORT, 'unsupported component type'); END"""
    )
    for component_type, table in COMPONENT_SPEC_TABLES.items():
        for action in ("INSERT", "UPDATE"):
            trigger_name = f"{table}_component_type_{action.lower()}"
            connection.execute(
                f"""CREATE TRIGGER {trigger_name}
                    BEFORE {action} ON {table}
                    WHEN (SELECT component_type FROM component_models WHERE id = NEW.model_id) != '{component_type}'
                    BEGIN SELECT RAISE(ABORT, 'specification type does not match component model'); END"""
            )
