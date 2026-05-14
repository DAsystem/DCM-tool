"""
DCM 标定数据管理工具 - 入口
DCM Calibration Data Management Tool - Entry Point
"""
import sys
import os

# Ensure high-DPI scaling works well on Windows
os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "1")

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont

from gui.main_window import MainWindow


def main():
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName("DCM 标定管理工具")
    app.setOrganizationName("DCMTool")

    # Default font — prefer system CJK font on Windows
    font = QFont()
    for family in ("Microsoft YaHei", "Segoe UI", "Arial"):
        font.setFamily(family)
        if QFont(family).exactMatch():
            break
    font.setPointSize(10)
    app.setFont(font)

    win = MainWindow()
    win.show()

    # If a file was passed on the command line, open it
    for arg in sys.argv[1:]:
        if os.path.isfile(arg):
            win._load_file(arg)

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
