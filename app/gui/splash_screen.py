# gui/splash_screen.py


"""Splash screen video player.

Shows a frameless, centered video (muted) while the main window initializes.
Transitions automatically to the application on:
 - End of media
 - Explicit error / invalid media
 - Fallback timeout (stalled backend)

Usage:
    splash = SplashScreen(path_to_mp4)
    splash.show(); splash.play_animation()
    # Later, once MainWindow is constructed:
    splash.set_main_window(main_window)

If initialization finishes after the video ends, the transition happens as
soon as the main window is marked ready. Defensive fallbacks ensure the user
is never left with a stuck splash screen.
"""

from PyQt6.QtWidgets import QApplication, QGraphicsDropShadowEffect
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget
from PyQt6.QtCore import Qt, QUrl, QTimer
from PyQt6.QtGui import QColor

# Inherit directly from QVideoWidget for a borderless video player
class SplashScreen(QVideoWidget):
    def __init__(self, video_path: str):
        super().__init__()
        self.video_path = video_path
        self.main_window = None
        self.main_window_ready = False
        self.video_finished = False
        self._fallback_started = False

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(960, 540)
        self.center_on_screen()

        # Subtle shadow only (rounded corners removed)
        self._add_shadow()

        # Simplified Multimedia Setup
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()

        self.player.setAudioOutput(self.audio_output)
        self.player.setVideoOutput(self) # The video output is this widget itself
        self.player.setSource(QUrl.fromLocalFile(self.video_path))
        self.audio_output.setMuted(True)

        # Connect the signal for when the video's status changes
        self.player.mediaStatusChanged.connect(self._handle_media_status)
        # Best-effort error hook (available on Qt 6.4+). If unavailable, ignore.
        try:
            # type: ignore[attr-defined]
            self.player.errorOccurred.connect(self._handle_error)  # pyright: ignore
        except Exception:
            pass

        # Fallback timer to avoid hanging if multimedia backend fails
        self._fallback_timer = QTimer(self)
        self._fallback_timer.setSingleShot(True)
        self._fallback_timer.timeout.connect(self._fallback_timeout)

    def _add_shadow(self):
        effect = QGraphicsDropShadowEffect(self)
        effect.setBlurRadius(40)
        effect.setOffset(0, 0)
        effect.setColor(QColor(0, 0, 0, 120))
        self.setGraphicsEffect(effect)

    def center_on_screen(self):
        screen_geo = QApplication.primaryScreen().geometry()
        self.move(
            (screen_geo.width() - self.width()) // 2,
            (screen_geo.height() - self.height()) // 2
        )

    def play_animation(self):
        # Start playback and also arm a fallback in case media doesn't progress
        print("Splash: starting video playback…")
        self.player.play()
        self._start_fallback_timer()

    def set_main_window(self, window):
        """Receives the main window instance once it has finished loading."""
        self.main_window = window
        self.main_window_ready = True
        
        # This handles the case where the main app loads *after* the video has already finished
        if self.video_finished:
            self.show_main_window_and_close()

    def _handle_media_status(self, status):
        """This function is called when the video player's state changes."""
        # Any definitive end or invalid state should transition the app.
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            print("Splash: video reached EndOfMedia.")
            self.video_finished = True
            self._fallback_timer.stop()
            if self.main_window_ready:
                self.show_main_window_and_close()
        elif status in (QMediaPlayer.MediaStatus.InvalidMedia,
                        QMediaPlayer.MediaStatus.NoMedia):
            print(f"Splash: media status indicates failure ({status}). Falling back.")
            self.video_finished = True
            self._fallback_timer.stop()
            if self.main_window_ready:
                self.show_main_window_and_close()
            else:
                # Keep fallback armed; transition will happen when main window arrives
                self._start_fallback_timer(short=True)
        else:
            # If we stall or encounter an unknown status (older Qt may lack UnknownMediaStatus), arm fallback
            try:
                stall_like = [QMediaPlayer.MediaStatus.StalledMedia]
                unknown = getattr(QMediaPlayer.MediaStatus, 'UnknownMediaStatus', None)
                if unknown is not None:
                    stall_like.append(unknown)
                if status in tuple(stall_like):
                    print("Splash: media stalled or unknown status; arming fallback.")
                    self._start_fallback_timer()
            except Exception:
                # Be conservative: keep fallback armed
                self._start_fallback_timer()

    def _handle_error(self, error):
        try:
            err_enum = getattr(QMediaPlayer, 'Error', None)
            if err_enum is not None and error != err_enum.NoError:
                print(f"Splash: QMediaPlayer errorOccurred -> {error}. Triggering fallback.")
        except Exception:
            print("Splash: QMediaPlayer reported an error. Triggering fallback.")
        self.video_finished = True
        self._fallback_timer.stop()
        if self.main_window_ready:
            self.show_main_window_and_close()
        else:
            self._start_fallback_timer(short=True)

    def _start_fallback_timer(self, short: bool = False):
        # Start only once or re-arm with shorter timeout when needed
        timeout_ms = 2500 if short else 6000
        self._fallback_started = True
        # Restart timer each call to extend/shorten as needed
        self._fallback_timer.start(timeout_ms)

    def _fallback_timeout(self):
        # As a last resort, proceed even if media never reports EndOfMedia
        print("Splash: fallback timeout reached. Proceeding to main window.")
        self.video_finished = True
        if self.main_window_ready:
            self.show_main_window_and_close()
    
    def show_main_window_and_close(self):
        """A single, clean function to perform the transition."""
        if self.main_window:
            self.main_window.showFullScreen()
        # Stop playback and release resources defensively
        try:
            self.player.stop()
        except Exception:
            pass
        self._fallback_timer.stop()
        self.close()

    # No rounded-corner mask to maintain on resize