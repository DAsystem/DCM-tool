"""
Main application window for the DCM Management Tool.
"""
from __future__ import annotations
import os
from pathlib import Path
from typing import Optional, Dict

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QTreeWidget, QTreeWidgetItem, QTabWidget, QLabel, QPushButton,
    QToolBar, QAction, QFileDialog, QMessageBox, QStatusBar,
    QLineEdit, QMenu, QMenuBar, QDialog, QDialogButtonBox,
    QListWidget, QListWidgetItem, QAbstractItemView, QApplication,
    QFrame, QGroupBox, QCheckBox, QScrollArea,
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QSize
from PyQt5.QtGui import QIcon, QColor, QFont, QKeySequence

from core.dcm_model import DCMFile, DCMParameter, ParameterType, PARAM_TYPE_LABELS
from core.dcm_parser import parse_dcm
from core.dcm_writer import write_dcm
from core.dcm_compare import compare_dcm, DCMDiff, MergeStrategy

from gui.parameter_editor import ParameterEditorPanel
from gui.compare_view import CompareView
from gui.merge_dialog import MergeDialog
from gui.styles import MAIN_STYLE

_TYPE_ICONS = {
    ParameterType.SCALAR:     "◆",
    ParameterType.CURVE:      "📈",
    ParameterType.FIXED_CURVE:"📈",
    ParameterType.MAP:        "🗺",
    ParameterType.FIXED_MAP:  "🗺",
    ParameterType.GROUP_CURVE:"📈",
    ParameterType.GROUP_MAP:  "🗺",
    ParameterType.DISTRIBUTION:"≋",
    ParameterType.GROUP_PARAM:"☰",
    ParameterType.TEXT:       "T",
}

_GROUP_ORDER = [
    (ParameterType.SCALAR,      "标量参数 (Scalar)"),
    (ParameterType.CURVE,       "一维曲线 (1D Curve)"),
    (ParameterType.FIXED_CURVE, "固定一维曲线"),
    (ParameterType.MAP,         "二维图 (2D Map)"),
    (ParameterType.FIXED_MAP,   "固定二维图"),
    (ParameterType.GROUP_CURVE, "组一维曲线"),
    (ParameterType.GROUP_MAP,   "组二维图"),
    (ParameterType.DISTRIBUTION,"分布"),
    (ParameterType.GROUP_PARAM, "组参数"),
    (ParameterType.TEXT,        "文本"),
]


class LoadThread(QThread):
    """Background thread for loading DCM files."""
    finished = pyqtSignal(object, str)
    error = pyqtSignal(str)

    def __init__(self, path: str):
        super().__init__()
        self.path = path

    def run(self):
        try:
            dcm = parse_dcm(self.path)
            self.finished.emit(dcm, self.path)
        except Exception as e:
            self.error.emit(str(e))


class ParamTreeWidget(QWidget):
    """Left panel: parameter tree with search."""
    param_selected = pyqtSignal(str)
    param_delete_requested = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.search = QLineEdit()
        self.search.setPlaceholderText("🔍 搜索参数…")
        self.search.textChanged.connect(self._filter)
        layout.addWidget(self.search)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabel("参数列表")
        self.tree.setColumnCount(2)
        self.tree.setHeaderLabels(["参数名称", "类型"])
        self.tree.header().setStretchLastSection(False)
        self.tree.header().setDefaultSectionSize(160)
        self.tree.setAlternatingRowColors(True)
        self.tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.tree.itemSelectionChanged.connect(self._on_select)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._context_menu)
        layout.addWidget(self.tree)

        self._dcm: Optional[DCMFile] = None
        self._group_items: Dict[str, QTreeWidgetItem] = {}

    def load_dcm(self, dcm: DCMFile):
        self._dcm = dcm
        self.tree.clear()
        self._group_items.clear()

        for ptype, label in _GROUP_ORDER:
            params = dcm.get_by_type(ptype)
            if not params:
                continue
            group = QTreeWidgetItem([f"{label}  ({len(params)})", ""])
            font = group.font(0)
            font.setBold(True)
            group.setFont(0, font)
            self.tree.addTopLevelItem(group)
            self._group_items[ptype.value] = group
            for name in sorted(params.keys()):
                child = QTreeWidgetItem([name, ptype.value])
                child.setData(0, Qt.UserRole, name)
                child.setToolTip(0, params[name].long_name or name)
                group.addChild(child)
            group.setExpanded(True)
        self.search.clear()

    def _on_select(self):
        items = self.tree.selectedItems()
        if not items:
            return
        # Only leaf items represent actual parameters
        name = items[0].data(0, Qt.UserRole)
        if name:
            self.param_selected.emit(name)

    def _filter(self, text: str):
        text = text.lower()
        root = self.tree.invisibleRootItem()
        for gi in range(root.childCount()):
            group = root.child(gi)
            any_visible = False
            for ci in range(group.childCount()):
                child = group.child(ci)
                name = (child.data(0, Qt.UserRole) or "").lower()
                visible = not text or text in name
                child.setHidden(not visible)
                if visible:
                    any_visible = True
            group.setHidden(not any_visible)

    def _context_menu(self, pos):
        items = self.tree.selectedItems()
        names = [it.data(0, Qt.UserRole) for it in items if it.data(0, Qt.UserRole)]
        if not names:
            return
        menu = QMenu(self)
        del_action = menu.addAction(f"删除选中 ({len(names)} 个参数)")
        action = menu.exec_(self.tree.viewport().mapToGlobal(pos))
        if action == del_action:
            self.param_delete_requested.emit(names)

    def select_param(self, name: str):
        root = self.tree.invisibleRootItem()
        for gi in range(root.childCount()):
            group = root.child(gi)
            for ci in range(group.childCount()):
                child = group.child(ci)
                if child.data(0, Qt.UserRole) == name:
                    self.tree.setCurrentItem(child)
                    return


class SelectParamsDialog(QDialog):
    """Dialog for selecting parameters to keep/export."""

    def __init__(self, dcm: DCMFile, parent=None):
        super().__init__(parent)
        self.setWindowTitle("选择要保留的参数")
        self.setMinimumSize(500, 600)
        layout = QVBoxLayout(self)

        info = QLabel(f"共 {len(dcm.parameters)} 个参数，选择要保留在新文件中的参数：")
        layout.addWidget(info)

        # Search
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索…")
        self.search.textChanged.connect(self._filter)
        layout.addWidget(self.search)

        # Select all / none
        btn_row = QHBoxLayout()
        all_btn = QPushButton("全选")
        none_btn = QPushButton("全不选")
        inv_btn = QPushButton("反选")
        all_btn.clicked.connect(self._select_all)
        none_btn.clicked.connect(self._select_none)
        inv_btn.clicked.connect(self._invert)
        btn_row.addWidget(all_btn)
        btn_row.addWidget(none_btn)
        btn_row.addWidget(inv_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QAbstractItemView.MultiSelection)
        layout.addWidget(self.list_widget)

        # Populate sorted by type then name
        self._all_items = []
        for ptype, _ in _GROUP_ORDER:
            params = dcm.get_by_type(ptype)
            for name in sorted(params.keys()):
                item = QListWidgetItem(f"{_TYPE_ICONS.get(ptype,'·')} {name}")
                item.setData(Qt.UserRole, name)
                item.setCheckState(Qt.Checked)
                self.list_widget.addItem(item)
                self._all_items.append(item)

        self.count_lbl = QLabel()
        layout.addWidget(self.count_lbl)
        self._update_count()
        self.list_widget.itemChanged.connect(lambda: self._update_count())

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        layout.addWidget(bb)

    def selected_names(self):
        return [
            item.data(Qt.UserRole)
            for item in self._all_items
            if item.checkState() == Qt.Checked
            and not item.isHidden()
        ]

    def _update_count(self):
        n = sum(1 for it in self._all_items
                if it.checkState() == Qt.Checked and not it.isHidden())
        self.count_lbl.setText(f"已选择: {n} 个参数")

    def _select_all(self):
        for it in self._all_items:
            if not it.isHidden():
                it.setCheckState(Qt.Checked)

    def _select_none(self):
        for it in self._all_items:
            it.setCheckState(Qt.Unchecked)

    def _invert(self):
        for it in self._all_items:
            if not it.isHidden():
                it.setCheckState(
                    Qt.Unchecked if it.checkState() == Qt.Checked else Qt.Checked
                )

    def _filter(self, text: str):
        text = text.lower()
        for it in self._all_items:
            name = (it.data(Qt.UserRole) or "").lower()
            it.setHidden(bool(text) and text not in name)
        self._update_count()


class DCMEditorTab(QWidget):
    """A single DCM file editor tab."""
    title_changed = pyqtSignal(str)
    modified_changed = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._dcm: Optional[DCMFile] = None
        self._modified = False
        self._current_param_name: Optional[str] = None

        splitter = QSplitter(Qt.Horizontal, self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(splitter)

        # Left: param tree
        self.tree_widget = ParamTreeWidget()
        self.tree_widget.setMinimumWidth(240)
        self.tree_widget.setMaximumWidth(340)
        splitter.addWidget(self.tree_widget)

        # Right: editor
        self.editor = ParameterEditorPanel()
        splitter.addWidget(self.editor)
        splitter.setSizes([280, 720])

        self.tree_widget.param_selected.connect(self._on_param_selected)
        self.tree_widget.param_delete_requested.connect(self._delete_params)
        self.editor.modified.connect(self._on_param_modified)

    def load_dcm(self, dcm: DCMFile):
        self._dcm = dcm
        self._modified = False
        self.tree_widget.load_dcm(dcm)
        self.editor.clear()
        self._current_param_name = None
        name = Path(dcm.file_path).name if dcm.file_path else "新文件"
        self.title_changed.emit(name)

    def _on_param_selected(self, name: str):
        if self._dcm is None:
            return
        param = self._dcm.parameters.get(name)
        if param:
            self._current_param_name = name
            self.editor.load_param(param)

    def _on_param_modified(self, name: str):
        self._modified = True
        self.modified_changed.emit(True)

    def _delete_params(self, names: list):
        if not self._dcm:
            return
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除选中的 {len(names)} 个参数吗？\n此操作不可撤销。",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        for name in names:
            self._dcm.parameters.pop(name, None)
            if name in self._dcm.order:
                self._dcm.order.remove(name)
        self.tree_widget.load_dcm(self._dcm)
        self.editor.clear()
        self._modified = True
        self.modified_changed.emit(True)

    def save(self, path: Optional[str] = None) -> bool:
        if self._dcm is None:
            return False
        target = path or self._dcm.file_path
        if not target:
            return False
        try:
            write_dcm(self._dcm, target)
            self._dcm.file_path = target
            self._modified = False
            self.modified_changed.emit(False)
            self.title_changed.emit(Path(target).name)
            return True
        except Exception as e:
            QMessageBox.critical(self, "保存失败", str(e))
            return False

    @property
    def dcm(self) -> Optional[DCMFile]:
        return self._dcm

    @property
    def is_modified(self) -> bool:
        return self._modified


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DCM 标定数据管理工具")
        self.setMinimumSize(1100, 720)
        self.setStyleSheet(MAIN_STYLE)

        self._load_threads: list = []
        self._compare_diff: Optional[DCMDiff] = None

        self._build_menu()
        self._build_toolbar()
        self._build_central()
        self._build_statusbar()

    # ------------------------------------------------------------------ UI build

    def _build_menu(self):
        mb = self.menuBar()

        # File
        file_menu = mb.addMenu("文件(&F)")
        self._act_open = file_menu.addAction("打开 DCM…")
        self._act_open.setShortcut(QKeySequence.Open)
        self._act_open.triggered.connect(self.open_file)

        file_menu.addSeparator()
        self._act_save = file_menu.addAction("保存")
        self._act_save.setShortcut(QKeySequence.Save)
        self._act_save.triggered.connect(self.save_current)

        self._act_save_as = file_menu.addAction("另存为…")
        self._act_save_as.setShortcut(QKeySequence("Ctrl+Shift+S"))
        self._act_save_as.triggered.connect(self.save_as_current)

        self._act_export = file_menu.addAction("导出选定参数…")
        self._act_export.triggered.connect(self.export_selected_params)

        file_menu.addSeparator()
        file_menu.addAction("退出").triggered.connect(self.close)

        # Tools
        tools_menu = mb.addMenu("工具(&T)")
        self._act_compare = tools_menu.addAction("对比两个 DCM 文件…")
        self._act_compare.setShortcut(QKeySequence("Ctrl+D"))
        self._act_compare.triggered.connect(self.compare_files)

        self._act_merge = tools_menu.addAction("合并 DCM 文件…")
        self._act_merge.triggered.connect(self.merge_files)

        # View
        view_menu = mb.addMenu("视图(&V)")
        view_menu.addAction("关闭当前标签").triggered.connect(self._close_current_tab)

        # Help
        help_menu = mb.addMenu("帮助(&H)")
        help_menu.addAction("关于").triggered.connect(self._show_about)

    def _build_toolbar(self):
        tb = QToolBar("主工具栏", self)
        tb.setMovable(False)
        tb.setIconSize(QSize(18, 18))
        self.addToolBar(tb)

        open_act = QAction("📂 打开", self)
        open_act.setToolTip("打开 DCM 文件 (Ctrl+O)")
        open_act.triggered.connect(self.open_file)
        tb.addAction(open_act)

        save_act = QAction("💾 保存", self)
        save_act.setToolTip("保存当前文件 (Ctrl+S)")
        save_act.triggered.connect(self.save_current)
        tb.addAction(save_act)

        save_as_act = QAction("📋 另存为", self)
        save_as_act.triggered.connect(self.save_as_current)
        tb.addAction(save_as_act)

        tb.addSeparator()

        compare_act = QAction("⚖ 对比", self)
        compare_act.setToolTip("对比两个 DCM 文件 (Ctrl+D)")
        compare_act.triggered.connect(self.compare_files)
        tb.addAction(compare_act)

        merge_act = QAction("🔀 合并", self)
        merge_act.setToolTip("合并两个 DCM 文件")
        merge_act.triggered.connect(self.merge_files)
        tb.addAction(merge_act)

        tb.addSeparator()

        export_act = QAction("✂ 导出参数", self)
        export_act.setToolTip("选择并导出参数子集")
        export_act.triggered.connect(self.export_selected_params)
        tb.addAction(export_act)

    def _build_central(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(0)

        self.tab_widget = QTabWidget()
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.tabCloseRequested.connect(self._close_tab)
        self.tab_widget.currentChanged.connect(self._on_tab_changed)
        layout.addWidget(self.tab_widget)

        # Welcome screen
        self._show_welcome()

    def _show_welcome(self):
        welcome = QWidget()
        wl = QVBoxLayout(welcome)
        wl.setAlignment(Qt.AlignCenter)
        title = QLabel("DCM 标定数据管理工具")
        title.setObjectName("titleLabel")
        title.setAlignment(Qt.AlignCenter)
        font = title.font()
        font.setPointSize(22)
        title.setFont(font)
        wl.addWidget(title)
        wl.addSpacing(16)
        sub = QLabel("支持 Vector CANape / INCA 生成的 DCM 标定文件\n打开文件开始使用")
        sub.setAlignment(Qt.AlignCenter)
        sub.setObjectName("sectionLabel")
        wl.addWidget(sub)
        wl.addSpacing(24)
        btn_row = QHBoxLayout()
        btn_row.setAlignment(Qt.AlignCenter)
        open_btn = QPushButton("📂  打开 DCM 文件")
        open_btn.setObjectName("primaryBtn")
        open_btn.setMinimumSize(160, 40)
        open_btn.clicked.connect(self.open_file)
        cmp_btn = QPushButton("⚖  对比两个文件")
        cmp_btn.setMinimumSize(160, 40)
        cmp_btn.clicked.connect(self.compare_files)
        btn_row.addWidget(open_btn)
        btn_row.addSpacing(12)
        btn_row.addWidget(cmp_btn)
        wl.addLayout(btn_row)
        self.tab_widget.addTab(welcome, "欢迎")
        self.tab_widget.tabBar().setTabButton(0, self.tab_widget.tabBar().RightSide, None)

    def _build_statusbar(self):
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.status_lbl = QLabel("就绪")
        self.status.addWidget(self.status_lbl)
        self.param_count_lbl = QLabel()
        self.status.addPermanentWidget(self.param_count_lbl)

    # ------------------------------------------------------------------ file ops

    def open_file(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "打开 DCM 文件", "",
            "DCM Files (*.dcm);;All Files (*)"
        )
        for path in paths:
            self._load_file(path)

    def _load_file(self, path: str):
        self.status_lbl.setText(f"正在加载: {Path(path).name} …")
        QApplication.processEvents()
        thread = LoadThread(path)
        thread.finished.connect(self._on_load_finished)
        thread.error.connect(self._on_load_error)
        self._load_threads.append(thread)
        thread.start()

    def _on_load_finished(self, dcm: DCMFile, path: str):
        tab = DCMEditorTab()
        tab.load_dcm(dcm)
        tab.title_changed.connect(lambda t, w=tab: self._update_tab_title(w, t))
        tab.modified_changed.connect(lambda m, w=tab: self._update_tab_modified(w, m))
        name = Path(path).name
        idx = self.tab_widget.addTab(tab, name)
        self.tab_widget.setCurrentIndex(idx)
        stats = dcm.stats()
        self.status_lbl.setText(
            f"已加载: {name}  |  {stats['total']} 个参数  "
            f"(标量:{stats['scalar']}  一维:{stats['curve']}  二维:{stats['map']})"
        )
        self._update_param_count(dcm)

    def _on_load_error(self, msg: str):
        self.status_lbl.setText("加载失败")
        QMessageBox.critical(self, "加载错误", f"无法解析 DCM 文件:\n{msg}")

    def save_current(self):
        tab = self._current_editor_tab()
        if tab is None:
            return
        if not tab.dcm or not tab.dcm.file_path:
            self.save_as_current()
            return
        if tab.save():
            self.status_lbl.setText(f"已保存: {Path(tab.dcm.file_path).name}")

    def save_as_current(self):
        tab = self._current_editor_tab()
        if tab is None or tab.dcm is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "另存为", "", "DCM Files (*.dcm);;All Files (*)"
        )
        if path:
            if not path.lower().endswith(".dcm"):
                path += ".dcm"
            if tab.save(path):
                self.status_lbl.setText(f"已另存为: {Path(path).name}")

    def export_selected_params(self):
        tab = self._current_editor_tab()
        if tab is None or tab.dcm is None:
            QMessageBox.information(self, "提示", "请先打开一个 DCM 文件。")
            return
        dlg = SelectParamsDialog(tab.dcm, self)
        if dlg.exec_() != QDialog.Accepted:
            return
        names = dlg.selected_names()
        if not names:
            QMessageBox.warning(self, "提示", "未选择任何参数。")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "保存导出文件", "", "DCM Files (*.dcm);;All Files (*)"
        )
        if not path:
            return
        if not path.lower().endswith(".dcm"):
            path += ".dcm"
        import copy
        new_dcm = copy.deepcopy(tab.dcm)
        new_dcm.parameters = {n: new_dcm.parameters[n] for n in names if n in new_dcm.parameters}
        new_dcm.order = [n for n in new_dcm.order if n in new_dcm.parameters]
        new_dcm.file_path = path
        try:
            write_dcm(new_dcm, path)
            QMessageBox.information(self, "导出完成",
                f"导出成功！\n共导出 {len(new_dcm.parameters)} 个参数。\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "导出失败", str(e))

    # ------------------------------------------------------------------ compare

    def compare_files(self):
        # If 2 editor tabs are open, use them; otherwise prompt for files
        editor_tabs = [
            self.tab_widget.widget(i)
            for i in range(self.tab_widget.count())
            if isinstance(self.tab_widget.widget(i), DCMEditorTab)
               and self.tab_widget.widget(i).dcm is not None
        ]

        left_dcm = right_dcm = None
        left_path = right_path = ""

        if len(editor_tabs) >= 2:
            reply = QMessageBox.question(
                self, "选择文件来源",
                f"检测到已打开 {len(editor_tabs)} 个 DCM 文件。\n"
                "是否对比当前已打开的前两个文件？\n\n"
                "（选"否"以手动选择文件）",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply == QMessageBox.Yes:
                left_dcm = editor_tabs[0].dcm
                right_dcm = editor_tabs[1].dcm
                left_path = left_dcm.file_path
                right_path = right_dcm.file_path

        if left_dcm is None:
            left_path, _ = QFileDialog.getOpenFileName(
                self, "选择左侧 DCM 文件", "", "DCM Files (*.dcm);;All Files (*)"
            )
            if not left_path:
                return
            right_path, _ = QFileDialog.getOpenFileName(
                self, "选择右侧 DCM 文件", "", "DCM Files (*.dcm);;All Files (*)"
            )
            if not right_path:
                return
            try:
                self.status_lbl.setText("正在加载对比文件…")
                QApplication.processEvents()
                left_dcm = parse_dcm(left_path)
                right_dcm = parse_dcm(right_path)
            except Exception as e:
                QMessageBox.critical(self, "加载失败", str(e))
                return

        self.status_lbl.setText("正在对比…")
        QApplication.processEvents()
        diff = compare_dcm(left_dcm, right_dcm)
        self._compare_diff = diff
        self._compare_left = left_dcm
        self._compare_right = right_dcm

        # Add compare tab
        view = CompareView()
        view.load(diff)
        stats = diff.stats()
        tab_label = f"对比: {Path(left_path).stem} ↔ {Path(right_path).stem}"
        idx = self.tab_widget.addTab(view, "⚖ " + tab_label)
        self.tab_widget.setCurrentIndex(idx)
        self.status_lbl.setText(
            f"对比完成: 共 {stats['total']} 个参数  "
            f"修改:{stats['modified']}  仅左:{stats['only_left']}  "
            f"仅右:{stats['only_right']}  相同:{stats['identical']}"
        )

    # ------------------------------------------------------------------ merge

    def merge_files(self):
        left_dcm = right_dcm = None
        diff = None
        per_param = {}

        # If a compare tab is open use its data
        cur = self.tab_widget.currentWidget()
        if isinstance(cur, CompareView) and self._compare_diff:
            diff = self._compare_diff
            left_dcm = self._compare_left
            right_dcm = self._compare_right
            per_param = cur.get_strategies()

        if left_dcm is None:
            # Prompt for files
            left_path, _ = QFileDialog.getOpenFileName(
                self, "选择左侧 DCM 文件", "", "DCM Files (*.dcm);;All Files (*)"
            )
            if not left_path:
                return
            right_path, _ = QFileDialog.getOpenFileName(
                self, "选择右侧 DCM 文件", "", "DCM Files (*.dcm);;All Files (*)"
            )
            if not right_path:
                return
            try:
                left_dcm = parse_dcm(left_path)
                right_dcm = parse_dcm(right_path)
                diff = compare_dcm(left_dcm, right_dcm)
            except Exception as e:
                QMessageBox.critical(self, "加载失败", str(e))
                return

        dlg = MergeDialog(left_dcm, right_dcm, diff, per_param, self)
        dlg.exec_()

    # ------------------------------------------------------------------ helpers

    def _current_editor_tab(self) -> Optional[DCMEditorTab]:
        w = self.tab_widget.currentWidget()
        return w if isinstance(w, DCMEditorTab) else None

    def _close_tab(self, idx: int):
        w = self.tab_widget.widget(idx)
        if isinstance(w, DCMEditorTab) and w.is_modified:
            reply = QMessageBox.question(
                self, "未保存的修改",
                "当前文件有未保存的修改，确定要关闭吗？",
                QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
            )
            if reply == QMessageBox.Cancel:
                return
            if reply == QMessageBox.Save:
                w.save()
        self.tab_widget.removeTab(idx)

    def _close_current_tab(self):
        idx = self.tab_widget.currentIndex()
        if idx >= 0:
            self._close_tab(idx)

    def _on_tab_changed(self, idx: int):
        w = self.tab_widget.widget(idx)
        if isinstance(w, DCMEditorTab) and w.dcm:
            self._update_param_count(w.dcm)
        else:
            self.param_count_lbl.clear()

    def _update_tab_title(self, tab: QWidget, title: str):
        idx = self.tab_widget.indexOf(tab)
        if idx >= 0:
            self.tab_widget.setTabText(idx, title)

    def _update_tab_modified(self, tab: QWidget, modified: bool):
        idx = self.tab_widget.indexOf(tab)
        if idx >= 0:
            text = self.tab_widget.tabText(idx)
            if modified and not text.endswith(" *"):
                self.tab_widget.setTabText(idx, text + " *")
            elif not modified and text.endswith(" *"):
                self.tab_widget.setTabText(idx, text[:-2])

    def _update_param_count(self, dcm: DCMFile):
        s = dcm.stats()
        self.param_count_lbl.setText(
            f"参数总数: {s['total']}  |  "
            f"标量: {s['scalar']}  一维: {s['curve']}  二维: {s['map']}"
        )

    def _show_about(self):
        QMessageBox.about(
            self, "关于 DCM 工具",
            "<b>DCM 标定数据管理工具</b><br><br>"
            "支持 Vector CANape / INCA 格式 DCM 文件<br>"
            "功能：打开、编辑、对比、合并、导出参数子集<br><br>"
            "可视化：一维曲线图、二维热力图<br>"
            "支持参数类型：标量、一维曲线、二维图及固定型变体"
        )

    def closeEvent(self, event):
        for i in range(self.tab_widget.count()):
            w = self.tab_widget.widget(i)
            if isinstance(w, DCMEditorTab) and w.is_modified:
                reply = QMessageBox.question(
                    self, "未保存的修改",
                    "有文件存在未保存的修改，确定要退出吗？",
                    QMessageBox.Yes | QMessageBox.No,
                )
                if reply == QMessageBox.No:
                    event.ignore()
                    return
                break
        event.accept()
