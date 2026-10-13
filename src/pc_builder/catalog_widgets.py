"""Экраны и формы каталога комплектующих."""

from pathlib import Path
from typing import Callable
from collections import Counter

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QRect, QSize, Qt, Signal
from PySide6.QtGui import QImage, QImageReader, QPainter
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QGridLayout, QHBoxLayout, QLabel,
    QLineEdit, QMenu, QMessageBox, QPushButton, QScrollArea, QTableWidget,
    QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget,
)

from .catalog import (
    COMPONENT_TYPE_LABELS, duplicate_component, list_archived_components,
    list_owned_models,
)
from .database import (
    DatabaseError, VALID_COMPONENT_TYPES, archive_component, create_component,
    delete_component, get_component, restore_component, update_component,
    list_manufacturer_options, add_manufacturer_option, delete_manufacturer_option,
)
from .characteristics_widgets import (
    CustomAttributesEditor,
    SPEC_FIELDS,
    SpecificationsEditor,
)
from .database import get_custom_attributes
from .database import get_component_image, save_component_image, delete_component_image
from .specifications import get_component_spec, list_specification_options


class _CatalogTableArea(QWidget):
    """Область таблицы с закреплённой поверх неё кнопкой добавления."""

    def __init__(self, table: QTableWidget, button: QPushButton, parent=None):
        super().__init__(parent)
        self.table = table
        self.button = button
        table.setParent(self)
        button.setParent(self)
        table.setViewportMargins(0, 0, 0, 62)

    def resizeEvent(self, event) -> None:
        self.table.setGeometry(self.rect())
        self.button.adjustSize()
        self.button.move(max(8, self.width() - self.button.width() - 18),
                         max(8, self.height() - self.button.height() - 14))
        self.button.raise_()
        super().resizeEvent(event)


def _display_date(value: str | None) -> str:
    return value.replace("T", " ").removesuffix("Z") if value else "—"


def _label(text: str) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    return label


def _message(parent, icon: QMessageBox.Icon, title: str, text: str, button: str = "Понятно") -> None:
    dialog = QMessageBox(icon, title, text, QMessageBox.StandardButton.NoButton, parent)
    dialog.addButton(button, QMessageBox.ButtonRole.AcceptRole)
    dialog.exec()


def confirm_delete(parent, component_name: str) -> bool:
    """Спрашивает подтверждение перед необратимым удалением."""
    answer = QMessageBox.question(
        parent,
        "Удалить комплектующее навсегда?",
        f"Удалить «{component_name}» навсегда? Это действие необратимо.",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    return answer == QMessageBox.StandardButton.Yes


def _prepare_component_image(path: str) -> tuple[bytes, str, str]:
    """Проверяет файл декодером Qt, ограничивает размер и подготавливает превью-БЛОБ."""
    source = Path(path)
    if source.stat().st_size > 20 * 1024 * 1024:
        raise ValueError("Исходный файл больше 20 МБ.")
    reader = QImageReader(str(source))
    reader.setAutoTransform(True)
    image_size = reader.size()
    if not reader.canRead():
        raise ValueError("Файл не является корректным поддерживаемым изображением.")
    image_format = bytes(reader.format()).lower()
    if image_format not in {b"jpg", b"jpeg", b"png", b"webp"}:
        raise ValueError("Поддерживаются только JPG, JPEG, PNG и WebP.")
    if image_size.isValid() and (
        image_size.width() > 30000 or image_size.height() > 30000
        or image_size.width() * image_size.height() > 100_000_000
    ):
        raise ValueError("Разрешение изображения слишком велико для безопасной обработки.")
    image = reader.read()
    if image.isNull():
        raise ValueError("Не удалось прочитать изображение.")
    if image.width() > 1600 or image.height() > 1600:
        image = image.scaled(
            QSize(1600, 1600), Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
    output = QByteArray()
    buffer = QBuffer(output)
    if not buffer.open(QIODevice.OpenModeFlag.WriteOnly):
        raise ValueError("Не удалось подготовить изображение для базы данных.")
    if image.hasAlphaChannel():
        image_format, mime_type = "PNG", "image/png"
    else:
        image_format, mime_type = "JPEG", "image/jpeg"
    if not image.save(buffer, image_format, 88 if image_format == "JPEG" else -1):
        raise ValueError("Не удалось перекодировать изображение.")
    return bytes(output), mime_type, source.name


class _ComponentImagePreview(QLabel):
    """Однократно декодирует BLOB и рисует QImage вписанным в область виджета."""

    EMPTY_TEXT = "Фотография комплектующего\nне добавлена"

    def __init__(self, parent=None):
        super().__init__(self.EMPTY_TEXT, parent)
        self._image: QImage | None = None
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setWordWrap(True)
        self.setMinimumSize(180, 150)
        self.setMaximumWidth(260)
        self.setStyleSheet("border: 1px dashed #777; color: #aaa; padding: 12px;")

    def set_image_data(self, data: bytes | None) -> None:
        self._image = None
        if data:
            # QBuffer хранит ссылку на переданный QByteArray, поэтому буфер
            # должен иметь отдельную Python-ссылку до завершения чтения.
            image_buffer = QByteArray(data)
            buffer = QBuffer(image_buffer)
            if buffer.open(QIODevice.OpenModeFlag.ReadOnly):
                reader = QImageReader(buffer)
                reader.setAutoTransform(True)
                decoded = reader.read()
                if not decoded.isNull():
                    # copy() отсоединяет изображение от буфера/декодера Qt.
                    self._image = decoded.copy()
        self.setText(self.EMPTY_TEXT if not data else ("Не удалось прочитать изображение" if self._image is None else ""))
        self.update()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if self._image is None:
            return
        area = self.contentsRect()
        target_size = self._image.size().scaled(area.size(), Qt.AspectRatioMode.KeepAspectRatio)
        x = area.x() + (area.width() - target_size.width()) // 2
        y = area.y() + (area.height() - target_size.height()) // 2
        target = QRect(x, y, target_size.width(), target_size.height())
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.drawImage(target, self._image)


class ComponentTypeDialog(QDialog):
    """Обязательный короткий шаг выбора категории перед созданием карточки."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Выбор типа комплектующего")
        self.setMinimumWidth(360)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Выберите тип комплектующего:"))
        self.type_combo = QComboBox()
        self.type_combo.addItem("Выберите тип…", None)
        for component_type, label in sorted(COMPONENT_TYPE_LABELS.items(), key=lambda pair: pair[1]):
            self.type_combo.addItem(label, component_type)
        self.type_combo.setCurrentIndex(0)
        layout.addWidget(self.type_combo)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Продолжить")
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Отмена")
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        self.type_combo.currentIndexChanged.connect(
            lambda _index: self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(
                self.type_combo.currentData() is not None
            )
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    @property
    def selected_type(self) -> str | None:
        return self.type_combo.currentData()


class ModelFormDialog(QDialog):
    """Форма создания или изменения комплектующего."""

    def __init__(self, database_path: Path | str | None = None, model: dict | None = None, parent=None):
        super().__init__(parent)
        self.database_path = database_path
        self.model = model
        self.model_id: int | None = None
        self.setWindowTitle("Редактирование комплектующего" if model else "Добавление комплектующего")
        self.resize(460, 560)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.type_combo = QComboBox()
        for component_type in sorted(VALID_COMPONENT_TYPES, key=lambda key: COMPONENT_TYPE_LABELS[key]):
            self.type_combo.addItem(COMPONENT_TYPE_LABELS[component_type], component_type)
        self.manufacturer_input = QComboBox()
        self.manufacturer_input.setEditable(True)
        self.manufacturer_input.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.manufacturer_input.setCurrentIndex(-1)
        self.manufacturer_input.setEditText("")
        self.manufacturer_input.setPlaceholderText("Введите или выберите производителя")
        manufacturer_row = QHBoxLayout()
        manufacturer_row.addWidget(self.manufacturer_input, 1)
        self.add_manufacturer_button = QPushButton("Добавить в список")
        self.remove_manufacturer_button = QPushButton("Удалить из списка")
        self.add_manufacturer_button.clicked.connect(self._add_manufacturer)
        self.remove_manufacturer_button.clicked.connect(self._remove_manufacturer)
        manufacturer_row.addWidget(self.add_manufacturer_button)
        manufacturer_row.addWidget(self.remove_manufacturer_button)
        self.model_name_input = QLineEdit()
        self.notes_input = QTextEdit()
        self.notes_input.setMaximumHeight(90)
        form.addRow("Тип комплектующего:", self.type_combo)
        form.addRow("Производитель:", manufacturer_row)
        self.type_combo.currentIndexChanged.connect(self._refresh_manufacturers)
        self._refresh_manufacturers()
        form.addRow("Название модели:", self.model_name_input)
        form.addRow("Заметки:", self.notes_input)
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Сохранить")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Отмена")
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        if model:
            index = self.type_combo.findData(model["component_type"])
            if index >= 0:
                self.type_combo.setCurrentIndex(index)
            index = self.manufacturer_input.findText(model["manufacturer"])
            if index >= 0:
                self.manufacturer_input.setCurrentIndex(index)
            else:
                self.manufacturer_input.setEditText(model["manufacturer"])
            self.model_name_input.setText(model["model_name"])
            self.notes_input.setPlainText(model["notes"] or "")

    def _refresh_manufacturers(self, *_args) -> None:
        kind = self.type_combo.currentData()
        current = self.manufacturer_input.currentText()
        try:
            values = list_manufacturer_options(kind, self.database_path)
        except DatabaseError:
            values = []
        self.manufacturer_input.blockSignals(True)
        self.manufacturer_input.clear()
        self.manufacturer_input.addItems(values)
        self.manufacturer_input.setCurrentIndex(-1)
        self.manufacturer_input.setEditText(current)
        self.manufacturer_input.blockSignals(False)

    def _add_manufacturer(self) -> None:
        value = self.manufacturer_input.currentText().strip()
        if not value:
            _message(self, QMessageBox.Icon.Information, "Пустое значение", "Введите название производителя.")
            return
        try:
            add_manufacturer_option(self.type_combo.currentData(), value, self.database_path)
        except DatabaseError as error:
            _message(self, QMessageBox.Icon.Warning, "Не удалось добавить производителя", str(error))
            return
        self.manufacturer_input.setEditText(value)
        self._refresh_manufacturers()
        self.manufacturer_input.setEditText(value)

    def _remove_manufacturer(self) -> None:
        value = self.manufacturer_input.currentText().strip()
        if not value:
            return
        try:
            delete_manufacturer_option(self.type_combo.currentData(), value, self.database_path)
        except DatabaseError as error:
            _message(self, QMessageBox.Icon.Warning, "Не удалось удалить производителя", str(error))
            return
        self._refresh_manufacturers()

    def _save(self) -> None:
        manufacturer = self.manufacturer_input.currentText().strip()
        model_name = self.model_name_input.text().strip()
        if not manufacturer or not model_name:
            _message(self, QMessageBox.Icon.Warning, "Не заполнены обязательные поля", "Укажите производителя и название модели.", "Закрыть")
            return
        fields = {
            "manufacturer": manufacturer,
            "model_name": model_name,
            "part_number": self.model.get("part_number") if self.model else None,
            "description": self.model.get("description") if self.model else None,
            "notes": self.notes_input.toPlainText().strip() or None,
        }
        try:
            known = list_manufacturer_options(self.type_combo.currentData(), self.database_path)
            if manufacturer.casefold() not in {value.casefold() for value in known}:
                add_manufacturer_option(self.type_combo.currentData(), manufacturer, self.database_path)
            if self.model:
                self.model_id = self.model["id"]
                update_component(
                    self.model_id, database_path=self.database_path,
                    component_type=self.type_combo.currentData(),
                    **fields,
                )
            else:
                self.model_id = create_component(
                    self.type_combo.currentData(), manufacturer, model_name,
                    part_number=fields["part_number"], description=fields["description"],
                    notes=fields["notes"], database_path=self.database_path,
                )
        except DatabaseError as error:
            _message(self, QMessageBox.Icon.Warning, "Не удалось сохранить комплектующее", str(error), "Закрыть")
            return
        self.accept()


class _LegacyModelCardDialog(QDialog):
    """Единая прокручиваемая карточка со спецификацией комплектующего."""

    SPECIFICATION_GROUPS = {
        "cpu": [
            ("Платформа и память", ("socket", "ram_type", "pcie_version")),
            ("Ядра и потоки", ("cores", "threads")),
            ("Частоты", ("base_clock_mhz", "boost_clock_mhz")),
            ("Тепловые характеристики", ("tdp_w",)),
            ("Графическое ядро", ("has_integrated_gpu",)),
        ],
        "motherboard": [
            ("Платформа", ("socket", "chipset", "form_factor")),
            ("Оперативная память", ("supported_ram_types", "ram_slots", "max_ram_gb", "max_ram_clock_mhz")),
            ("Накопители", ("m2_slots", "sata_ports")),
            ("Шина расширения", ("pcie_version",)),
        ],
        "ram": [("Характеристики памяти", ("ram_type", "capacity_gb", "frequency_mhz", "form_factor", "ecc"))],
        "gpu": [
            ("Графический чип", ("chip_manufacturer", "vram_type", "cooling_type")),
            ("Видеопамять", ("vram_gb",)),
            ("Размеры карты", ("length_mm", "thickness_mm", "slot_width")),
            ("Питание", ("power_w", "recommended_psu_w", "power_connectors")),
        ],
        "psu": [
            ("Мощность и эффективность", ("rated_power_w", "efficiency_rating")),
            ("Форм-фактор и модульность", ("form_factor", "modularity")),
            ("Разъёмы", ("pcie_6_2pin_count", "eps_4_4pin_count", "native_12vhpwr", "native_12v2x6", "sata_power_count")),
        ],
        "ssd": [("Характеристики накопителя", ("capacity_gb", "form_factor", "interface_type", "protocol", "pcie_version", "power_w"))],
        "hdd": [("Характеристики накопителя", ("capacity_gb", "form_factor", "interface_type", "power_w"))],
        "cpu_cooler": [
            ("Совместимость", ("supported_sockets",)),
            ("Размеры и питание", ("height_mm", "power_w")),
        ],
        "case_fan": [("Характеристики вентилятора", ("size_mm", "thickness_mm", "connector_type", "lighting", "power_w", "max_rpm"))],
        "case": [
            ("Поддерживаемые компоненты", ("form_factors_supported", "max_gpu_length_mm", "max_cpu_cooler_height_mm", "max_psu_length_mm")),
            ("Места для накопителей", ("drive_2_5_bays", "drive_3_5_bays")),
            ("Поддержка радиаторов", ("radiator_support",)),
        ],
    }

    def __init__(
        self, model_id: int, database_path: Path | str | None = None,
        parent=None, changed: Callable[[], None] | None = None,
    ):
        super().__init__(parent)
        self.model_id = model_id
        self.database_path = database_path
        self.changed = changed
        self.resize(900, 560)
        self.setMinimumSize(650, 360)
        self.root_layout = QVBoxLayout(self)
        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(18, 12, 18, 12)
        self.content_layout.setSpacing(10)
        self.scroll.setWidget(self.content)
        self.root_layout.addWidget(self.scroll, 1)
        self._reload()

    @staticmethod
    def _plain_value(value) -> bool:
        return value is not None and not (isinstance(value, str) and not value.strip())

    def _spec_value(self, component_type: str, field: str, value, kind: str, extra) -> str | None:
        if isinstance(value, (list, dict)) and not value:
            return None
        if not self._plain_value(value):
            return None
        if kind == "bool":
            return "Да" if value else "Нет"
        if field in {"capacity_gb", "vram_gb"}:
            if value < 1:
                return f"{value * 1024:g} МБ"
            return f"{value:g} ГБ"
        if kind == "enum" or kind == "choice_text":
            options = {option["value"]: option["display_value"] for option in
                       list_specification_options(component_type, field, self.database_path)}
            return options.get(value, (extra or {}).get(value, value))
        if kind in {"strings", "form_factors", "radiators", "ram_types"}:
            if kind == "radiators":
                return ", ".join(f"{item} мм" for item in value)
            option_field = "socket" if field == "supported_sockets" else (
                "ram_type" if field == "supported_ram_types" else field
            )
            options = {option["value"]: option["display_value"] for option in
                       list_specification_options(component_type, option_field, self.database_path)}
            return ", ".join(options.get(item, item) for item in value)
        if kind == "connectors":
            labels = {
                "pcie_6pin": "PCIe 6 pin", "pcie_8pin": "PCIe 8 pin",
                "12vhpwr": "12VHPWR", "12v_2x6": "12V-2x6",
            }
            return ", ".join(f"{labels.get(key, key)} — {count} шт." for key, count in value.items())
        if kind in {"int", "number"}:
            suffix = f" {extra}" if extra else ""
            return f"{value:g}{suffix}" if isinstance(value, float) else f"{value}{suffix}"
        return str(value)

    def _section_title(self, title: str) -> None:
        label = QLabel(title)
        label.setStyleSheet("font-size: 15px; font-weight: 600; margin-top: 5px;")
        self.content_layout.addWidget(label)

    def _add_rows(self, entries: list[tuple[str, str]]) -> None:
        if not entries:
            return
        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(5)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 2)
        for row, (name, value) in enumerate(entries):
            key = QLabel(name)
            key.setWordWrap(True)
            val = QLabel(value)
            val.setWordWrap(True)
            val.setTextFormat(Qt.TextFormat.PlainText)
            grid.addWidget(key, row, 0, Qt.AlignmentFlag.AlignTop)
            grid.addWidget(val, row, 1, Qt.AlignmentFlag.AlignTop)
        self.content_layout.addLayout(grid)

    def _render(self, model: dict) -> None:
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
            elif item.layout() is not None:
                item.layout().deleteLater()

        name = QLabel(model["model_name"])
        name.setWordWrap(True)
        name.setStyleSheet("font-size: 23px; font-weight: 700;")
        self.content_layout.addWidget(name)
        edit_button = QPushButton("Редактировать комплектующее")
        edit_button.setMaximumWidth(260)
        edit_button.clicked.connect(self._edit_component)
        self.content_layout.addWidget(edit_button)
        category = COMPONENT_TYPE_LABELS.get(model["component_type"], "Комплектующее")
        details = [category]
        if model["manufacturer"]:
            details.append(model["manufacturer"])
        metadata = QLabel(" · ".join(details))
        metadata.setWordWrap(True)
        self.content_layout.addWidget(metadata)
        self.content_layout.addWidget(QLabel("Статус: " + ("В наличии" if model["status"] == "owned" else "В архиве")))
        if model["part_number"]:
            self._add_rows([("Артикул", model["part_number"])])

        spec = get_component_spec(self.model_id, self.database_path) or {}
        fields = {field[0]: field for field in SPEC_FIELDS[model["component_type"]]}
        for section, keys in self.SPECIFICATION_GROUPS[model["component_type"]]:
            rows = []
            for key in keys:
                value = spec.get(key)
                if not self._plain_value(value) or isinstance(value, (list, dict)) and not value:
                    continue
                _field, label, kind, extra = fields[key]
                display = self._spec_value(model["component_type"], key, value, kind, extra)
                if display is not None:
                    rows.append((label, display))
            if rows:
                self._section_title(section)
                self._add_rows(rows)

        attributes = get_custom_attributes(self.model_id, self.database_path)
        rows = []
        for attribute in attributes:
            column = {"text": "value_text", "number": "value_number", "boolean": "value_boolean", "enum": "value_enum"}[attribute["value_type"]]
            value = attribute[column]
            if attribute["value_type"] == "boolean" and value is not None:
                value = "Да" if value else "Нет"
            if value is None or isinstance(value, str) and not value.strip():
                continue
            suffix = f" {attribute['unit']}" if attribute["unit"] else ""
            rows.append((attribute["name"], f"{value}{suffix}"))
        if rows:
            self._section_title("Пользовательские характеристики")
            self._add_rows(rows)

        info = []
        if model["description"]:
            info.append(("Описание", model["description"]))
        if model["notes"]:
            info.append(("Заметки", model["notes"]))
        if info:
            self._section_title("Дополнительные сведения")
            self._add_rows(info)

        edit_characteristics = QPushButton("Редактировать характеристики")
        edit_characteristics.clicked.connect(self._edit_characteristics)
        self.content_layout.addWidget(edit_characteristics)
        content_height = self.content_layout.sizeHint().height()
        self.resize(900, min(720, max(380, content_height + 75)))

    def _edit_characteristics(self) -> None:
        model = get_component(self.model_id, self.database_path)
        if model is None:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Редактирование характеристик")
        dialog.resize(820, 720)
        dialog.setMinimumSize(650, 500)
        layout = QVBoxLayout(dialog)
        scroll = QScrollArea(dialog)
        scroll.setWidgetResizable(True)
        body = QWidget()
        body_layout = QVBoxLayout(body)
        spec_title = QLabel("Стандартные характеристики")
        spec_title.setStyleSheet("font-size: 16px; font-weight: 600;")
        body_layout.addWidget(spec_title)
        spec_editor = SpecificationsEditor(self.model_id, model["component_type"], self.database_path, body)
        body_layout.addWidget(spec_editor)
        custom_title = QLabel("Пользовательские характеристики")
        custom_title.setStyleSheet("font-size: 16px; font-weight: 600; margin-top: 8px;")
        body_layout.addWidget(custom_title)
        custom_editor = CustomAttributesEditor(self.model_id, model["component_type"], self.database_path, body)
        body_layout.addWidget(custom_editor)
        scroll.setWidget(body)
        layout.addWidget(scroll, 1)
        close = QPushButton("Закрыть")
        close.clicked.connect(dialog.accept)
        layout.addWidget(close)
        dialog.exec()
        self._reload()

    def _reload(self) -> None:
        model = get_component(self.model_id, self.database_path)
        if model is None:
            _message(self, QMessageBox.Icon.Warning, "Комплектующее не найдено", "Эта запись больше недоступна.", "Закрыть")
            self.reject()
            return
        self.setWindowTitle("Комплектующее — " + model["model_name"])
        self._render(model)

    def _edit_component(self) -> None:
        model = get_component(self.model_id, self.database_path)
        if model is None:
            return
        dialog = ModelFormDialog(self.database_path, model, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._reload()
            if self.changed:
                self.changed()


class _NotesEdit(QTextEdit):
    editingFinished = Signal()

    def focusOutEvent(self, event) -> None:
        super().focusOutEvent(event)
        self.editingFinished.emit()


class ModelCardDialog(QDialog):
    """Основная карточка: общие сведения и характеристики на одной странице."""

    def __init__(
        self, model_id: int | None, database_path: Path | str | None = None,
        parent=None, changed: Callable[[], None] | None = None, *, draft_type: str | None = None,
    ):
        super().__init__(parent)
        self.model_id = model_id
        self.database_path = database_path
        self.changed = changed or (lambda: None)
        self._loading = True
        self._draft = model_id is None
        self._pending_image: tuple[bytes, str, str] | None = None
        self.model = get_component(model_id, database_path) if model_id is not None else None
        self.component_type = (self.model or {}).get("component_type", draft_type)
        if self.component_type not in VALID_COMPONENT_TYPES:
            raise ValueError("Для новой карточки необходимо явно передать выбранный тип комплектующего.")
        self.setWindowTitle("Новое комплектующее" if self._draft else "Комплектующее")
        self.resize(1040, 820)
        self.setMinimumSize(700, 520)

        root = QVBoxLayout(self)
        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.body = QWidget()
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(18, 14, 18, 18)
        self.body_layout.setSpacing(12)
        self.scroll.setWidget(self.body)
        root.addWidget(self.scroll, 1)

        top = QHBoxLayout()
        photo_area = QWidget()
        photo_layout = QVBoxLayout(photo_area)
        photo_layout.setContentsMargins(0, 0, 0, 0)
        self.photo_placeholder = _ComponentImagePreview()
        photo_layout.addWidget(self.photo_placeholder, 1)
        photo_buttons = QHBoxLayout()
        self.image_add_button = QPushButton("Добавить изображение")
        self.image_delete_button = QPushButton("Удалить")
        self.image_add_button.clicked.connect(self._choose_component_image)
        self.image_delete_button.clicked.connect(self._remove_component_image)
        photo_buttons.addWidget(self.image_add_button)
        photo_buttons.addWidget(self.image_delete_button)
        photo_layout.addLayout(photo_buttons)
        top.addWidget(photo_area, 1)

        details = QVBoxLayout()
        self.type_combo = QComboBox()
        for component_type, label in sorted(COMPONENT_TYPE_LABELS.items(), key=lambda pair: pair[1]):
            self.type_combo.addItem(label, component_type)
        selected_type_index = self.type_combo.findData(self.component_type)
        if selected_type_index < 0:
            raise ValueError(f"Неизвестный тип комплектующего: {self.component_type!r}.")
        self.type_combo.setCurrentIndex(selected_type_index)
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Название комплектующего")
        self.manufacturer_input = QComboBox()
        self.manufacturer_input.setEditable(True)
        self.manufacturer_input.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.manufacturer_input.setPlaceholderText("Выберите или введите производителя")
        self.status_label = QLabel()
        details.addWidget(QLabel("Тип комплектующего"))
        details.addWidget(self.type_combo)
        details.addWidget(QLabel("Название"))
        details.addWidget(self.name_input)
        details.addWidget(QLabel("Производитель"))
        details.addWidget(self.manufacturer_input)
        if self.model:
            self.type_combo.setCurrentIndex(max(0, self.type_combo.findData(self.component_type)))
            self.type_combo.setEnabled(False)
            self.status_label.setText("Статус: " + ("В наличии" if self.model["status"] == "owned" else "В архиве"))
        self.status_label.setVisible(self.model is not None)
        details.addWidget(self.status_label)
        top.addLayout(details, 2)
        self.body_layout.addLayout(top)

        notes_title = QLabel("Заметки")
        notes_title.setStyleSheet("font-weight: 600;")
        self.body_layout.addWidget(notes_title)
        self.notes_input = _NotesEdit()
        self.notes_input.setPlaceholderText("Дополнительные заметки")
        self.notes_input.setMaximumHeight(90)
        self.body_layout.addWidget(self.notes_input)
        self.form_status = QLabel()
        self.form_status.setWordWrap(True)
        self.body_layout.addWidget(self.form_status)

        self.spec_title = QLabel("Характеристики")
        self.spec_title.setStyleSheet("font-size: 17px; font-weight: 600;")
        self.body_layout.addWidget(self.spec_title)
        self.spec_editor = SpecificationsEditor(
            self.model_id, self.component_type, self.database_path, self.body, auto_save=True,
        )
        self.body_layout.addWidget(self.spec_editor)

        self.custom_title = QLabel("Пользовательские характеристики")
        self.custom_title.setStyleSheet("font-size: 16px; font-weight: 600;")
        self.body_layout.addWidget(self.custom_title)
        self.custom_host = QWidget()
        self.custom_layout = QVBoxLayout(self.custom_host)
        self.custom_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.addWidget(self.custom_host)
        self.custom_editor: CustomAttributesEditor | None = None
        if self.model:
            self._show_custom_editor()
        else:
            hint = QLabel(
                "Сохраните комплектующее, чтобы редактировать значения характеристик, "
                "определённых для его категории. Определения настраиваются в отдельном разделе."
            )
            hint.setWordWrap(True)
            self.custom_layout.addWidget(hint)

        self.create_button = QPushButton("Сохранить комплектующее")
        self.create_button.setVisible(self._draft)
        self.create_button.clicked.connect(self._create_draft)
        root.addWidget(self.create_button)
        close = QPushButton("Закрыть")
        close.clicked.connect(self.accept)
        root.addWidget(close)

        if self.model:
            self.name_input.setText(self.model["model_name"])
            self.notes_input.setPlainText(self.model["notes"] or "")
        index = self.manufacturer_input.findText((self.model or {}).get("manufacturer", ""))
        try:
            manufacturers = list_manufacturer_options(self.component_type, self.database_path)
        except DatabaseError:
            manufacturers = []
        self.manufacturer_input.addItems([value for value in manufacturers if self.manufacturer_input.findText(value) < 0])
        if self.model:
            if index >= 0:
                self.manufacturer_input.setCurrentIndex(index)
            else:
                self.manufacturer_input.setEditText(self.model["manufacturer"])

        self.name_input.editingFinished.connect(lambda: self._save_component_field("model_name", self.name_input.text().strip() or None, self.name_input))
        self.manufacturer_input.activated.connect(lambda _i: self._save_component_field("manufacturer", self.manufacturer_input.currentText().strip() or None, self.manufacturer_input))
        if self.manufacturer_input.lineEdit():
            self.manufacturer_input.lineEdit().editingFinished.connect(lambda: self._save_component_field("manufacturer", self.manufacturer_input.currentText().strip() or None, self.manufacturer_input))
        self.notes_input.editingFinished.connect(lambda: self._save_component_field("notes", self.notes_input.toPlainText().strip() or None, self.notes_input))
        self.type_combo.currentIndexChanged.connect(self._draft_type_changed)
        self.image_delete_button.setEnabled(False)
        if self.model_id is not None:
            self._load_component_image()
        self._loading = False

    def _load_component_image(self) -> None:
        try:
            stored = get_component_image(self.model_id, self.database_path)
        except DatabaseError as error:
            self.form_status.setText(f"Не удалось загрузить изображение: {error}")
            return
        self.photo_placeholder.set_image_data(stored["image_data"] if stored else None)
        self.image_delete_button.setEnabled(stored is not None)
        self.image_add_button.setText("Заменить изображение" if stored else "Добавить изображение")

    def _choose_component_image(self) -> None:
        path, _selected_filter = QFileDialog.getOpenFileName(
            self, "Выберите изображение комплектующего", "",
            "Изображения (*.jpg *.jpeg *.png *.webp)",
        )
        if not path:
            return
        try:
            image_data, mime_type, original_name = _prepare_component_image(path)
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "Не удалось открыть изображение", str(error))
            return
        if self._draft or self.model_id is None:
            self._pending_image = (image_data, mime_type, original_name)
            self.photo_placeholder.set_image_data(image_data)
            self.form_status.setText("Изображение будет сохранено вместе с комплектующим.")
            self.image_delete_button.setEnabled(True)
            return
        try:
            save_component_image(
                self.model_id, image_data, mime_type,
                original_name=original_name, database_path=self.database_path,
            )
        except DatabaseError as error:
            QMessageBox.warning(self, "Не удалось сохранить изображение", str(error))
            return
        self.photo_placeholder.set_image_data(image_data)
        self.image_delete_button.setEnabled(True)
        self.image_add_button.setText("Заменить изображение")
        self.form_status.setText("Изображение сохранено в базе данных.")

    def _remove_component_image(self) -> None:
        if self._draft or self.model_id is None:
            self._pending_image = None
            self.photo_placeholder.set_image_data(None)
            self.image_delete_button.setEnabled(False)
            self.image_add_button.setText("Добавить изображение")
            return
        try:
            delete_component_image(self.model_id, self.database_path)
        except DatabaseError as error:
            QMessageBox.warning(self, "Не удалось удалить изображение", str(error))
            return
        self.photo_placeholder.set_image_data(None)
        self.image_delete_button.setEnabled(False)
        self.image_add_button.setText("Добавить изображение")
        self.form_status.setText("Изображение удалено.")

    def _show_custom_editor(self) -> None:
        if self.model_id is None:
            return
        while self.custom_layout.count():
            item = self.custom_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self.custom_editor = CustomAttributesEditor(self.model_id, self.component_type, self.database_path, self.custom_host)
        self.custom_layout.addWidget(self.custom_editor)

    def _draft_type_changed(self, _index: int) -> None:
        if not self._draft or self._loading:
            return
        new_type = self.type_combo.currentData()
        if new_type not in VALID_COMPONENT_TYPES:
            return
        if new_type == self.component_type:
            return
        self.component_type = new_type
        current_manufacturer = self.manufacturer_input.currentText()
        self.manufacturer_input.blockSignals(True)
        self.manufacturer_input.clear()
        try:
            manufacturers = list_manufacturer_options(new_type, self.database_path)
        except DatabaseError:
            manufacturers = []
        self.manufacturer_input.addItems(manufacturers)
        self.manufacturer_input.setCurrentIndex(-1)
        self.manufacturer_input.setEditText(current_manufacturer)
        self.manufacturer_input.blockSignals(False)
        self.body_layout.removeWidget(self.spec_editor)
        self.spec_editor.hide()
        self.spec_editor.setParent(None)
        self.spec_editor.deleteLater()
        self.spec_editor = SpecificationsEditor(None, self.component_type, self.database_path, self.body, auto_save=True)
        self.body_layout.insertWidget(self.body_layout.indexOf(self.custom_title), self.spec_editor)

    def _save_component_field(self, field: str, value, control: QWidget) -> bool:
        if self._loading or self._draft or self.model_id is None:
            return False
        if field == "model_name" and not value:
            control.setStyleSheet("border: 1px solid #d9534f;")
            control.setToolTip("Название обязательно.")
            self.form_status.setText("Название комплектующего не может быть пустым.")
            return False
        try:
            update_component(self.model_id, database_path=self.database_path, **{field: value})
        except DatabaseError as error:
            control.setStyleSheet("border: 1px solid #d9534f;")
            control.setToolTip(str(error))
            self.form_status.setText(f"Не удалось сохранить поле «{field}»: {error}")
            return False
        control.setStyleSheet("")
        control.setToolTip("")
        self.form_status.setText("Изменение сохранено.")
        self.setWindowTitle("Комплектующее — " + (value if field == "model_name" else self.name_input.text()))
        self.changed()
        return True

    def _create_draft(self) -> None:
        manufacturer = self.manufacturer_input.currentText().strip()
        model_name = self.name_input.text().strip()
        if not manufacturer or not model_name:
            self.form_status.setText("Укажите производителя и название комплектующего.")
            return
        try:
            self.model_id = create_component(
                self.component_type, manufacturer, model_name,
                notes=self.notes_input.toPlainText().strip() or None,
                database_path=self.database_path,
            )
        except DatabaseError as error:
            self.form_status.setText(f"Не удалось создать комплектующее: {error}")
            return
        self._draft = False
        self.model = get_component(self.model_id, self.database_path)
        image_save_error = None
        if self._pending_image is not None:
            image_data, mime_type, original_name = self._pending_image
            try:
                save_component_image(
                    self.model_id, image_data, mime_type,
                    original_name=original_name, database_path=self.database_path,
                )
                self._pending_image = None
                self.form_status.setText("Комплектующее и изображение сохранены.")
            except DatabaseError as error:
                image_save_error = error
        self.spec_editor.bind_model(self.model_id)
        self.spec_editor.save_pending()
        self.create_button.hide()
        self.type_combo.setEnabled(False)
        self.status_label.setText("Статус: В наличии")
        self.status_label.show()
        self._show_custom_editor()
        self.form_status.setText(
            f"Комплектующее создано, но изображение не сохранено: {image_save_error}. "
            "Выберите изображение повторно."
            if image_save_error else "Комплектующее создано. Изменения полей сохраняются отдельно."
        )
        if self._pending_image is None:
            self.image_add_button.setText("Заменить изображение" if self.photo_placeholder._image is not None else "Добавить изображение")
        self.setWindowTitle("Комплектующее — " + model_name)
        self.changed()


class CatalogPage(QWidget):
    """Список активных комплектующих."""

    def __init__(self, database_path: Path | str | None = None, status_message: Callable[[str], None] | None = None):
        super().__init__()
        self.database_path = database_path
        self.status_message = status_message or (lambda _message: None)
        layout = QVBoxLayout(self)
        heading = QLabel("Моё железо")
        heading.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(heading)
        controls = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Поиск по названию, производителю или артикулу")
        self.type_filter = QComboBox()
        self.type_filter.addItem("Все типы", None)
        for component_type, label in sorted(COMPONENT_TYPE_LABELS.items(), key=lambda pair: pair[1]):
            self.type_filter.addItem(label, component_type)
        self.sort_order = QComboBox()
        self.sort_order.addItem("Название: А—Я", False)
        self.sort_order.addItem("Название: Я—А", True)
        self.add_model_button = QPushButton("Добавить комплектующее")
        self.search_input.textChanged.connect(self.refresh)
        self.type_filter.currentIndexChanged.connect(self.refresh)
        self.sort_order.currentIndexChanged.connect(self._sort_order_changed)
        self.add_model_button.clicked.connect(self._add_component)
        controls.addWidget(self.search_input, 2)
        controls.addWidget(self.type_filter)
        controls.addWidget(self.sort_order)
        layout.addLayout(controls)
        self.table = self._create_table(["Тип", "Производитель", "Название модели"])
        self._columns: list[dict] = []
        self._header_sort: tuple[dict, bool] | None = None
        self.table.horizontalHeader().sectionClicked.connect(self._sort_by_header)
        self.table.cellDoubleClicked.connect(lambda _row, _column: self._open_selected())
        self.table.customContextMenuRequested.connect(self._context_menu)
        self.table_area = _CatalogTableArea(self.table, self.add_model_button, self)
        layout.addWidget(self.table_area, 1)
        footer = QHBoxLayout()
        self.open_button = QPushButton("Открыть карточку")
        self.open_button.clicked.connect(self._open_selected)
        footer.addWidget(self.open_button)
        footer.addStretch()
        layout.addLayout(footer)
        self.refresh()

    def _sort_order_changed(self, *_args) -> None:
        self._header_sort = None
        self.refresh()

    @staticmethod
    def _populated(value) -> bool:
        return value is not None and value != "" and value != [] and value != {}

    @staticmethod
    def _definitions(component_type: str) -> dict[str, tuple[str, str, object]]:
        definitions = {}
        for key, label, kind, extra in SPEC_FIELDS[component_type]:
            identity = "ram_type" if key == "supported_ram_types" else key
            data_type = "strings" if identity == "ram_type" or kind in {"ram_types", "strings"} else (
                "numeric" if kind == "memory" else kind
            )
            definitions[identity] = (label, data_type, extra)
        return definitions

    @staticmethod
    def _spec_value(spec: dict, component_type: str, field: str):
        if field == "ram_type":
            if component_type == "motherboard":
                return spec.get("supported_ram_types", [spec["ram_type"]] if spec.get("ram_type") else [])
            value = spec.get(field)
            return [value] if value else None
        return spec.get(field)

    @staticmethod
    def _custom_identity(attribute: dict) -> tuple[str, str, str]:
        # У custom_attributes нет отдельной общей таблицы определений; единая
        # характеристика определяется её именем, типом значения и единицей.
        return (attribute["name"].strip().casefold(), attribute["value_type"], (attribute["unit"] or "").strip().casefold())

    @classmethod
    def _choose_columns(cls, components: list[dict], specs: dict[int, dict], custom: dict[int, list[dict]], component_type: str | None) -> list[dict]:
        columns = [{"kind": "type", "key": "component_type", "label": "Тип", "data_type": "text"},
                   {"kind": "base", "key": "manufacturer", "label": "Производитель", "data_type": "text"},
                   {"kind": "base", "key": "model_name", "label": "Название модели", "data_type": "text"}]
        kinds = [component_type] if component_type else sorted(SPEC_FIELDS)
        standard_defs: dict[str, set[str]] = {}
        labels: dict[str, Counter] = {}
        for kind in kinds:
            for field, (label, data_type, _extra) in cls._definitions(kind).items():
                standard_defs.setdefault(field, set()).add(kind)
                labels.setdefault(field, Counter())[(label, data_type)] += 1
        if component_type is None:
            keys = sorted((field for field, owners in standard_defs.items() if len(owners) >= 2),
                          key=lambda field: (min(COMPONENT_TYPE_LABELS.get(k, k) for k in standard_defs[field]), field))
        else:
            keys = sorted((field for field in standard_defs if any(
                cls._populated(cls._spec_value(specs.get(row["id"]) or {}, row["component_type"], field))
                for row in components
            )), key=lambda field: field)
        for field in keys:
            if component_type is None:
                if field == "ram_type":
                    # В общей таблице это объединённое поле описывает тип памяти
                    # модуля и поддерживаемые платой типы, поэтому используем
                    # нейтральную подпись вместо подписи конкретной категории.
                    label = "Тип памяти"
                    data_type = "strings"
                else:
                    label, data_type = sorted(labels[field].items(), key=lambda pair: (-pair[1], pair[0][0].casefold()))[0][0]
            else:
                label, data_type = sorted(labels[field].items(), key=lambda pair: pair[0][0].casefold())[0][0]
            columns.append({"kind": "spec", "key": field, "label": label, "data_type": data_type})

        custom_by_identity: dict[tuple[str, str, str], dict] = {}
        owners: dict[tuple[str, str, str], set[str]] = {}
        present: set[tuple[str, str, str]] = set()
        for row in components:
            for attribute in custom.get(row["id"], []):
                identity = cls._custom_identity(attribute)
                owners.setdefault(identity, set()).add(row["component_type"])
                custom_by_identity.setdefault(identity, attribute)
                value_key = {"text": "value_text", "number": "value_number", "boolean": "value_boolean", "enum": "value_enum"}[attribute["value_type"]]
                if cls._populated(attribute[value_key]):
                    present.add(identity)
        if component_type is None:
            custom_keys = sorted((identity for identity in owners if len(owners[identity]) >= 2 and identity in present),
                                 key=lambda identity: (identity[0], identity[1], identity[2]))
        else:
            custom_keys = sorted((identity for identity in present if component_type in owners[identity]),
                                 key=lambda identity: (identity[0], identity[1], identity[2]))
        for identity in custom_keys:
            attribute = custom_by_identity[identity]
            columns.append({"kind": "custom", "key": identity, "label": attribute["name"], "data_type": attribute["value_type"]})
        return columns

    @staticmethod
    def _sort_value(value, data_type: str):
        if value is None or value == "" or value == [] or value == {}:
            return (1, "")  # пустые значения всегда после заполненных
        if data_type in {"int", "number", "numeric"}:
            return (0, float(value))
        if isinstance(value, bool):
            return (0, int(value))
        if isinstance(value, (list, dict)):
            value = ", ".join(f"{key}:{item}" for key, item in sorted(value.items())) if isinstance(value, dict) else ", ".join(map(str, value))
        return (0, str(value).casefold())

    def _sort_by_header(self, column: int) -> None:
        if column >= len(self._columns):
            return
        descriptor = self._columns[column]
        if self._header_sort and self._header_sort[0] == descriptor:
            self._header_sort = (descriptor, not self._header_sort[1])
        else:
            self._header_sort = (descriptor, False)
        self.refresh()

    def _raw_value(self, descriptor: dict, component: dict, specs: dict, custom: dict):
        if descriptor["kind"] in {"base", "type"}:
            return component[descriptor["key"]]
        if descriptor["kind"] == "spec":
            return self._spec_value(specs.get(component["id"], {}), component["component_type"], descriptor["key"])
        identity = descriptor["key"]
        for attribute in custom.get(component["id"], []):
            if self._custom_identity(attribute) == identity:
                return attribute[{"text": "value_text", "number": "value_number", "boolean": "value_boolean", "enum": "value_enum"}[attribute["value_type"]]]
        return None

    def _typed_sort_value(self, descriptor: dict, component: dict, specs: dict, custom: dict):
        value = self._raw_value(descriptor, component, specs, custom)
        if descriptor["kind"] == "type":
            value = COMPONENT_TYPE_LABELS.get(value, value)
        elif descriptor["kind"] == "spec" and descriptor["data_type"] in {"enum", "choice_text", "strings", "form_factors"}:
            value = self._display_value(descriptor, value, component) if value is not None else None
        elif descriptor["kind"] == "spec" and descriptor["data_type"] == "radiators":
            value = ", ".join(map(str, value)) if value else value
        elif descriptor["kind"] == "spec" and descriptor["data_type"] == "connectors":
            value = ", ".join(sorted(value)) if value else value
        return self._sort_value(value, descriptor["data_type"])

    def _display_value(self, descriptor: dict, value, component: dict) -> str:
        if value is None:
            return ""
        if descriptor["kind"] == "type":
            return COMPONENT_TYPE_LABELS.get(value, "Неизвестный тип")
        if descriptor["kind"] == "spec":
            field = descriptor["key"]
            if field in {"capacity_gb", "vram_gb"}:
                return f"{value * 1024:g} МБ" if value < 1 else f"{value:g} ГБ"
            kind = descriptor["data_type"]
            if kind == "bool":
                return "Да" if value else "Нет"
            if kind in {"enum", "choice_text"}:
                options = {option["value"]: option["display_value"] for option in list_specification_options(component["component_type"], field, self.database_path)}
                return options.get(value, value)
            if kind in {"strings", "form_factors", "radiators"}:
                if kind == "radiators":
                    return ", ".join(f"{item} мм" for item in value)
                option_field = "socket" if field == "supported_sockets" else field
                options = {option["value"]: option["display_value"] for option in list_specification_options(component["component_type"], option_field, self.database_path)}
                return ", ".join(options.get(item, item) for item in value)
            if kind == "connectors":
                return ", ".join(f"{key}: {count}" for key, count in sorted(value.items()))
            suffix = {"int": "шт."}.get(kind, "")
            return f"{value:g} {suffix}".strip() if isinstance(value, float) else f"{value} {suffix}".strip()
        if descriptor["kind"] == "custom" and descriptor["data_type"] == "boolean":
            return "Да" if value else "Нет"
        return str(value)

    @staticmethod
    def _create_table(headers: list[str]) -> QTableWidget:
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.horizontalHeader().setStretchLastSection(True)
        table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        return table

    def refresh(self, *_args) -> None:
        try:
            components = list_owned_models(
                search=self.search_input.text() if hasattr(self, "search_input") else "",
                component_type=self.type_filter.currentData() if hasattr(self, "type_filter") else None,
                descending=self.sort_order.currentData() if hasattr(self, "sort_order") else False,
                database_path=self.database_path,
            )
            specs = {row["id"]: (get_component_spec(row["id"], self.database_path) or {}) for row in components}
            custom = {row["id"]: get_custom_attributes(row["id"], self.database_path) for row in components}
        except DatabaseError as error:
            _message(self, QMessageBox.Icon.Critical, "Ошибка каталога", str(error), "Закрыть")
            return
        selected_type = self.type_filter.currentData() if hasattr(self, "type_filter") else None
        self._columns = self._choose_columns(components, specs, custom, selected_type)
        self.table.setColumnCount(len(self._columns))
        self.table.setHorizontalHeaderLabels([column["label"] for column in self._columns])
        if self._header_sort and not any(column == self._header_sort[0] for column in self._columns):
            self._header_sort = None
        if self._header_sort:
            descriptor, descending = self._header_sort
            sort_index = self._columns.index(descriptor)
            components.sort(key=lambda row: self._typed_sort_value(descriptor, row, specs, custom), reverse=descending)
            # Пустые значения должны оставаться последними в обоих направлениях.
            empty = [row for row in components if self._raw_value(descriptor, row, specs, custom) in (None, "", [], {})]
            nonempty = [row for row in components if self._raw_value(descriptor, row, specs, custom) not in (None, "", [], {})]
            nonempty.sort(key=lambda row: self._typed_sort_value(descriptor, row, specs, custom), reverse=descending)
            components = nonempty + empty
            self.table.horizontalHeader().setSortIndicator(sort_index, Qt.SortOrder.DescendingOrder if descending else Qt.SortOrder.AscendingOrder)
        else:
            if self.sort_order.currentData():
                components.sort(key=lambda row: row["model_name"].casefold(), reverse=True)
            self.table.horizontalHeader().setSortIndicator(-1, Qt.SortOrder.AscendingOrder)
        self.table.setRowCount(len(components))
        for row, component in enumerate(components):
            for column, descriptor in enumerate(self._columns):
                raw = self._raw_value(descriptor, component, specs, custom)
                value = self._display_value(descriptor, raw, component)
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole + 1, self._sort_value(raw, descriptor["data_type"]))
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, component["id"])
                self.table.setItem(row, column, item)
        self.table.resizeColumnsToContents()
        self.status_message(f"Комплектующих в наличии: {len(components)}")

    def _selected_component_id(self) -> int | None:
        row = self.table.currentRow()
        return self.table.item(row, 0).data(Qt.ItemDataRole.UserRole) if row >= 0 else None

    def _context_menu(self, position) -> None:
        index = self.table.indexAt(position)
        if not index.isValid():
            return
        self.table.selectRow(index.row())
        component_id = self._selected_component_id()
        if component_id is None:
            return
        menu, actions = self._build_context_menu(self)
        edit, duplicate, archive, delete = actions
        selected = menu.exec(self.table.viewport().mapToGlobal(position))
        if selected is edit:
            self._open_component(component_id)
        elif selected is duplicate:
            self._duplicate(component_id)
        elif selected is archive:
            self._archive(component_id)
        elif selected is delete:
            self._delete(component_id)

    @staticmethod
    def _context_action_labels() -> list[str]:
        return ["Редактировать", "Дублировать", "В архив", "Удалить навсегда"]

    @staticmethod
    def _build_context_menu(parent) -> tuple[QMenu, list]:
        menu = QMenu(parent)
        actions = [menu.addAction(label) for label in CatalogPage._context_action_labels()]
        menu.insertSeparator(actions[-1])
        return menu, actions

    def _archive(self, component_id: int) -> None:
        try:
            archive_component(component_id, self.database_path)
        except DatabaseError as error:
            _message(self, QMessageBox.Icon.Warning, "Не удалось архивировать", str(error), "Закрыть")
        self.refresh()

    def _duplicate(self, component_id: int) -> None:
        try:
            duplicate_id = duplicate_component(component_id, self.database_path)
        except (DatabaseError, ValueError, TypeError) as error:
            _message(self, QMessageBox.Icon.Warning, "Не удалось дублировать", str(error), "Закрыть")
            return
        self.refresh()
        self._open_component(duplicate_id)

    def _delete(self, component_id: int) -> None:
        component = get_component(component_id, self.database_path)
        if component is None or not confirm_delete(self, component["model_name"]):
            return
        try:
            delete_component(component_id, self.database_path)
        except DatabaseError as error:
            _message(self, QMessageBox.Icon.Warning, "Не удалось удалить", str(error), "Закрыть")
        self.refresh()

    def _add_component(self) -> None:
        type_dialog = ComponentTypeDialog(self)
        if type_dialog.exec() != QDialog.DialogCode.Accepted or type_dialog.selected_type is None:
            return
        dialog = ModelCardDialog(
            None, self.database_path, self, self.refresh,
            draft_type=type_dialog.selected_type,
        )
        dialog.exec()
        self.refresh()

    def _open_selected(self) -> None:
        component_id = self._selected_component_id()
        if component_id is None:
            _message(self, QMessageBox.Icon.Information, "Комплектующее не выбрано", "Выберите запись в каталоге.")
            return
        self._open_component(component_id)

    def _open_component(self, component_id: int) -> None:
        dialog = ModelCardDialog(component_id, self.database_path, self, self.refresh)
        dialog.exec()
        self.refresh()


class ArchivePage(QWidget):
    """Список архивных комплектующих с восстановлением и удалением."""

    def __init__(self, database_path: Path | str | None = None, status_message: Callable[[str], None] | None = None):
        super().__init__()
        self.database_path = database_path
        self.status_message = status_message or (lambda _message: None)
        layout = QVBoxLayout(self)
        heading = QLabel("Архив")
        heading.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(heading)
        toolbar = QHBoxLayout()
        toolbar.addWidget(_label("Архивные комплектующие можно восстановить в раздел «Моё железо»."), 1)
        self.refresh_button = QPushButton("Обновить")
        self.restore_button = QPushButton("Восстановить")
        self.refresh_button.clicked.connect(self.refresh)
        self.restore_button.clicked.connect(self._restore_selected)
        toolbar.addWidget(self.refresh_button)
        toolbar.addWidget(self.restore_button)
        layout.addLayout(toolbar)
        self.table = CatalogPage._create_table(["Тип", "Комплектующее", "Дата архивации"])
        self.table.cellDoubleClicked.connect(lambda _row, _column: self._open_selected())
        self.table.customContextMenuRequested.connect(self._context_menu)
        layout.addWidget(self.table, 1)
        self.refresh()

    def refresh(self, *_args) -> None:
        try:
            records = list_archived_components(self.database_path)
        except DatabaseError as error:
            _message(self, QMessageBox.Icon.Critical, "Ошибка архива", str(error), "Закрыть")
            return
        self.table.setRowCount(len(records))
        for row, record in enumerate(records):
            values = [COMPONENT_TYPE_LABELS.get(record["component_type"], "Неизвестный тип"),
                      f"{record['manufacturer']} — {record['model_name']}",
                      _display_date(record["archived_at"])]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, record["id"])
                self.table.setItem(row, column, item)
        self.table.resizeColumnsToContents()
        self.status_message(f"Комплектующих в архиве: {len(records)}")

    def _selected_component_id(self) -> int | None:
        row = self.table.currentRow()
        return self.table.item(row, 0).data(Qt.ItemDataRole.UserRole) if row >= 0 else None

    def _context_menu(self, position) -> None:
        index = self.table.indexAt(position)
        if not index.isValid():
            return
        self.table.selectRow(index.row())
        component_id = self._selected_component_id()
        if component_id is None:
            return
        menu, actions = self._build_context_menu(self)
        open_action, restore_action, delete_action = actions
        selected = menu.exec(self.table.viewport().mapToGlobal(position))
        if selected is open_action:
            self._open_component(component_id)
        elif selected is restore_action:
            self._restore(component_id)
        elif selected is delete_action:
            self._delete(component_id)

    @staticmethod
    def _context_action_labels() -> list[str]:
        return ["Открыть / редактировать", "Восстановить", "Удалить навсегда"]

    @staticmethod
    def _build_context_menu(parent) -> tuple[QMenu, list]:
        menu = QMenu(parent)
        actions = [menu.addAction(label) for label in ArchivePage._context_action_labels()]
        menu.insertSeparator(actions[-1])
        return menu, actions

    def _restore(self, component_id: int) -> None:
        try:
            restore_component(component_id, self.database_path)
        except DatabaseError as error:
            _message(self, QMessageBox.Icon.Warning, "Не удалось восстановить", str(error), "Закрыть")
        self.refresh()
        self.status_message("Комплектующее восстановлено и снова отображается в разделе «Моё железо».")

    def _restore_selected(self) -> None:
        component_id = self._selected_component_id()
        if component_id is None:
            _message(self, QMessageBox.Icon.Information, "Комплектующее не выбрано", "Выберите запись в архиве.")
            return
        self._restore(component_id)

    def _delete(self, component_id: int) -> None:
        component = get_component(component_id, self.database_path)
        if component is None or not confirm_delete(self, component["model_name"]):
            return
        try:
            delete_component(component_id, self.database_path)
        except DatabaseError as error:
            _message(self, QMessageBox.Icon.Warning, "Не удалось удалить", str(error), "Закрыть")
        self.refresh()

    def _open_selected(self) -> None:
        component_id = self._selected_component_id()
        if component_id is None:
            _message(self, QMessageBox.Icon.Information, "Комплектующее не выбрано", "Выберите запись в архиве.")
            return
        self._open_component(component_id)

    def _open_component(self, component_id: int) -> None:
        dialog = ModelCardDialog(component_id, self.database_path, self, self.refresh)
        dialog.exec()
        self.refresh()
