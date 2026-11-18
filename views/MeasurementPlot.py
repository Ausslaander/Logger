from collections import deque
from math import isfinite

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import (
    QComboBox, QFrame, QHBoxLayout, QLineEdit, QSizePolicy, QVBoxLayout, QWidget,
)


class MeasurementPlot(QFrame):
    """Независимый выбор параметра и график последних десяти минут."""

    def __init__(self, parameters, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setMinimumWidth(320)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.parameter_combo = QComboBox(self)
        self.parameter_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.parameter_combo.setMinimumContentsLength(14)
        self.parameter_combo.addItem("Выберите параметр", None)
        for parameter in parameters:
            title = parameter.name
            if parameter.unit:
                title += f", {parameter.unit}"
            self.parameter_combo.addItem(title, parameter)

        self.current_value = QLineEdit("—", self)
        self.current_value.setReadOnly(True)
        self.current_value.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.current_value.setFixedWidth(120)
        self.current_value.setAccessibleName("Текущее значение")
        self.current_value.setToolTip("Текущее значение выбранного параметра")
        controls = QHBoxLayout()
        controls.addWidget(self.parameter_combo, 1)
        controls.addWidget(self.current_value)
        self.canvas = PlotCanvas(self)
        layout = QVBoxLayout(self)
        layout.addLayout(controls)
        layout.addWidget(self.canvas, 1)
        self.parameter_combo.currentIndexChanged.connect(self._change_parameter)

    def _change_parameter(self):
        parameter = self.parameter_combo.currentData()
        self.parameter_combo.setToolTip(self.parameter_combo.currentText())
        self.canvas.clear(parameter.unit if parameter else "")
        self.current_value.setText("—")

    def clear(self):
        self.canvas.clear(self.canvas.unit)
        self.current_value.setText("—")

    def add_sample(self, elapsed: float, values: dict):
        parameter = self.parameter_combo.currentData()
        if parameter is not None:
            value = values.get(parameter.key)
            self.canvas.add_sample(elapsed, value)
            self.current_value.setText(
                f"{value:g}" if isinstance(value, (int, float)) and isfinite(value) else "—"
            )


class PlotCanvas(QWidget):
    WINDOW_SECONDS = 600

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(180)
        self.unit = ""
        self._points = deque()

    def clear(self, unit: str):
        self.unit = unit
        self._points.clear()
        self.update()

    def add_sample(self, elapsed: float, value):
        if not isinstance(value, (int, float)) or not isfinite(value):
            value = None
        self._points.append((elapsed, value))
        while self._points and self._points[0][0] < elapsed - self.WINDOW_SECONDS:
            self._points.popleft()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        palette = self.palette()
        painter.fillRect(self.rect(), palette.base())
        area = QRectF(72, 20, self.width() - 88, self.height() - 58)
        painter.setPen(palette.mid().color())
        painter.drawRect(area)
        painter.setPen(palette.text().color())
        painter.drawText(QRectF(0, 0, 66, 20), Qt.AlignmentFlag.AlignCenter, self.unit)
        painter.drawText(
            QRectF(area.left(), area.bottom() + 20, area.width(), 18),
            Qt.AlignmentFlag.AlignCenter, "Время от начала испытания, с",
        )

        valid_values = [value for _, value in self._points if value is not None]
        if not valid_values:
            painter.drawText(area, Qt.AlignmentFlag.AlignCenter, "Ожидание измерений")
            return

        minimum, maximum = min(valid_values), max(valid_values)
        padding = max((maximum - minimum) * 0.1, abs(maximum) * 0.01, 0.1)
        minimum -= padding
        maximum += padding
        end = max(self._points[-1][0], 10)
        start = max(0, end - self.WINDOW_SECONDS)

        for tick in range(5):
            fraction = tick / 4
            y = area.bottom() - fraction * area.height()
            x = area.left() + fraction * area.width()
            painter.setPen(palette.mid().color())
            painter.drawLine(QPointF(area.left(), y), QPointF(area.right(), y))
            painter.drawLine(QPointF(x, area.top()), QPointF(x, area.bottom()))
            painter.setPen(palette.text().color())
            painter.drawText(
                QRectF(0, y - 9, area.left() - 7, 18),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                f"{minimum + fraction * (maximum - minimum):.4g}",
            )
            painter.drawText(
                QRectF(x - 28, area.bottom() + 1, 56, 18),
                Qt.AlignmentFlag.AlignCenter, f"{start + fraction * (end - start):.4g}",
            )

        path = QPainterPath()
        connected = False
        last_point = None
        for elapsed, value in self._points:
            if value is None:
                connected = False
                continue
            point = QPointF(
                area.left() + (elapsed - start) / (end - start) * area.width(),
                area.bottom() - (value - minimum) / (maximum - minimum) * area.height(),
            )
            if connected:
                path.lineTo(point)
            else:
                path.moveTo(point)
            connected = True
            last_point = point
        painter.setClipRect(area.adjusted(-3, -3, 3, 3))
        painter.setPen(QPen(QColor("#3489df"), 2))
        painter.drawPath(path)
        if last_point is not None:
            painter.setBrush(QColor("#3489df"))
            painter.drawEllipse(last_point, 3, 3)
