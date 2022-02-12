__author__ = "Mandar Patil (mandarons@pm.me)"

import warnings
import logging
import os
import sys
from ruamel.yaml import YAML

DEFAULT_ROOT_DESTINATION = "./icloud"
DEFAULT_DRIVE_DESTINATION = "drive"
DEFAULT_PHOTOS_DESTINATION = "photos"
DEFAULT_SYNC_INTERVAL_SEC = 1800  # 30 minutes
DEFAULT_CONFIG_FILE_NAME = "config.yaml"
DEFAULT_CONFIG_FILE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), DEFAULT_CONFIG_FILE_NAME
)

warnings.filterwarnings("ignore", category=DeprecationWarning)


def read_config(config_path=DEFAULT_CONFIG_FILE_PATH):
    if not (config_path and os.path.exists(config_path)):
        print("Config file not found at %s.", config_path)
        return None
    print("Loading config from %s ...", config_path)
    with open(file=config_path, mode="r") as config_file:
        config = YAML().load(config_file)
    config["app"]["credentials"]["username"] = (
        config["app"]["credentials"]["username"].strip()
        if config["app"]["credentials"]["username"] is not None
        else ""
    )
    return config


def get_logger_config(config):
    logger_config = {}
    if "logger" not in config["app"]:
        return None
    config_app_logger = config["app"]["logger"]
    logger_config["level"] = (
        config_app_logger["level"].strip().lower()
        if "level" in config_app_logger
        else "warning"
    )
    logger_config["filename"] = (
        config_app_logger["filename"].strip().lower()
        if "filename" in config_app_logger
        else "icloud.log"
    )
    return logger_config


def log_handler_exists(logger, handler_type, **kwargs):
    for handler in logger.handlers:
        if isinstance(handler, handler_type):
            if handler_type is logging.FileHandler:
                if handler.baseFilename.endswith(kwargs["filename"]):
                    return True
            elif handler_type is logging.StreamHandler:
                if handler.stream is kwargs["stream"]:
                    return True
    return False


class ColorfulConsoleFormatter(logging.Formatter):

    grey = "\x1b[38;21m"
    blue = "\x1b[38;5;39m"
    yellow = "\x1b[38;5;226m"
    red = "\x1b[38;5;196m"
    bold_red = "\x1b[31;1m"
    reset = "\x1b[0m"

    def __init__(self, fmt):
        super().__init__()
        self.fmt = fmt
        self.formats = {
            logging.DEBUG: self.grey + self.fmt + self.reset,
            logging.INFO: self.blue + self.fmt + self.reset,
            logging.WARNING: self.yellow + self.fmt + self.reset,
            logging.ERROR: self.red + self.fmt + self.reset,
            logging.CRITICAL: self.bold_red + self.fmt + self.reset,
        }

    def format(self, record):
        log_fmt = self.formats.get(record.levelno)
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)


def get_logger():
    logger = logging.getLogger()
    # if not logger.hasHandlers():
    # TODO: parse config for logger configuration
    logger_config = get_logger_config(config=read_config())
    if logger_config:
        logger.setLevel(logging.getLevelName(level=logger_config["level"].upper()))
        if not log_handler_exists(
            logger=logger,
            handler_type=logging.FileHandler,
            filename=logger_config["filename"],
        ):
            file_handler = logging.FileHandler(logger_config["filename"])
            file_handler.setFormatter(
                logging.Formatter(
                    "%(asctime)s :: %(levelname)s :: %(name)s :: %(filename)s :: %(lineno)d :: %(message)s"
                )
            )
            logger.addHandler(file_handler)
        if not log_handler_exists(
            logger=logger, handler_type=logging.StreamHandler, stream=sys.stdout
        ):
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setFormatter(
                ColorfulConsoleFormatter(
                    "%(asctime)s :: %(levelname)s :: %(name)s :: %(filename)s :: %(lineno)d :: %(message)s"
                )
            )
            logger.addHandler(console_handler)
    return logger


LOGGER = get_logger()
