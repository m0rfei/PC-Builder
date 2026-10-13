"""Начальные значения редактируемых справочников."""

INITIAL_MANUFACTURERS = {
    "cpu": ("AMD", "Intel"),
    "motherboard": ("ASUS", "MSI", "Gigabyte", "ASRock", "Biostar", "Intel", "EVGA", "ECS", "Foxconn", "DFI", "AOpen", "Abit", "Epox", "Shuttle", "Supermicro", "Tyan"),
    "ram": ("Kingston", "Corsair", "G.Skill", "Crucial", "ADATA", "Patriot", "TeamGroup", "GeIL", "Mushkin", "OCZ", "Apacer", "Transcend", "Samsung", "Hynix", "Micron", "Elpida", "Nanya"),
    "hdd": ("Western Digital", "Seagate", "Toshiba", "Hitachi", "IBM", "Fujitsu", "Maxtor", "Quantum"),
    "ssd": ("Samsung", "Kingston", "Crucial", "Western Digital", "SanDisk", "Seagate", "Toshiba", "Kioxia", "Intel", "Micron", "OCZ", "ADATA", "Corsair", "Patriot", "TeamGroup", "Transcend", "Silicon Power", "Plextor", "Apacer", "PNY", "Solidigm"),
    "gpu": ("ASUS", "MSI", "Gigabyte", "ASRock", "Sapphire", "PowerColor", "XFX", "Zotac", "PNY", "Palit", "Gainward", "Inno3D", "EVGA", "Leadtek", "Manli", "KFA2", "Acer", "HIS", "Club 3D", "Sparkle", "BFG", "VisionTek"),
    "psu": ("Seasonic", "Corsair", "EVGA", "be quiet!", "Cooler Master", "Thermaltake", "FSP", "Super Flower", "Antec", "SilverStone"),
    "cpu_cooler": ("Noctua", "DeepCool", "be quiet!", "Cooler Master", "Arctic", "Thermalright", "Corsair", "NZXT", "Thermaltake"),
    "case_fan": ("Noctua", "Arctic", "be quiet!", "Corsair", "Cooler Master", "DeepCool", "Thermaltake", "Lian Li"),
    "case": ("Fractal Design", "Corsair", "NZXT", "be quiet!", "Cooler Master", "Thermaltake", "Lian Li", "Phanteks", "Antec", "SilverStone"),
}

SOCKET_OPTIONS = {
    "LGA775": "Intel LGA 775", "LGA771": "Intel LGA 771", "LGA1156": "Intel LGA 1156",
    "LGA1155": "Intel LGA 1155", "LGA1150": "Intel LGA 1150", "LGA1151": "Intel LGA 1151",
    "LGA1200": "Intel LGA 1200", "LGA1700": "Intel LGA 1700", "LGA1851": "Intel LGA 1851",
    "Socket 754": "AMD Socket 754", "Socket 939": "AMD Socket 939", "AM2": "AMD AM2",
    "AM2+": "AMD AM2+", "AM3": "AMD AM3", "AM3+": "AMD AM3+", "FM1": "AMD FM1",
    "FM2": "AMD FM2", "FM2+": "AMD FM2+", "AM4": "AMD AM4", "AM5": "AMD AM5",
    "TR4": "AMD TR4", "sTRX4": "AMD sTRX4", "sWRX8": "AMD sWRX8",
}

INITIAL_SPEC_OPTIONS = {
    "motherboard": {
        "form_factor": {"atx": "ATX", "micro_atx": "Micro-ATX", "mini_itx": "Mini-ITX", "extended_atx": "Extended ATX", "mini_dtx": "Mini-DTX", "dtx": "DTX", "ssi_eeb": "SSI-EEB"},
        "ram_type": {value: value.upper() for value in ("ddr", "ddr2", "ddr3", "ddr3l", "ddr4", "ddr5")},
        "pcie_version": {f"{v}.0": f"PCIe {v}.0" for v in range(1, 7)},
        "socket": SOCKET_OPTIONS,
    },
    "ram": {
        "ram_type": {value: value.upper() for value in ("ddr", "ddr2", "ddr3", "ddr3l", "ddr4", "ddr5")},
        "form_factor": {"dimm": "DIMM", "so_dimm": "SO-DIMM", "micro_dimm": "Micro-DIMM", "udimm": "UDIMM", "rdimm": "RDIMM", "lrdimm": "LRDIMM"},
    },
    "gpu": {
        "vram_type": {value: value.upper() for value in ("gddr3", "gddr5", "gddr5x", "gddr6", "gddr6x", "gddr7", "hbm", "hbm2", "hbm2e", "hbm3", "hbm3e")},
        "power_connectors": {"pcie_6pin": "PCIe 6 pin", "pcie_8pin": "PCIe 8 pin", "12vhpwr": "12VHPWR", "12v_2x6": "12V-2x6"},
        "chip_manufacturer": {"NVIDIA": "NVIDIA", "AMD": "AMD", "Intel": "Intel"},
    },
    "psu": {
        "modularity": {"modular": "Полностью модульный", "semi_modular": "Полумодульный", "non_modular": "Немодульный"},
        "form_factor": {"atx": "ATX", "sfx": "SFX", "sfx_l": "SFX-L", "tfx": "TFX", "flex_atx": "Flex ATX", "1u": "1U", "2u": "2U", "proprietary": "Проприетарный"},
        "efficiency_rating": {"80_plus": "80 PLUS", "80_plus_bronze": "80 PLUS Bronze", "80_plus_silver": "80 PLUS Silver", "80_plus_gold": "80 PLUS Gold", "80_plus_platinum": "80 PLUS Platinum", "80_plus_titanium": "80 PLUS Titanium"},
    },
    "ssd": {
        "form_factor": {"2_5_in": "2,5″", "m2": "M.2"},
        "interface_type": {"sata": "SATA", "pcie": "PCIe"},
        "protocol": {"nvme": "NVMe"},
        "pcie_version": {f"{v}.0": f"PCIe {v}.0" for v in range(1, 7)},
    },
    "hdd": {
        "form_factor": {"2_5_in": "2,5 дюйма", "3_5_in": "3,5 дюйма"},
        "interface_type": {"sata": "SATA", "sas": "SAS", "ide": "IDE"},
    },
    "cpu": {"socket": SOCKET_OPTIONS, "ram_type": {value: value.upper() for value in ("ddr", "ddr2", "ddr3", "ddr3l", "ddr4", "ddr5")}, "pcie_version": {f"{v}.0": f"PCIe {v}.0" for v in range(1, 7)}},
    "cpu_cooler": {"socket": SOCKET_OPTIONS},
    "case_fan": {
        "connector_type": {"3_pin": "3 pin", "4_pin_pwm": "4 pin PWM", "molex_4pin": "Molex 4 pin", "sata_power": "Питание SATA", "proprietary": "Проприетарный", "other": "Другой"},
    },
    "case": {
        "form_factors_supported": {"atx": "ATX", "micro_atx": "Micro-ATX", "mini_itx": "Mini-ITX", "extended_atx": "Extended ATX", "mini_dtx": "Mini-DTX", "dtx": "DTX", "ssi_eeb": "SSI-EEB"},
    },
}

