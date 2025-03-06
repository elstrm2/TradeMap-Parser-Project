import sys

sys.dont_write_bytecode = True

import os
import json
import time
import glob
import logging
from pathlib import Path
from threading import Event
from datetime import datetime
from logging.handlers import RotatingFileHandler


def setup_logging() -> logging.Logger:
    logs_dir = os.path.join("bot", "logs")
    if not os.path.exists(logs_dir):
        os.makedirs(logs_dir)

    MAX_LOG_FILES = 5
    MAX_BYTES = 1024 * 1024

    current_time = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_file = os.path.join(logs_dir, f"log_{current_time}.log")

    log_files = []
    for pattern in ["log_*.log", "log_*.log.*"]:
        log_files.extend(glob.glob(os.path.join(logs_dir, pattern)))

    log_files = sorted(log_files, key=os.path.getctime)

    while len(log_files) >= MAX_LOG_FILES:
        try:
            oldest_file = log_files.pop(0)
            os.remove(oldest_file)
            print(f"Удален старый лог файл: {oldest_file}")
        except Exception as e:
            print(f"Ошибка при удалении старого лог файла {oldest_file}: {e}")

    for lib in ["selenium", "urllib3", "webdriver", "WDM"]:
        logging.getLogger(lib).setLevel(logging.ERROR)

    app_logger = logging.getLogger("app")
    if app_logger.handlers:
        return app_logger

    app_logger.setLevel(logging.DEBUG)

    formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )

    file_handler = RotatingFileHandler(
        log_file, maxBytes=MAX_BYTES, backupCount=MAX_LOG_FILES - 1, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.DEBUG)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.DEBUG)

    app_logger.handlers.clear()
    app_logger.addHandler(file_handler)
    app_logger.addHandler(console_handler)

    app_logger.propagate = False

    return app_logger


app_logger = setup_logging()

BASE_URL = "https://www.trademap.org/Index.aspx"
PRODUCT_URL = "https://www.trademap.org/Product_SelCountry_MQ_TS.aspx"

DEFAULT_ACTION_DELAY = 0.5
DEFAULT_PAGE_TIMEOUT = 5
DEFAULT_RETRY_COUNT = 3
DEFAULT_DOWNLOAD_TIMEOUT = 30
DEFAULT_FREEZE_HEADER = True


def main(stop_event: Event) -> bool:
    try:
        app_logger.info("Bot main function started")

        config_path = Path("bot/config.json")
        if not config_path.exists():
            app_logger.error("Configuration file not found")
            return False

        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)

        app_logger.info("Configuration loaded successfully")

        if not config.get("username") or not config.get("password"):
            app_logger.error("Missing credentials in config")
            return False

        if not config.get("product_codes") or not config.get("countries"):
            app_logger.error("Missing product codes or countries in config")
            return False

        time.sleep(2)

        if stop_event.is_set():
            app_logger.info("Received stop signal during initialization")
            return False

        app_logger.info("Bot initialized successfully")

        while not stop_event.is_set():
            try:
                time.sleep(1)
                app_logger.debug("Bot working...")

            except Exception as e:
                app_logger.error(f"Error in main loop: {str(e)}")
                continue

        app_logger.info("Bot stopped gracefully")
        return True

    except Exception as e:
        app_logger.error(
            f"Critical error in bot main function: {str(e)}", exc_info=True
        )
        return False
