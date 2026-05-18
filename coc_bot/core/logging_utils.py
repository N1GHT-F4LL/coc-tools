import logging
import sys


class ColorFormatter(logging.Formatter):
    RESET = "\x1b[0m"
    COLORS = {
        logging.DEBUG: "\x1b[36m",   # Cyan
        logging.INFO: "\x1b[90m",    # Gray
        logging.WARNING: "\x1b[33m", # Yellow
        logging.ERROR: "\x1b[31m",   # Red
        logging.CRITICAL: "\x1b[35m" # Magenta
    }

    def __init__(self, use_color=True):
        super().__init__("%(message)s")
        self.use_color = use_color

    def format(self, record):
        msg = record.getMessage()
        level_tag = f"[{record.levelname}]"
        if not self.use_color:
            return f"{level_tag} {msg}"
        color = self.COLORS.get(record.levelno, "")
        if color:
            level_tag = f"{color}{level_tag}{self.RESET}"
        return f"{level_tag} {msg}"


def setup_logging(level=logging.INFO):
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(ColorFormatter(use_color=bool(sys.stdout.isatty())))
    root_logger.addHandler(handler)
