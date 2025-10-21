# --- main.py ---

import sys
import os
import atexit
import tempfile
import psutil
from PyQt6.QtWidgets import QApplication, QMessageBox
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
    # --- MODIFIED: Create QApplication FIRST ---
    # This is essential for the QMessageBox to work.
    app = QApplication(sys.argv)

    # --- MODIFIED: New single-instance workflow ---
    if not check_for_previous_instance():
        # User cancelled, so exit cleanly.
        sys.exit(0)
    
    # If we got here, it's safe to launch. Create the lock file.
    create_lock_file()
    # --- END MODIFICATION ---

    app.setApplicationName("VISUO1")
    try:
        app.setApplicationDisplayName("VISUO1")
    except Exception:
        pass

    # The rest of the launch logic is unchanged
    current_dir = os.path.dirname(os.path.abspath(__file__))
    video_path = os.path.join(current_dir, 'assets', 'logo_animation.mp4')
    
    if SHOW_SPLASH_SCREEN and os.path.exists(video_path):
        splash = SplashScreen(video_path)
        splash.show()
        splash.play_animation()
        
        window = MainWindow()
        splash.set_main_window(window)
        
    else:
        if SHOW_SPLASH_SCREEN and not os.path.exists(video_path):
             print(f"Warning: Splash screen video not found at '{video_path}'.")
             
        window = MainWindow()
        window.showFullScreen()
    
    sys.exit(app.exec())