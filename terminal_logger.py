# terminal_logger.py
import logging
import sys

class TerminalLogger:
    """A lightweight wrapper around logging to ensure consistent format."""
    
    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.INFO)
        # Handlers are configured in app.py via basicConfig, 
        # so we don't add them here to avoid duplication.

    def info(self, msg, **kwargs):
        self._log(logging.INFO, msg, kwargs)

    def warn(self, msg, **kwargs):
        self._log(logging.WARNING, msg, kwargs)

    def error(self, msg, **kwargs):
        self._log(logging.ERROR, msg, kwargs)

    def debug(self, msg, **kwargs):
        self._log(logging.DEBUG, msg, kwargs)

    def exception(self, msg, **kwargs):
        self.logger.exception(f"{msg} | {kwargs}")

    def _log(self, level, msg, kwargs):
        if kwargs:
            # Format structured data as key=value for readability
            pairs = [f"{k}={v}" for k, v in kwargs.items()]
            msg = f"{msg} | " + " ".join(pairs)
        self.logger.log(level, msg)