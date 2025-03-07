import subprocess
import sys

sys.dont_write_bytecode = True

import os
import json
import time
from pathlib import Path
from threading import Thread, Event, Lock
from typing import Dict, Any, Optional

from flask import Flask, jsonify, render_template, request
from pydantic import BaseModel, ValidationError

from bot.core import setup_logging

app_logger = setup_logging()

from typing_extensions import Annotated
from pydantic import BaseModel, Field


class ConfigSchema(BaseModel):
    username: str
    password: str
    product_codes: list[str]
    countries: list[str]
    action_delay: Annotated[float, Field(ge=0.1)]
    page_timeout: Annotated[int, Field(ge=1)]
    retry_count: Annotated[int, Field(ge=1)]
    download_timeout: Annotated[int, Field(ge=5)]
    captcha_timeout: Annotated[int, Field(ge=30)]
    freeze_header: bool
    parse_all_pages: bool
    quantity_unit: str
    parse_depth: str


class BotController:

    def __init__(self) -> None:
        self.bot_thread: Optional[Thread] = None
        self.stop_event = Event()
        self.lock = Lock()
        self.config_path = Path("bot/config.json")
        self.is_stopping = False
        self.is_starting = False
        self.last_result: Optional[bool] = None
        self.last_error: Optional[str] = None

    def get_bot_state(self) -> str:
        if self.bot_is_running():
            return "running"
        if self.is_stopping:
            return "stopping"
        return "stopped"

    def get_last_result(self) -> Optional[bool]:
        return self.last_result

    def get_last_error(self) -> Optional[str]:
        return self.last_error

    def clear_errors(self) -> None:
        self.last_error = None

    def load_config(self) -> Dict[str, Any]:
        default_config = {
            "username": "",
            "password": "",
            "product_codes": [],
            "countries": [],
            "action_delay": 0.5,
            "page_timeout": 5,
            "retry_count": 3,
            "download_timeout": 30,
            "captcha_timeout": 60,
            "freeze_header": True,
            "parse_all_pages": False,
            "quantity_unit": "Kilograms",
            "parse_depth": "level1",
        }

        try:
            if not self.config_path.exists():
                app_logger.warning(
                    "Конфиг не найден, создаём новый с дефолтными значениями"
                )
                self.save_config(default_config)
                return default_config

            with open(self.config_path, "r", encoding="utf-8") as f:
                loaded_config = json.load(f)
                config = default_config.copy()
                needs_update = False

                for key in default_config:
                    if key not in loaded_config:
                        needs_update = True
                        continue

                    try:
                        temp_config = default_config.copy()
                        temp_config[key] = loaded_config[key]

                        ConfigSchema(**temp_config)

                        config[key] = loaded_config[key]
                    except ValidationError as e:
                        app_logger.warning(
                            f"Невалидное значение для {key}, исправляем на значение по умолчанию: {str(e)}"
                        )
                        needs_update = True

                if needs_update:
                    app_logger.info("Обновляем конфиг файл с исправленными значениями")
                    self.save_config(config)

                return config

        except json.JSONDecodeError as e:
            app_logger.error(f"Ошибка чтения JSON: {str(e)}")
            self.save_config(default_config)
            return default_config
        except Exception as e:
            app_logger.error(f"Непредвиденная ошибка загрузки конфига: {str(e)}")
            self.save_config(default_config)
            return default_config

    def save_config(self, config: Dict[str, Any]) -> bool:
        try:
            validated = ConfigSchema(**config).model_dump()
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(validated, f, indent=2, ensure_ascii=False)
            app_logger.info("Конфигурация успешно сохранена")
            return True
        except (ValidationError, TypeError) as e:
            app_logger.error(f"Некорректная конфигурация: {str(e)}")
            return False
        except Exception as e:
            app_logger.error(f"Ошибка сохранения: {str(e)}", exc_info=True)
            return False

    def bot_is_running(self) -> bool:
        app_logger.debug("Checking bot status...")
        return (
            self.bot_thread is not None
            and self.bot_thread.is_alive()
            and not self.is_stopping
        )

    def start_bot(self) -> bool:
        if self.bot_is_running():
            app_logger.warning("Bot is already running")
            return False

        self.clear_errors()

        with self.lock:
            if self.is_starting:
                app_logger.warning("Start already in progress")
                return False

            try:
                app_logger.info("Attempting to start bot...")
                self.is_starting = True
                self.stop_event.clear()
                initialization_event = Event()

                try:
                    from bot.core import main as bot_main

                    app_logger.info("Bot module imported successfully")
                except ImportError as e:
                    app_logger.critical(f"Failed to import bot module: {str(e)}")
                    self._cleanup()
                    return False

                def bot_wrapper() -> None:
                    try:
                        initialization_event.set()
                        app_logger.info("Bot initialization started")
                        self.last_result = bot_main(self.stop_event)
                        if self.last_result:
                            app_logger.info("Bot completed successfully")
                            self.last_error = None
                        else:
                            app_logger.error("Bot completed with errors")
                            self.last_error = "Ошибка выполнения бота"
                    except Exception as e:
                        app_logger.error(f"Bot thread error: {str(e)}", exc_info=True)
                        self.last_result = False
                        self.last_error = f"{type(e).__name__}: {str(e)}"
                    finally:
                        self._cleanup()

                self.bot_thread = Thread(target=bot_wrapper, daemon=True)
                self.bot_thread.start()

                if not initialization_event.wait(timeout=3.0):
                    app_logger.error("Bot initialization timeout")
                    self._cleanup()
                    return False

                app_logger.info("Bot started successfully")
                return True

            except Exception as e:
                app_logger.error(f"Error starting bot: {str(e)}", exc_info=True)
                return False
            finally:
                if not self.bot_is_running():
                    self.is_starting = False
                    self._cleanup()

    def stop_bot(self) -> bool:
        with self.lock:
            app_logger.info("Attempting to stop bot...")

            if self.is_stopping:
                app_logger.warning("Stop already in progress")
                return True

            try:
                interval = 1
                attempts = 60

                self.is_stopping = True
                app_logger.info("Setting stop event...")
                self.stop_event.set()

                app_logger.debug(
                    f"Stop parameters: interval={interval}s, attempts={attempts}"
                )

                for i in range(attempts):
                    if self.bot_thread is None or not self.bot_thread.is_alive():
                        app_logger.info("Bot thread finished successfully")
                        self._cleanup()
                        return True

                    app_logger.info(f"Waiting for bot to stop... {i + 1}/{attempts}")
                    time.sleep(interval)

                app_logger.error("Bot failed to stop within timeout")
                return False

            except Exception as e:
                app_logger.error(f"Error stopping bot: {str(e)}", exc_info=True)
                return False
            finally:
                self._cleanup()

    def _cleanup(self) -> None:
        self.bot_thread = None
        self.stop_event.clear()
        self.is_stopping = False
        self.is_starting = False
        app_logger.info("Bot state cleaned up")


app = Flask("app")
app.secret_key = os.urandom(24)
controller = BotController()


@app.route("/api/config", methods=["GET"])
def get_config() -> Dict[str, Any]:
    try:
        config = controller.load_config()
        return {"status": "success", "config": config}
    except Exception as e:
        app_logger.error(f"Ошибка получения конфига: {str(e)}", exc_info=True)
        return {"status": "error", "message": str(e)}


@app.route("/api/config", methods=["POST"])
def update_config() -> Dict[str, str]:
    try:
        new_config = request.get_json()
        if not new_config:
            return {"status": "error", "message": "Empty config"}, 400

        if controller.save_config(new_config):
            return {"status": "success"}
        return {"status": "error", "message": "Invalid configuration"}, 400

    except Exception as e:
        app_logger.error(f"Ошибка обновления конфига: {str(e)}", exc_info=True)
        return {"status": "error", "message": str(e)}, 500


@app.route("/api/bot/start", methods=["POST"])
def start_bot() -> Dict[str, str]:
    try:
        app_logger.info("Received start bot request")

        if controller.bot_is_running():
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": "Бот уже запущен",
                        "state": "running",
                        "timestamp": time.ctime(),
                    }
                ),
                409,
            )

        start_result = controller.start_bot()

        if start_result:
            return jsonify(
                {
                    "status": "success",
                    "message": "Бот успешно запущен",
                    "state": "starting",
                    "timestamp": time.ctime(),
                }
            )

        return (
            jsonify(
                {
                    "status": "error",
                    "message": "Не удалось запустить бота",
                    "state": "stopped",
                    "timestamp": time.ctime(),
                }
            ),
            500,
        )

    except Exception as e:
        error_msg = f"Ошибка запуска бота: {str(e)}"
        app_logger.error(error_msg, exc_info=True)
        return (
            jsonify(
                {
                    "status": "error",
                    "message": error_msg,
                    "details": str(e),
                    "state": "error",
                    "timestamp": time.ctime(),
                }
            ),
            500,
        )


@app.route("/api/bot/stop", methods=["POST"])
def stop_bot() -> Dict[str, str]:
    try:
        app_logger.info("Received stop bot request")

        if not controller.bot_is_running():
            return jsonify(
                {
                    "status": "success",
                    "message": "Бот не запущен",
                    "state": "stopped",
                    "timestamp": time.ctime(),
                }
            )

        stop_result = controller.stop_bot()

        if stop_result:
            return jsonify(
                {
                    "status": "success",
                    "message": "Запрос на остановку бота отправлен",
                    "state": "stopping",
                    "timestamp": time.ctime(),
                }
            )

        return (
            jsonify(
                {
                    "status": "error",
                    "message": "Не удалось отправить запрос на остановку",
                    "state": "running",
                    "timestamp": time.ctime(),
                }
            ),
            500,
        )

    except Exception as e:
        error_msg = f"Ошибка остановки бота: {str(e)}"
        app_logger.error(error_msg, exc_info=True)
        return (
            jsonify(
                {
                    "status": "error",
                    "message": error_msg,
                    "details": str(e),
                    "state": "unknown",
                    "timestamp": time.ctime(),
                }
            ),
            500,
        )


@app.route("/api/bot/status", methods=["GET"])
def bot_status() -> Dict[str, str]:
    status_info = {
        "state": controller.get_bot_state(),
        "last_result": controller.get_last_result(),
        "error": controller.get_last_error(),
        "timestamp": time.ctime(),
    }
    return jsonify(status_info)


@app.route("/api/server/status", methods=["GET"])
def server_status() -> Dict[str, str]:
    return jsonify({"status": "running", "timestamp": time.ctime()})


@app.route("/api/bot/captcha-status", methods=["GET"])
def check_captcha_status() -> Dict[str, str]:
    from bot.core import CAPTCHA_STATE

    if CAPTCHA_STATE["active"]:
        return jsonify({"status": "waiting", "message": CAPTCHA_STATE["message"]})
    return jsonify({"status": "none", "message": "Капча не требуется"})


@app.route("/")
def index():
    if getattr(sys, "frozen", False):
        template_folder = os.path.join(sys._MEIPASS, "templates")
        template_path = os.path.join(template_folder, "index.html")
        with open(template_path, "r", encoding="utf-8") as f:
            template_content = f.read()
        return template_content
    else:
        return render_template("index.html")


@app.route("/favicon.ico")
def favicon() -> tuple[str, int]:
    return "", 204


@app.errorhandler(404)
def handle_not_found(e) -> Dict[str, str]:
    app_logger.warning(f"404 Not Found: {request.url}")
    return {"status": "error", "message": "Resource not found"}, 404


@app.route("/api/bot/clear-errors", methods=["POST"])
def clear_errors() -> Dict[str, str]:
    controller.clear_errors()
    return jsonify({"status": "success"})


@app.errorhandler(500)
def handle_server_error(e) -> Dict[str, str]:
    app_logger.critical(f"500 Error: {str(e)}", exc_info=True)
    return {"status": "error", "message": "Internal server error"}, 500


if __name__ == "__main__":
    try:
        app_logger.info("=" * 50)
        app_logger.info("Starting Parser Server")
        app_logger.info("=" * 50)

        import socket

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.bind(("localhost", 5000))
            sock.close()
        except socket.error:
            app_logger.error("Port 5000 is already in use!")
            if sys.platform == "win32":
                try:
                    netstat_result = subprocess.run(
                        ["netstat", "-ano"],
                        capture_output=True,
                        text=True,
                        shell=True,
                    )

                    pids = set()
                    for line in netstat_result.stdout.splitlines():
                        if ":5000" in line and "LISTENING" in line:
                            parts = line.strip().split()
                            pid = parts[-1]
                            pids.add(pid)

                    for pid in pids:
                        try:
                            subprocess.run(
                                ["taskkill", "/F", "/PID", pid],
                                capture_output=True,
                                shell=True,
                                timeout=5,
                            )
                            app_logger.debug(f"Killed process with PID: {pid}\n")
                        except subprocess.TimeoutExpired:
                            app_logger.error(f"Timeout killing PID {pid}\n")
                            sys.exit(1)
                        except Exception as e:
                            app_logger.error(f"Error killing PID {pid}: {e}\n")
                            sys.exit(1)

                except Exception as e:
                    app_logger.error(f"Process check error: {e}\n")
                    sys.exit(1)

        app_logger.info("Checking configuration...")
        app_logger.debug(f"Current directory: {os.getcwd()}")
        app_logger.debug(f"Python path: {sys.executable}")
        app_logger.debug(f"Python version: {sys.version}")

        app_logger.info("Starting server on http://localhost:5000")
        app.run(host="localhost", port=5000, debug=False, use_reloader=False)
    except Exception as e:
        app_logger.critical(f"Server startup failed: {str(e)}", exc_info=True)
        sys.exit(1)
