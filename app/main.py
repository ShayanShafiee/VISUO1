# main.py ---

import sys
from PyQt6.QtWidgets import QApplication
from gui.main_window import MainWindow

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    
    # Instead of window.show(), which shows a normal window,
    # we use window.showFullScreen() to launch it in fullscreen mode.
    window.showFullScreen()
    
    sys.exit(app.exec())