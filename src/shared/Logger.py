import logging
from logging.handlers import RotatingFileHandler
import os


def __initiate_logger(name, log_path, debug):
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    if not logger.handlers:
        file_handler = RotatingFileHandler(log_path, maxBytes=1_000_000, backupCount=1)
        file_handler.setLevel(logging.INFO) if not debug else file_handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter("%(asctime)s:%(name)s:%(levelname)s:%(message)s", datefmt="%Y-%m-%d %H:%M:%S")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        if debug:
            logger = __make_debug_logger(logger, formatter)
    return logger


def __make_debug_logger(logger, formatter):
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.DEBUG)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)
    return logger


def __create_log_folder_if_necessary(log_path):
    if not os.path.isdir(log_path):
        os.mkdir(log_path)


def create_logger(name, debug, log_filename):
    root_path = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    log_path = os.path.join(root_path, "logs")
    log_filename = os.path.join(log_path, log_filename)
    __create_log_folder_if_necessary(log_path)
    logger = __initiate_logger(name, log_filename, debug)
    return logger
