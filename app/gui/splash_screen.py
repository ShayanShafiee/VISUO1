# --- gui/splash_screen.py ---

from PyQt6.QtWidgets import QApplication
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget
from PyQt6.QtCore import Qt, QUrl

# Inherit directly from QVideoWidget for a borderless video player
class SplashScreen(QVideoWidget):
    def __init__(self, video_path: str):
        super().__init__()
        self.video_path = video_path
        self.main_window = None
        self.main_window_ready = False
        self.video_finished = False

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(960, 540)
        self.center_on_screen()

        # Simplified Multimedia Setup
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()

        self.player.setAudioOutput(self.audio_output)
        self.player.setVideoOutput(self) # The video output is this widget itself
        self.player.setSource(QUrl.fromLocalFile(self.video_path))
        self.audio_output.setMuted(True)

        # Connect the signal for when the video's status changes
        self.player.mediaStatusChanged.connect(self._handle_media_status)

    def center_on_screen(self):
        screen_geo = QApplication.primaryScreen().geometry()
        self.move(
            (screen_geo.width() - self.width()) // 2,
            (screen_geo.height() - self.height()) // 2
        )

    def play_animation(self):
        self.player.play()

    def set_main_window(self, window):
        """Receives the main window instance once it has finished loading."""
        self.main_window = window
        self.main_window_ready = True
        
        # This handles the case where the main app loads *after* the video has already finished
        if self.video_finished:
            self.show_main_window_and_close()

    def _handle_media_status(self, status):
        """This function is called when the video player's state changes."""
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self.video_finished = True
            
            # This handles the case where the video finishes *after* the main app has already loaded
            if self.main_window_ready:
                self.show_main_window_and_close()
    
    def show_main_window_and_close(self):
        """A single, clean function to perform the transition."""
        if self.main_window:
            self.main_window.showFullScreen()
        self.close()