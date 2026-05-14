"""
Side-by-side DCM comparison view.
"""
from __future__ import annotations
from typing import Optional, Dict

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QSplitter, QHeaderView,
    QAbstractItemView, QGroupBox, QComboBox, QCheckBox,
    QSizePolicy, QFrame, QTreeWidget, QTreeWidgetItem,
    QLineEdit, QApplication,
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QBrush

from core.dcm_model import DCMFile, DCMParameter
from core.dcm_compare import DCMDiff, ParamDiff, DiffStatus, MergeStrategy
from gui.styles import DIFF_COLORS, DIFF_FG

_STATUS_ICON = {
    DiffStatus.IDENTICAL: "●",
    DiffStatus.MODIFIED:  "◆",
    DiffStatus.ONLY_LEFT: "◀",
    DiffStatus.ONLY_RIGHT: "▶",
}
_STATUS_COLOR = {
    DiffStatus.IDENTICAL: "#a6adc8",
    DiffStatus.MODIFIED:  "#fab387",
    DiffStatus.ONLY_LEFT: "#89b4fa",
    DiffStatus.ONLY_RIGHT: "#a6e3a1",
}


class DiffTreePanel(QWidget):
    """Left tree showing all parameter diffs grouped by status."""
    param_selected = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Filter row
        filter_row = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("搜索参数名…")
        self.search_edit.textChanged.connect(self._apply_filter)
        filter_row.addWidget(self.search_edit)
        layout.addLayout(filter_row)

        # Status filter checkboxes
        cb_row = QHBoxLayout()
        self.cb_modified = QCheckBox("修改")
        self.cb_left = QCheckBox("仅左")
        self.cb_right = QCheckBox("仅右")
        self.cb_same = QCheckBox("相同")
        for cb in (self.cb_modified, self.cb_left, self.cb_right, self.cb_same):
            cb.setChecked(True)
            cb.stateChanged.connect(self._apply_filter)
            cb_row.addWidget(cb)
        layout.addLayout(cb_row)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabel("参数差异列表")
        self.tree.setColumnCount(2)
        self.tree.setHeaderLabels(["参数名称", "状态"])
        self.tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.tree.itemSelectionChanged.connect(self._on_select)
        layout.addWidget(self.tree)

        # Stats row
        self.stats_lbl = QLabel()
        self.stats_lbl.setObjectName("sectionLabel")
        layout.addWidget(self.stats_lbl)

        self._diff: Optional[DCMDiff] = None
        self._all_items: list = []

    def load_diff(self, diff: DCMDiff):
        self._diff = diff
        self._rebuild_tree(diff)
        stats = diff.stats()
        self.stats_lbl.setText(
            f"共 {stats['total']}  修改 {stats['modified']}  "
            f"仅左 {stats['only_left']}  仅右 {stats['only_right']}  "
            f"相同 {stats['identical']}"
        )

    def _rebuild_tree(self, diff: DCMDiff):
        self.tree.clear()
        self._all_items.clear()
        groups = {
            DiffStatus.MODIFIED: ("修改 (MODIFIED)", self.cb_modified),
            DiffStatus.ONLY_LEFT: ("仅在左侧 (LEFT ONLY)", self.cb_left),
            DiffStatus.ONLY_RIGHT: ("仅在右侧 (RIGHT ONLY)", self.cb_right),
            DiffStatus.IDENTICAL: ("相同 (IDENTICAL)", self.cb_same),
        }
        for status, (group_name, _) in groups.items():
            items_in_group = [d for d in diff.diffs.values() if d.status == status]
            if not items_in_group:
                continue
            group_item = QTreeWidgetItem([f"{group_name}  ({len(items_in_group)})", ""])
            font = group_item.font(0)
            font.setBold(True)
            group_item.setFont(0, font)
            group_item.setForeground(0, QBrush(QColor(_STATUS_COLOR[status])))
            self.tree.addTopLevelItem(group_item)
            for d in sorted(items_in_group, key=lambda x: x.name):
                child = QTreeWidgetItem([d.name, d.summary()])
                child.setForeground(0, QBrush(QColor(_STATUS_COLOR[status])))
                child.setData(0, Qt.UserRole, d.name)
                group_item.addChild(child)
                self._all_items.append(child)
            group_item.setExpanded(status != DiffStatus.IDENTICAL)

    def _on_select(self):
        items = self.tree.selectedItems()
        if not items:
            return
        name = items[0].data(0, Qt.UserRole)
        if name:
            self.param_selected.emit(name)

    def _apply_filter(self):
        text = self.search_edit.text().lower()
        show_map = {
            DiffStatus.MODIFIED: self.cb_modified.isChecked(),
            DiffStatus.ONLY_LEFT: self.cb_left.isChecked(),
            DiffStatus.ONLY_RIGHT: self.cb_right.isChecked(),
            DiffStatus.IDENTICAL: self.cb_same.isChecked(),
        }
        if self._diff is None:
            return
        self._rebuild_tree(self._diff)
        # Apply text filter
        root = self.tree.invisibleRootItem()
        for gi in range(root.childCount()):
            group = root.child(gi)
            any_visible = False
            for ci in range(group.childCount()):
                child = group.child(ci)
                name = child.data(0, Qt.UserRole) or ""
                # get status from diff
                d = self._diff.diffs.get(name)
                status_ok = show_map.get(d.status, True) if d else True
                visible = status_ok and (not text or text in name.lower())
                child.setHidden(not visible)
                if visible:
                    any_visible = True
            group.setHidden(not any_visible)


class DiffDetailPanel(QWidget):
    """Right panel showing side-by-side diff for selected parameter."""
    strategy_changed = pyqtSignal(str, str)  # name, strategy

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        # Header with name and strategy selector
        header = QHBoxLayout()
        self.name_lbl = QLabel("—")
        self.name_lbl.setObjectName("titleLabel")
        header.addWidget(self.name_lbl)
        header.addStretch()
        header.addWidget(QLabel("合并策略:"))
        self.strategy_combo = QComboBox()
        self.strategy_combo.addItems(["保留左侧", "保留右侧"])
        self.strategy_combo.currentIndexChanged.connect(self._on_strategy)
        header.addWidget(self.strategy_combo)
        layout.addLayout(header)

        # Side-by-side labels
        labels = QHBoxLayout()
        self.left_lbl = QLabel("← 左侧文件")
        self.left_lbl.setObjectName("sectionLabel")
        self.right_lbl = QLabel("右侧文件 →")
        self.right_lbl.setObjectName("sectionLabel")
        self.right_lbl.setAlignment(Qt.AlignRight)
        labels.addWidget(self.left_lbl)
        labels.addWidget(self.right_lbl)
        layout.addLayout(labels)

        # Diff table
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["行", "列", "左侧值", "右侧值"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table)

        self._name: Optional[str] = None

    def load_diff(self, pdiff: ParamDiff, left_path: str, right_path: str):
        self._name = pdiff.name
        self.name_lbl.setText(pdiff.name)
        self.left_lbl.setText(f"← {left_path.split('/')[-1].split(chr(92))[-1]}")
        self.right_lbl.setText(f"{right_path.split('/')[-1].split(chr(92))[-1]} →")

        if pdiff.status == DiffStatus.IDENTICAL:
            self.table.setRowCount(1)
            item = QTableWidgetItem("参数值完全相同")
            item.setForeground(QColor(DIFF_FG["same"]))
            self.table.setItem(0, 0, item)
            for c in range(1, 4):
                self.table.setItem(0, c, QTableWidgetItem(""))
            return

        if pdiff.status == DiffStatus.ONLY_LEFT:
            self.table.setRowCount(1)
            self.table.setItem(0, 0, QTableWidgetItem("仅在左侧存在"))
            for c in range(1, 4):
                self.table.setItem(0, c, QTableWidgetItem(""))
            self._color_row(0, "removed")
            return

        if pdiff.status == DiffStatus.ONLY_RIGHT:
            self.table.setRowCount(1)
            self.table.setItem(0, 0, QTableWidgetItem("仅在右侧存在"))
            for c in range(1, 4):
                self.table.setItem(0, c, QTableWidgetItem(""))
            self._color_row(0, "added")
            return

        # Modified
        vd = pdiff.value_diffs
        self.table.setRowCount(len(vd))
        for i, (row, col, lv, rv) in enumerate(vd):
            self.table.setItem(i, 0, QTableWidgetItem(str(row)))
            self.table.setItem(i, 1, QTableWidgetItem(str(col)))
            self.table.setItem(i, 2, QTableWidgetItem(str(lv)))
            self.table.setItem(i, 3, QTableWidgetItem(str(rv)))
            self._color_row(i, "modified")

    def _color_row(self, row: int, kind: str):
        bg = QColor(DIFF_COLORS.get(kind, DIFF_COLORS["same"]))
        fg = QColor(DIFF_FG.get(kind, DIFF_FG["same"]))
        for c in range(self.table.columnCount()):
            it = self.table.item(row, c)
            if it:
                it.setBackground(bg)
                it.setForeground(fg)

    def _on_strategy(self, idx: int):
        if self._name:
            s = "keep_left" if idx == 0 else "keep_right"
            self.strategy_changed.emit(self._name, s)

    def clear(self):
        self.name_lbl.setText("—")
        self.table.setRowCount(0)
        self._name = None


class CompareView(QWidget):
    """Full comparison view combining tree + detail panels."""
    strategies_updated = pyqtSignal(dict)  # name -> strategy

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(splitter)

        self.tree_panel = DiffTreePanel()
        self.tree_panel.setMinimumWidth(280)
        splitter.addWidget(self.tree_panel)

        self.detail_panel = DiffDetailPanel()
        splitter.addWidget(self.detail_panel)
        splitter.setSizes([320, 640])

        self._diff: Optional[DCMDiff] = None
        self._strategies: Dict[str, str] = {}

        self.tree_panel.param_selected.connect(self._show_param)
        self.detail_panel.strategy_changed.connect(self._record_strategy)

    def load(self, diff: DCMDiff):
        self._diff = diff
        self._strategies.clear()
        self.tree_panel.load_diff(diff)
        self.detail_panel.clear()

    def _show_param(self, name: str):
        if self._diff is None:
            return
        pdiff = self._diff.diffs.get(name)
        if pdiff:
            self.detail_panel.load_diff(pdiff, self._diff.left_path, self._diff.right_path)

    def _record_strategy(self, name: str, strategy: str):
        self._strategies[name] = strategy
        self.strategies_updated.emit(self._strategies)

    def get_strategies(self) -> Dict[str, MergeStrategy]:
        result = {}
        for name, s in self._strategies.items():
            result[name] = MergeStrategy.KEEP_LEFT if s == "keep_left" else MergeStrategy.KEEP_RIGHT
        return result
