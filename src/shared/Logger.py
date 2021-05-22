import logging
from logging.handlers import RotatingFileHandler


def __initiate_logger(name, log_path):
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    file_handler = RotatingFileHandler(log_path, maxBytes=10_000_000, backupCount=1)
    file_handler.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s:%(name)s:%(levelname)s:%(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    return logger


def __make_debug_logger(logger):
    formatter = logging.Formatter("%(asctime)s:%(name)s:%(levelname)s:%(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.DEBUG)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)
    return logger


def create_logger(name, debug, log_path):
    logger = __initiate_logger(name, log_path)
    if debug:
        logger = __make_debug_logger(logger)
    return logger
