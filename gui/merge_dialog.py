"""
Merge dialog for combining two DCM files.
"""
from __future__ import annotations
from typing import Dict, Optional

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QCheckBox, QComboBox, QGroupBox, QFormLayout, QDialogButtonBox,
    QFileDialog, QMessageBox, QScrollArea, QWidget, QFrame,
)
from PyQt5.QtCore import Qt

from core.dcm_model import DCMFile
from core.dcm_compare import DCMDiff, DiffStatus, MergeStrategy, merge_dcm
from core.dcm_writer import write_dcm


class MergeDialog(QDialog):
    """Dialog to configure and execute a DCM merge."""

    def __init__(self, left: DCMFile, right: DCMFile, diff: DCMDiff,
                 per_param_strategies: Optional[Dict[str, MergeStrategy]] = None,
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle("合并 DCM 文件")
        self.setMinimumSize(580, 480)
        self.left = left
        self.right = right
        self.diff = diff
        self.per_param = per_param_strategies or {}
        self._result_path: Optional[str] = None

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Title
        title = QLabel("合并配置")
        title.setObjectName("titleLabel")
        layout.addWidget(title)

        stats = diff.stats()
        summary = QLabel(
            f"总参数: {stats['total']}  |  "
            f"相同: {stats['identical']}  |  "
            f"修改: {stats['modified']}  |  "
            f"仅左: {stats['only_left']}  |  "
            f"仅右: {stats['only_right']}"
        )
        layout.addWidget(summary)

        # Default strategy for modified params
        mod_box = QGroupBox("修改参数的默认策略")
        mod_form = QFormLayout(mod_box)
        self.default_combo = QComboBox()
        self.default_combo.addItems(["保留左侧值", "保留右侧值"])
        mod_form.addRow("默认选择:", self.default_combo)
        layout.addWidget(mod_box)

        # Inclusion options
        inc_box = QGroupBox("包含范围")
        inc_layout = QVBoxLayout(inc_box)
        self.cb_include_left = QCheckBox(f"包含仅在左侧的参数 ({stats['only_left']} 个)")
        self.cb_include_right = QCheckBox(f"包含仅在右侧的参数 ({stats['only_right']} 个)")
        self.cb_include_left.setChecked(True)
        self.cb_include_right.setChecked(True)
        inc_layout.addWidget(self.cb_include_left)
        inc_layout.addWidget(self.cb_include_right)
        layout.addWidget(inc_box)

        # Per-param overrides summary
        if self.per_param:
            ov_box = QGroupBox(f"已设置逐参数策略 ({len(self.per_param)} 个)")
            ov_layout = QVBoxLayout(ov_box)
            scroll = QScrollArea()
            scroll.setMaximumHeight(120)
            scroll.setWidgetResizable(True)
            inner = QWidget()
            inner_layout = QVBoxLayout(inner)
            inner_layout.setSpacing(2)
            for name, strat in self.per_param.items():
                lbl = QLabel(f"  {name}: {'保留左侧' if strat == MergeStrategy.KEEP_LEFT else '保留右侧'}")
                lbl.setObjectName("sectionLabel")
                inner_layout.addWidget(lbl)
            inner_layout.addStretch()
            scroll.setWidget(inner)
            ov_layout.addWidget(scroll)
            layout.addWidget(ov_box)

        # Output path
        out_box = QGroupBox("输出文件")
        out_layout = QHBoxLayout(out_box)
        self.out_label = QLabel("(未选择)")
        self.out_label.setWordWrap(True)
        out_layout.addWidget(self.out_label, 1)
        browse_btn = QPushButton("浏览…")
        browse_btn.clicked.connect(self._browse_output)
        out_layout.addWidget(browse_btn)
        layout.addWidget(out_box)

        # Buttons
        btn_box = QHBoxLayout()
        self.merge_btn = QPushButton("执行合并")
        self.merge_btn.setObjectName("primaryBtn")
        self.merge_btn.clicked.connect(self._do_merge)
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_box.addStretch()
        btn_box.addWidget(cancel_btn)
        btn_box.addWidget(self.merge_btn)
        layout.addLayout(btn_box)

    def _browse_output(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "保存合并结果", "", "DCM Files (*.dcm);;All Files (*)"
        )
        if path:
            if not path.lower().endswith(".dcm"):
                path += ".dcm"
            self._result_path = path
            self.out_label.setText(path)

    def _do_merge(self):
        if not self._result_path:
            QMessageBox.warning(self, "提示", "请先选择输出文件路径。")
            return

        default_strat = (MergeStrategy.KEEP_LEFT
                         if self.default_combo.currentIndex() == 0
                         else MergeStrategy.KEEP_RIGHT)
        result = merge_dcm(
            self.left,
            self.right,
            self.diff,
            overrides=self.per_param,
            default_modified=default_strat,
            include_only_left=self.cb_include_left.isChecked(),
            include_only_right=self.cb_include_right.isChecked(),
        )
        try:
            write_dcm(result, self._result_path)
            QMessageBox.information(
                self, "合并完成",
                f"合并成功！\n共写入 {len(result.parameters)} 个参数。\n\n{self._result_path}"
            )
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "写入失败", str(e))
