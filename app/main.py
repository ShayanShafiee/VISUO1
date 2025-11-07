# app/main.py


"""Application entry point.

Responsibilities:
1. Enforce a single running instance via a PID lock file (with user choice to restart or cancel).
2. Initialize QApplication, optional splash screen, window icon, and resource paths.
3. Construct and show the MainWindow and begin the Qt event loop.

Design highlights:
- Lock file lives in system temp directory; stale locks are ignored.
- If an instance is running, user can terminate it from a dialog (helpful when a hidden window remains).
- Uses a helper to generate a rounded icon from a square PNG for a polished appearance.

Comment style avoids change-log wording; focus stays on purpose and flow.
"""

import sys
import os
import atexit
import tempfile
import psutil
from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QPainterPath
from PyQt6.QtCore import Qt
from gui.main_window import MainWindow
from gui.splash_screen import SplashScreen

# --- Single-Instance Lock File Logic ---

LOCK_FILE_PATH = os.path.join(tempfile.gettempdir(), "visuo1.lock")

def remove_lock_file():
    """This function is automatically called on a clean program exit."""
    try:
        if os.path.exists(LOCK_FILE_PATH):
            os.remove(LOCK_FILE_PATH)
    except OSError as e:
        print(f"Warning: Could not remove lock file. {e}")

def check_for_previous_instance() -> bool:
    """
    Checks for a previous instance. If found, asks the user what to do.
    Returns True if the app should proceed, False if it should exit.
    """
    if not os.path.exists(LOCK_FILE_PATH):
        return True # No lock file, so we can proceed.

    try:
        with open(LOCK_FILE_PATH, 'r') as f:
            old_pid = int(f.read())
    except (IOError, ValueError):
        # The lock file is corrupt or unreadable, so we can ignore it.
        return True

    # Check if a process with that PID is actually running
    if not psutil.pid_exists(old_pid):
        return True # The lock file is stale, so we can proceed.

    # --- An instance is already running. Ask the user what to do. ---
    msg_box = QMessageBox()
    msg_box.setIcon(QMessageBox.Icon.Warning)
    msg_box.setWindowTitle("Instance Already Running")
    msg_box.setText("Another instance of VISUO1 is already open.")
    msg_box.setInformativeText("Do you want to close the existing instance and start a new one?")
    
    # Create custom buttons for clear actions
    restart_button = msg_box.addButton("Close & Restart", QMessageBox.ButtonRole.AcceptRole)
    cancel_button = msg_box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
    
    msg_box.exec()

    if msg_box.clickedButton() == cancel_button:
        # User chose to cancel, so the new instance should exit.
        return False
    
    # User chose to restart. Terminate the old process.
    print(f"User chose to restart. Terminating previous instance with PID: {old_pid}.")
    try:
        old_process = psutil.Process(old_pid)
        old_process.terminate()
        old_process.wait(timeout=3) # Wait up to 3 seconds for it to close
    except (psutil.NoSuchProcess, psutil.TimeoutExpired) as e:
        print(f"Warning: Could not terminate previous instance cleanly. It may have already closed. Error: {e}")

    return True # We can now proceed with launching.

def create_lock_file():
    """Writes the current process's PID to the lock file."""
    # Register our cleanup function to run when the app exits gracefully
    atexit.register(remove_lock_file)
    with open(LOCK_FILE_PATH, 'w') as f:
        f.write(str(os.getpid()))

# --- End of Single-Instance Logic ---


# Debug Toggle for Splash Screen
SHOW_SPLASH_SCREEN = True

if __name__ == '__main__':
    # This is essential for the QMessageBox to work.
    app = QApplication(sys.argv)

    # Single-instance guard: ask user if an earlier instance should be closed.
    if not check_for_previous_instance():
        # User cancelled, so exit cleanly.
        sys.exit(0)
    
    # If we got here, it's safe to launch. Create the lock file.
    create_lock_file()

    app.setApplicationName("VISUO1")
    try:
        app.setApplicationDisplayName("VISUO1")
    except Exception:
        pass

    # Resolve asset paths for script and bundled (PyInstaller) execution
    current_dir = os.path.dirname(os.path.abspath(__file__))
    base_dir = getattr(sys, '_MEIPASS', current_dir)

    # App icon (rounded corners)
    def _make_rounded_icon(png_path: str, radius: int = 24) -> QIcon:
        if not os.path.exists(png_path):
            return QIcon()
        pix = QPixmap(png_path)
        if pix.isNull():
            return QIcon()
        size = min(pix.width(), pix.height())
        if size <= 0:
            return QIcon()
        # Scale/crop to square
        square = pix.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                            Qt.TransformationMode.SmoothTransformation)
        rounded = QPixmap(size, size)
        rounded.fill(Qt.GlobalColor.transparent)
        painter = QPainter(rounded)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        path = QPainterPath()
        path.addRoundedRect(0.0, 0.0, float(size), float(size), float(radius), float(radius))
        painter.setClipPath(path)
        painter.drawPixmap(0, 0, square)
        painter.end()
        return QIcon(rounded)

    icon_path = os.path.join(base_dir, 'assets', 'Icon.png')
    icon = _make_rounded_icon(icon_path, radius=24)
    if not icon.isNull():
        app.setWindowIcon(icon)
    else:
        print(f"Warning: App icon not found or invalid at '{icon_path}'.")

    # Splash video
    video_path = os.path.join(base_dir, 'assets', 'logo_animation.mp4')
    
    if SHOW_SPLASH_SCREEN and os.path.exists(video_path):
        splash = SplashScreen(video_path)
        splash.show()
        splash.play_animation()
        
        window = MainWindow()
        # Ensure main window also carries the app icon
        if not icon.isNull():
            window.setWindowIcon(icon)
        splash.set_main_window(window)
        
    else:
        if SHOW_SPLASH_SCREEN and not os.path.exists(video_path):
             print(f"Warning: Splash screen video not found at '{video_path}'.")
             
        window = MainWindow()
        if not icon.isNull():
            window.setWindowIcon(icon)
        window.showFullScreen()
    
    sys.exit(app.exec())