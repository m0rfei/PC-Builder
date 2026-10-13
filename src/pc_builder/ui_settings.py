"""Пользовательские настройки масштаба и размера текста интерфейса."""

from __future__ import annotations

import re

from PySide6.QtCore import QEvent, QObject, QSize, Qt, QSettings
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QPushButton,
    QProxyStyle,
    QVBoxLayout,
    QWidget,
)


DEFAULT_PERCENT = 100
ALLOWED_PERCENTAGES = tuple(range(80, 151, 10))
_SCALED_CSS = re.compile(
    r"(?P<property>font-size|padding(?:-[a-z]+)?|margin(?:-[a-z]+)?|border-width)"
    r"\s*:\s*(?P<number>\d+(?:\.\d+)?)\s*(?P<unit>px|pt)",
    re.IGNORECASE,
)


class _ScalingStyle(QProxyStyle):
    """Увеличивает метрики элементов Qt согласно масштабу интерфейса."""

    def __init__(self, base_style):
        super().__init__(base_style)
        self.factor = 1.0

    def pixelMetric(self, metric, option=None, widget=None):
        value = super().pixelMetric(metric, option, widget)
        if value <= 0:
            return value
        return max(1, round(value * self.factor))

    def sizeFromContents(self, content_type, option, size, widget=None):
        result = super().sizeFromContents(content_type, option, size, widget)
        return QSize(max(1, round(result.width() * self.factor)), max(1, round(result.height() * self.factor)))

    def layoutSpacing(self, control1, control2, orientation, option=None, widget=None):
        value = super().layoutSpacing(control1, control2, orientation, option, widget)
        return value if value < 0 else round(value * self.factor)


class UiSettingsController(QObject):
    """Хранилище и application-wide применение настроек без накопления масштаба."""

    def __init__(self, application: QApplication):
        super().__init__(application)
        self.application = application
        self.settings = QSettings("PC-Builder", "PC-Builder")
        self.scale_percent = self._read_percent("interface/scale", DEFAULT_PERCENT)
        self.font_percent = self._read_percent("interface/font", DEFAULT_PERCENT)
        self._base_app_font = QFont(application.font())
        self._applying = False
        self._style = _ScalingStyle(application.style())
        application.setStyle(self._style)
        application.installEventFilter(self)
        self.apply()

    def _read_percent(self, key: str, default: int) -> int:
        try:
            value = int(self.settings.value(key, default))
        except (TypeError, ValueError):
            value = default
        return value if value in ALLOWED_PERCENTAGES else default

    @staticmethod
    def _scale_font(font: QFont, factor: float) -> QFont:
        result = QFont(font)
        if result.pointSizeF() > 0:
            result.setPointSizeF(max(1.0, result.pointSizeF() * factor))
        elif result.pixelSize() > 0:
            result.setPixelSize(max(1, round(result.pixelSize() * factor)))
        return result

    @staticmethod
    def _scale_css(stylesheet: str, scale_factor: float, font_factor: float) -> str:
        def replace(match: re.Match) -> str:
            factor = font_factor if match.group("property").lower() == "font-size" else scale_factor
            value = float(match.group("number")) * factor
            number = str(round(value, 2)).rstrip("0").rstrip(".")
            return f"{match.group('property')}: {number}{match.group('unit')}"

        return _SCALED_CSS.sub(replace, stylesheet)

    @staticmethod
    def _scaled_size(size: QSize, factor: float, *, maximum: bool = False) -> QSize:
        limit = 16_777_215
        width = size.width()
        height = size.height()
        if maximum:
            width = limit if width >= limit else max(0, round(width * factor))
            height = limit if height >= limit else max(0, round(height * factor))
        else:
            width = max(0, round(width * factor))
            height = max(0, round(height * factor))
        return QSize(width, height)

    def set_scale_percent(self, value: int) -> None:
        if value not in ALLOWED_PERCENTAGES:
            return
        self.scale_percent = value
        self.settings.setValue("interface/scale", value)
        self.settings.sync()
        self.apply()

    def set_font_percent(self, value: int) -> None:
        if value not in ALLOWED_PERCENTAGES:
            return
        self.font_percent = value
        self.settings.setValue("interface/font", value)
        self.settings.sync()
        self.apply()

    def reset(self) -> None:
        self.scale_percent = DEFAULT_PERCENT
        self.font_percent = DEFAULT_PERCENT
        self.settings.setValue("interface/scale", DEFAULT_PERCENT)
        self.settings.setValue("interface/font", DEFAULT_PERCENT)
        self.settings.sync()
        self.apply()

    def apply(self) -> None:
        if self._applying:
            return
        self._applying = True
        scale_factor = self.scale_percent / 100
        font_factor = self.font_percent / 100
        self._style.factor = scale_factor
        self.application.setFont(self._scale_font(self._base_app_font, font_factor))
        for window in self.application.topLevelWidgets():
            self._apply_tree(window, scale_factor, font_factor)
        self._applying = False

    def _apply_tree(self, widget: QWidget, scale_factor: float, font_factor: float) -> None:
        # Обычные элементы наследуют размер от QApplication. Не назначаем им
        # локальный QFont: это фиксирует размер и мешает дальнейшему наследованию.
        # Если приложение явно установило шрифт конкретному виджету, сохраняем
        # именно его исходное значение и масштабируем от него.
        if widget.testAttribute(Qt.WidgetAttribute.WA_SetFont):
            if not hasattr(widget, "_pcbuilder_explicit_base_font"):
                widget._pcbuilder_explicit_base_font = QFont(widget.font())
            widget.setFont(self._scale_font(widget._pcbuilder_explicit_base_font, font_factor))

        current_style = widget.styleSheet()
        last_style = getattr(widget, "_pcbuilder_applied_stylesheet", None)
        if not hasattr(widget, "_pcbuilder_base_stylesheet") or (last_style is not None and current_style != last_style):
            widget._pcbuilder_base_stylesheet = current_style
        transformed_style = self._scale_css(widget._pcbuilder_base_stylesheet, scale_factor, font_factor)
        if current_style != transformed_style:
            widget.setStyleSheet(transformed_style)
        widget._pcbuilder_applied_stylesheet = transformed_style

        layout = widget.layout()
        if layout is not None:
            if not hasattr(layout, "_pcbuilder_base_margins"):
                layout._pcbuilder_base_margins = layout.contentsMargins()
                layout._pcbuilder_base_spacing = layout.spacing()
            margins = layout._pcbuilder_base_margins
            layout.setContentsMargins(*(round(v * scale_factor) for v in (
                margins.left(), margins.top(), margins.right(), margins.bottom()
            )))
            if layout._pcbuilder_base_spacing >= 0:
                layout.setSpacing(round(layout._pcbuilder_base_spacing * scale_factor))
            for index in range(layout.count()):
                item = layout.itemAt(index)
                child = item.widget()
                if child is not None:
                    self._apply_tree(child, scale_factor, font_factor)
                elif item.layout() is not None:
                    self._apply_layout_tree(item.layout(), scale_factor)
        for child in widget.children():
            if not isinstance(child, QWidget):
                continue
            if layout is None or not any(layout.itemAt(i).widget() is child for i in range(layout.count())):
                self._apply_tree(child, scale_factor, font_factor)

        if not hasattr(widget, "_pcbuilder_base_minimum"):
            widget._pcbuilder_base_minimum = widget.minimumSize()
            widget._pcbuilder_base_maximum = widget.maximumSize()
        widget.setMinimumSize(self._scaled_size(widget._pcbuilder_base_minimum, scale_factor))
        widget.setMaximumSize(self._scaled_size(widget._pcbuilder_base_maximum, scale_factor, maximum=True))

    def _apply_layout_tree(self, layout, factor: float) -> None:
        if not hasattr(layout, "_pcbuilder_base_margins"):
            layout._pcbuilder_base_margins = layout.contentsMargins()
            layout._pcbuilder_base_spacing = layout.spacing()
        margins = layout._pcbuilder_base_margins
        layout.setContentsMargins(*(round(v * factor) for v in (
            margins.left(), margins.top(), margins.right(), margins.bottom()
        )))
        if layout._pcbuilder_base_spacing >= 0:
            layout.setSpacing(round(layout._pcbuilder_base_spacing * factor))
        for index in range(layout.count()):
            item = layout.itemAt(index)
            if item.widget() is not None:
                self._apply_tree(item.widget(), factor, self.font_percent / 100)
            elif item.layout() is not None:
                self._apply_layout_tree(item.layout(), factor)

    def eventFilter(self, watched, event):
        if not self._applying and event.type() in (QEvent.Type.Show, QEvent.Type.Polish) and isinstance(watched, QWidget):
            self._applying = True
            self._apply_tree(watched, self.scale_percent / 100, self.font_percent / 100)
            self._applying = False
        return False


def ensure_ui_settings(application: QApplication | None = None) -> UiSettingsController:
    application = application or QApplication.instance()
    if application is None:
        raise RuntimeError("Для настроек интерфейса сначала создайте QApplication.")
    controller = getattr(application, "_pcbuilder_ui_settings", None)
    if controller is None:
        controller = UiSettingsController(application)
        application._pcbuilder_ui_settings = controller
    return controller


class UiSettingsDialog(QDialog):
    """Диалог настроек, применяющий значения сразу и сохраняющий их в QSettings."""

    def __init__(self, controller: UiSettingsController, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.setWindowTitle("Настройки интерфейса")
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.scale_combo = self._percent_combo(controller.scale_percent)
        self.font_combo = self._percent_combo(controller.font_percent)
        form.addRow("Масштаб интерфейса:", self.scale_combo)
        form.addRow("Размер шрифта:", self.font_combo)
        layout.addLayout(form)
        self.scale_combo.currentIndexChanged.connect(self._scale_changed)
        self.font_combo.currentIndexChanged.connect(self._font_changed)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText("Закрыть")
        buttons.rejected.connect(self.accept)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)
        self.reset_button = QPushButton("Сбросить к 100%")
        self.reset_button.clicked.connect(self._reset)
        layout.addWidget(self.reset_button)

    @staticmethod
    def _percent_combo(current: int) -> QComboBox:
        combo = QComboBox()
        for value in ALLOWED_PERCENTAGES:
            combo.addItem(f"{value}%", value)
        combo.setCurrentIndex(combo.findData(current))
        return combo

    def _scale_changed(self, _index: int) -> None:
        value = self.scale_combo.currentData()
        if value is not None:
            self.controller.set_scale_percent(value)

    def _font_changed(self, _index: int) -> None:
        value = self.font_combo.currentData()
        if value is not None:
            self.controller.set_font_percent(value)

    def _reset(self) -> None:
        self.controller.reset()
        self.scale_combo.setCurrentIndex(self.scale_combo.findData(DEFAULT_PERCENT))
        self.font_combo.setCurrentIndex(self.font_combo.findData(DEFAULT_PERCENT))

