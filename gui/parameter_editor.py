"""
Widgets for viewing and editing DCM parameters (scalar, 1D, 2D).
"""
from __future__ import annotations
from typing import Optional, List

import numpy as np

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QSplitter,
    QGroupBox, QFormLayout, QScrollArea, QSizePolicy, QFrame,
    QHeaderView, QAbstractItemView, QMessageBox,
)
from PyQt5.QtCore import Qt, pyqtSignal, QLocale
from PyQt5.QtGui import QColor, QFont, QDoubleValidator

try:
    import matplotlib
    matplotlib.use("Qt5Agg")
    from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.figure import Figure
    import matplotlib.pyplot as plt
    HAS_MPL = True
except ImportError:
    HAS_MPL = False

from core.dcm_model import DCMParameter, ParameterType, PARAM_TYPE_LABELS
from gui.styles import DIFF_COLORS, DIFF_FG


class InfoPanel(QGroupBox):
    """Displays read-only parameter metadata."""

    def __init__(self, parent=None):
        super().__init__("参数信息", parent)
        form = QFormLayout(self)
        form.setSpacing(6)

        def _lbl():
            l = QLabel()
            l.setTextInteractionFlags(Qt.TextSelectableByMouse)
            return l

        self.name_lbl = _lbl()
        self.type_lbl = _lbl()
        self.func_lbl = _lbl()
        self.desc_lbl = _lbl()
        self.unitx_lbl = _lbl()
        self.unity_lbl = _lbl()
        self.unitw_lbl = _lbl()

        form.addRow("名称:", self.name_lbl)
        form.addRow("类型:", self.type_lbl)
        form.addRow("功能:", self.func_lbl)
        form.addRow("描述:", self.desc_lbl)
        form.addRow("X单位:", self.unitx_lbl)
        form.addRow("Y单位:", self.unity_lbl)
        form.addRow("值单位:", self.unitw_lbl)

    def load(self, param: DCMParameter):
        self.name_lbl.setText(param.name)
        self.type_lbl.setText(PARAM_TYPE_LABELS.get(param.param_type, param.param_type.value))
        self.func_lbl.setText(param.function or "—")
        self.desc_lbl.setText(param.long_name or "—")
        self.unitx_lbl.setText(param.unit_x or "—")
        self.unity_lbl.setText(param.unit_y or "—")
        self.unitw_lbl.setText(param.unit_w or "—")

    def clear(self):
        for lbl in (self.name_lbl, self.type_lbl, self.func_lbl,
                    self.desc_lbl, self.unitx_lbl, self.unity_lbl, self.unitw_lbl):
            lbl.setText("—")


class ScalarEditor(QWidget):
    """Editor for KENNWERT scalar parameters."""
    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        row = QHBoxLayout()
        row.addWidget(QLabel("数值:"))
        self.edit = QLineEdit()
        self.edit.setValidator(QDoubleValidator(-1e308, 1e308, 10))
        self.edit.setMinimumWidth(180)
        row.addWidget(self.edit)
        row.addStretch()
        layout.addLayout(row)
        layout.addStretch()

    def load(self, param: DCMParameter):
        v = param.values
        self.edit.setText(str(v) if v is not None else "0.0")

    def save_to(self, param: DCMParameter):
        try:
            param.values = float(self.edit.text())
        except ValueError:
            pass


class CurveEditor(QWidget):
    """Editor for KENNLINIE 1-D curve parameters with chart."""
    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        splitter = QSplitter(Qt.Vertical, self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(splitter)

        # Table
        self.table = QTableWidget()
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.itemChanged.connect(self._on_item_changed)
        splitter.addWidget(self.table)

        # Chart
        if HAS_MPL:
            self.canvas = _make_canvas()
            splitter.addWidget(self.canvas)
            splitter.setSizes([200, 260])
        else:
            splitter.setSizes([400, 0])

        self._loading = False
        self._param: Optional[DCMParameter] = None

    def load(self, param: DCMParameter):
        self._loading = True
        self._param = param
        xs = param.x_values or []
        vs = param.values or []
        n = max(len(xs), len(vs))
        self.table.setRowCount(2)
        self.table.setColumnCount(n)
        self.table.setVerticalHeaderLabels(
            [f"X ({param.unit_x})" if param.unit_x else "X",
             f"值 ({param.unit_w})" if param.unit_w else "值"]
        )
        for i in range(n):
            x_item = QTableWidgetItem(str(xs[i]) if i < len(xs) else "")
            x_item.setBackground(QColor("#2a2a3e"))
            self.table.setItem(0, i, x_item)
            v_item = QTableWidgetItem(str(vs[i]) if i < len(vs) else "")
            self.table.setItem(1, i, v_item)
        self._loading = False
        self._update_chart(xs, vs, param)

    def _on_item_changed(self, item):
        if self._loading or self._param is None:
            return
        self._collect_values()
        xs = self._param.x_values
        vs = self._param.values or []
        self._update_chart(xs, vs, self._param)

    def _collect_values(self):
        if self._param is None:
            return
        xs, vs = [], []
        for c in range(self.table.columnCount()):
            xi = self.table.item(0, c)
            vi = self.table.item(1, c)
            try:
                xs.append(float(xi.text()) if xi else 0.0)
            except ValueError:
                xs.append(0.0)
            try:
                vs.append(float(vi.text()) if vi else 0.0)
            except ValueError:
                vs.append(0.0)
        self._param.x_values = xs
        self._param.values = vs

    def save_to(self, param: DCMParameter):
        self._collect_values()
        param.x_values = self._param.x_values
        param.values = self._param.values

    def _update_chart(self, xs, vs, param):
        if not HAS_MPL:
            return
        try:
            fig = self.canvas.figure
            fig.clear()
            ax = fig.add_subplot(111)
            ax.set_facecolor("#181825")
            fig.patch.set_facecolor("#1e1e2e")
            ax.tick_params(colors="#a6adc8")
            for spine in ax.spines.values():
                spine.set_edgecolor("#45475a")
            if xs and vs:
                ax.plot(xs, vs, color="#89b4fa", linewidth=1.8, marker="o",
                        markersize=4, markerfacecolor="#cba6f7")
                ax.set_xlabel(param.unit_x or "X", color="#a6adc8", fontsize=9)
                ax.set_ylabel(param.unit_w or "Value", color="#a6adc8", fontsize=9)
            ax.grid(True, color="#313244", linestyle="--", linewidth=0.5)
            fig.tight_layout(pad=1.2)
            self.canvas.draw()
        except Exception:
            pass


class MapEditor(QWidget):
    """Editor for KENNFELD 2-D map parameters with heatmap."""
    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        splitter = QSplitter(Qt.Vertical, self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(splitter)

        self.table = QTableWidget()
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.itemChanged.connect(self._on_item_changed)
        splitter.addWidget(self.table)

        if HAS_MPL:
            self.canvas = _make_canvas(height=3.2)
            splitter.addWidget(self.canvas)
            splitter.setSizes([240, 280])
        else:
            splitter.setSizes([500, 0])

        self._loading = False
        self._param: Optional[DCMParameter] = None

    def load(self, param: DCMParameter):
        self._loading = True
        self._param = param
        xs = param.x_values or []
        ys = param.y_values or []
        vals = param.values or []
        nrows = len(ys) or (len(vals))
        ncols = len(xs) or (len(vals[0]) if vals else 0)

        # +1 for Y-axis header column
        self.table.setRowCount(nrows + 1)
        self.table.setColumnCount(ncols + 1)

        # Corner cell
        corner = QTableWidgetItem("")
        corner.setBackground(QColor("#2a2a3e"))
        corner.setFlags(Qt.ItemIsEnabled)
        self.table.setItem(0, 0, corner)

        # X header row
        for c, xv in enumerate(xs):
            item = QTableWidgetItem(str(xv))
            item.setBackground(QColor("#2a2a3e"))
            item.setForeground(QColor("#89dceb"))
            self.table.setItem(0, c + 1, item)

        # Y header col + data
        for r in range(nrows):
            yv = ys[r] if r < len(ys) else ""
            y_item = QTableWidgetItem(str(yv))
            y_item.setBackground(QColor("#2a2a3e"))
            y_item.setForeground(QColor("#cba6f7"))
            self.table.setItem(r + 1, 0, y_item)
            row_vals = vals[r] if r < len(vals) else []
            for c in range(ncols):
                v = row_vals[c] if c < len(row_vals) else 0.0
                self.table.setItem(r + 1, c + 1, QTableWidgetItem(str(v)))

        self.table.horizontalHeader().setVisible(False)
        self.table.verticalHeader().setVisible(False)
        self._loading = False
        self._update_chart(xs, ys, vals, param)

    def _on_item_changed(self, item):
        if self._loading or self._param is None:
            return
        self._collect_values()
        xs = self._param.x_values
        ys = self._param.y_values
        vals = self._param.values or []
        self._update_chart(xs, ys, vals, self._param)

    def _collect_values(self):
        if self._param is None:
            return
        nr = self.table.rowCount() - 1
        nc = self.table.columnCount() - 1
        xs, ys, rows = [], [], []
        for c in range(nc):
            it = self.table.item(0, c + 1)
            try:
                xs.append(float(it.text()) if it else 0.0)
            except ValueError:
                xs.append(0.0)
        for r in range(nr):
            it = self.table.item(r + 1, 0)
            try:
                ys.append(float(it.text()) if it else 0.0)
            except ValueError:
                ys.append(0.0)
            row = []
            for c in range(nc):
                it2 = self.table.item(r + 1, c + 1)
                try:
                    row.append(float(it2.text()) if it2 else 0.0)
                except ValueError:
                    row.append(0.0)
            rows.append(row)
        self._param.x_values = xs
        self._param.y_values = ys
        self._param.values = rows

    def save_to(self, param: DCMParameter):
        self._collect_values()
        param.x_values = self._param.x_values
        param.y_values = self._param.y_values
        param.values = self._param.values

    def _update_chart(self, xs, ys, vals, param):
        if not HAS_MPL or not vals:
            return
        try:
            data = np.array(vals, dtype=float)
            fig = self.canvas.figure
            fig.clear()
            ax = fig.add_subplot(111)
            ax.set_facecolor("#181825")
            fig.patch.set_facecolor("#1e1e2e")
            im = ax.imshow(data, aspect="auto", cmap="plasma",
                           extent=[min(xs or [0]), max(xs or [1]),
                                   min(ys or [0]), max(ys or [1])],
                           origin="lower")
            cbar = fig.colorbar(im, ax=ax)
            cbar.ax.yaxis.set_tick_params(color="#a6adc8")
            plt.setp(cbar.ax.yaxis.get_ticklabels(), color="#a6adc8")
            ax.set_xlabel(param.unit_x or "X", color="#a6adc8", fontsize=9)
            ax.set_ylabel(param.unit_y or "Y", color="#a6adc8", fontsize=9)
            ax.tick_params(colors="#a6adc8")
            for spine in ax.spines.values():
                spine.set_edgecolor("#45475a")
            fig.tight_layout(pad=1.2)
            self.canvas.draw()
        except Exception:
            pass


class ParameterEditorPanel(QWidget):
    """Main editor panel that shows InfoPanel + appropriate editor for any parameter."""
    modified = pyqtSignal(str)  # emits param name when changed

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        self.info_panel = InfoPanel()
        layout.addWidget(self.info_panel)

        self.editor_area = QWidget()
        self.editor_layout = QVBoxLayout(self.editor_area)
        self.editor_layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.editor_area, 1)

        btn_row = QHBoxLayout()
        self.save_btn = QPushButton("保存修改")
        self.save_btn.setObjectName("primaryBtn")
        self.reset_btn = QPushButton("重置")
        btn_row.addStretch()
        btn_row.addWidget(self.reset_btn)
        btn_row.addWidget(self.save_btn)
        layout.addLayout(btn_row)

        self._current_param: Optional[DCMParameter] = None
        self._editor: Optional[QWidget] = None
        self._readonly = False

        self.save_btn.clicked.connect(self._on_save)
        self.reset_btn.clicked.connect(self._on_reset)

    def set_readonly(self, ro: bool):
        self._readonly = ro
        self.save_btn.setVisible(not ro)
        self.reset_btn.setVisible(not ro)

    def load_param(self, param: DCMParameter):
        self._current_param = param
        self.info_panel.load(param)
        self._rebuild_editor(param)

    def _rebuild_editor(self, param: DCMParameter):
        # Clear old editor
        while self.editor_layout.count():
            w = self.editor_layout.takeAt(0).widget()
            if w:
                w.deleteLater()
        self._editor = None

        if param.is_scalar:
            ed = ScalarEditor()
            ed.load(param)
            self._editor = ed
        elif param.is_1d:
            ed = CurveEditor()
            ed.load(param)
            self._editor = ed
        elif param.is_2d:
            ed = MapEditor()
            ed.load(param)
            self._editor = ed
        elif param.is_text:
            from PyQt5.QtWidgets import QTextEdit
            ed = QTextEdit()
            ed.setReadOnly(self._readonly)
            if isinstance(param.values, list):
                ed.setPlainText("\n".join(str(v) for v in param.values))
            elif param.values:
                ed.setPlainText(str(param.values))
            self._editor = ed
        else:
            lbl = QLabel("(不支持的参数类型)")
            lbl.setAlignment(Qt.AlignCenter)
            self._editor = lbl

        if self._editor:
            if self._readonly and hasattr(self._editor, 'setEnabled'):
                self._editor.setEnabled(False)
            self.editor_layout.addWidget(self._editor)

    def _on_save(self):
        if self._current_param is None or self._editor is None:
            return
        if hasattr(self._editor, "save_to"):
            self._editor.save_to(self._current_param)
        self.modified.emit(self._current_param.name)

    def _on_reset(self):
        if self._current_param:
            self._rebuild_editor(self._current_param)

    def clear(self):
        self._current_param = None
        self.info_panel.clear()
        while self.editor_layout.count():
            w = self.editor_layout.takeAt(0).widget()
            if w:
                w.deleteLater()
        self._editor = None


def _make_canvas(height: float = 2.8) -> "FigureCanvas":
    fig = Figure(figsize=(6, height), dpi=96)
    fig.patch.set_facecolor("#1e1e2e")
    canvas = FigureCanvas(fig)
    canvas.setMinimumHeight(int(height * 96))
    return canvas
