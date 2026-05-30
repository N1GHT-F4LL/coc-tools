import logging
import threading
import traceback

import cv2
import numpy as np
from PyQt5.QtCore import QThread, QRunnable, QObject, pyqtSignal


class _LogSignals(QObject):
    record = pyqtSignal(str, str)  # (levelname, formatted_message)


class QtLogHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.signals = _LogSignals()
        self.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%H:%M:%S",
        ))

    def emit(self, record):
        try:
            self.signals.record.emit(record.levelname, self.format(record))
        except Exception:
            pass


class BotThread(QThread):
    log_line = pyqtSignal(str, str)  # (levelname, formatted_message)
    status   = pyqtSignal(str)       # "running" | "stopped" | "error:<msg>"

    def __init__(self):
        super().__init__()
        self._stop = None

    def run(self):
        from core.logging_utils import setup_logging
        from main import run_bot, load_settings as _load

        setup_logging(logging.INFO)
        qt_handler = QtLogHandler()
        qt_handler.signals.record.connect(self.log_line)
        logging.getLogger().addHandler(qt_handler)

        self._stop = threading.Event()
        try:
            settings = _load()
            self.status.emit("running")
            run_bot(settings, stop_event=self._stop, non_interactive=True)
            self.status.emit("stopped")
        except Exception as e:
            self.log_line.emit("ERROR", traceback.format_exc())
            self.status.emit(f"error:{e}")
        finally:
            logging.getLogger().removeHandler(qt_handler)

    def request_stop(self):
        if self._stop is not None:
            self._stop.set()


class _SsSignals(QObject):
    done  = pyqtSignal(object)  # numpy BGR array
    error = pyqtSignal(str)


class ScreenshotWorker(QRunnable):
    def __init__(self, settings):
        super().__init__()
        self.signals = _SsSignals()
        self._settings = settings

    def run(self):
        try:
            from ppadb.client import Client as AdbClient
            serial = self._settings.get("device", {}).get("serial", "127.0.0.1:5555")
            client = AdbClient(host="127.0.0.1", port=5037)
            dev = client.device(serial)
            if dev is None:
                self.signals.error.emit(f"Device '{serial}' not found. Is ADB running?")
                return
            raw = dev.screencap()
            arr = np.frombuffer(raw, np.uint8)
            frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if frame is None:
                self.signals.error.emit("screencap returned empty data.")
                return
            self.signals.done.emit(frame)
        except Exception as e:
            self.signals.error.emit(str(e))
