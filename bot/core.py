import sys

sys.dont_write_bytecode = True

import os
import re
import json
import time
import glob
import logging
import traceback
import pandas as pd
from pathlib import Path
from threading import Event
from datetime import datetime
from logging.handlers import RotatingFileHandler
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    WebDriverException,
    TimeoutException,
    NoSuchElementException,
)
from selenium.webdriver.common.action_chains import ActionChains


def setup_logging() -> logging.Logger:
    logs_dir = os.path.join("bot", "logs")
    if not os.path.exists(logs_dir):
        os.makedirs(logs_dir)

    MAX_LOG_FILES = 6
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
DEFAULT_CAPTCHA_TIMEOUT = 300
DEFAULT_FREEZE_HEADER = True
DEFAULT_PARSE_ALL_PAGES = False
DEFAULT_QUANTITY_UNIT = "Kilograms"
DEFAULT_PARSE_DEPTH = "level1"

CAPTCHA_STATE = {"active": False, "message": None}

WEIGHT_UNITS = {
    "Kilograms": 1.0,
    "Kilogram": 1.0,
    "kilogram": 1.0,
    "Kilogrammes": 1.0,
    "kilogrammes": 1.0,
    "Kgs": 1.0,
    "kg": 1.0,
    "KG": 1.0,
    "Tons": 1000.0,
    "Tonnes": 1000.0,
    "tonnes": 1000.0,
    "Ton": 1000.0,
    "ton": 1000.0,
    "MT": 1000.0,
    "mt": 1000.0,
}


def validate_product_code(code: str) -> bool:
    app_logger.debug(f"Проверка кода продукта: {code}")
    is_valid = len(str(code)) >= 0 and str(code).isdigit()
    if not is_valid:
        app_logger.warning(f"Неверный формат кода продукта: {code}")
    return is_valid


def check_chrome_installed() -> bool:
    app_logger.debug("Проверка установки Chrome")
    try:
        driver = webdriver.Chrome()
        driver.quit()
        app_logger.info("Chrome успешно обнаружен")
        return True
    except WebDriverException as e:
        app_logger.error(f"Chrome не установлен: {str(e)}")
        return False


def validate_config(config: dict) -> bool:
    app_logger.debug("Начало проверки конфигурации")
    app_logger.debug(
        f"Полученный конфиг: {json.dumps(config, ensure_ascii=False, indent=2)}"
    )

    required_fields = {
        "username": "логин",
        "password": "пароль",
        "product_codes": "коды продуктов",
        "countries": "страны",
    }

    for field, name in required_fields.items():
        if field not in config or not config[field]:
            error_msg = f"В конфиге отсутствует или пустое поле '{name}'"
            app_logger.error(error_msg)
            return False
        app_logger.debug(f"Поле '{name}' присутствует и не пустое")

    if not config["product_codes"] or not config["countries"]:
        error_msg = "Должен быть указан минимум 1 код продукта и 1 страна"
        app_logger.error(error_msg)
        return False

    if "action_delay" not in config:
        config["action_delay"] = DEFAULT_ACTION_DELAY
    if "page_timeout" not in config:
        config["page_timeout"] = DEFAULT_PAGE_TIMEOUT
    if "retry_count" not in config:
        config["retry_count"] = DEFAULT_RETRY_COUNT
    if "download_timeout" not in config:
        config["download_timeout"] = DEFAULT_DOWNLOAD_TIMEOUT
    if "captcha_timeout" not in config:
        config["captcha_timeout"] = DEFAULT_CAPTCHA_TIMEOUT
    if "freeze_header" not in config:
        config["freeze_header"] = DEFAULT_FREEZE_HEADER
    if "parse_all_pages" not in config:
        config["parse_all_pages"] = DEFAULT_PARSE_ALL_PAGES
    if "quantity_unit" not in config:
        config["quantity_unit"] = DEFAULT_QUANTITY_UNIT
    if "parse_depth" not in config:
        config["parse_depth"] = DEFAULT_PARSE_DEPTH

    if config["quantity_unit"] not in ["Kilograms", "Tons"]:
        error_msg = f"Неверная единица измерения в конфиге: {config['quantity_unit']}. Допустимы только 'Kilograms' или 'Tons'"
        app_logger.error(error_msg)
        return False

    valid_depths = ["level1", "level2", "level3", "level4"]
    if config["parse_depth"] not in valid_depths:
        error_msg = f"Неверный уровень глубины парсинга: {config['parse_depth']}. Допустимые значения: {', '.join(valid_depths)}"
        app_logger.error(error_msg)
        return False

    try:
        config["action_delay"] = float(config["action_delay"])
        config["page_timeout"] = int(config["page_timeout"])
        config["retry_count"] = int(config["retry_count"])
        config["download_timeout"] = int(config["download_timeout"])
        config["captcha_timeout"] = int(config["captcha_timeout"])
        config["freeze_header"] = bool(config["freeze_header"])

        if (
            config["action_delay"] <= 0.1
            or config["page_timeout"] <= 1
            or config["retry_count"] <= 1
            or config["download_timeout"] <= 5
            or config["captcha_timeout"] <= 30
        ):
            raise ValueError("Значения задержек и попыток должны быть положительными")

        app_logger.debug(f"Задержка между действиями: {config['action_delay']} сек")
        app_logger.debug(f"Таймаут ожидания: {config['page_timeout']} сек")
        app_logger.debug(f"Количество попыток: {config['retry_count']}")
        app_logger.debug(f"Таймаут загрузки: {config['download_timeout']} сек")
        app_logger.debug(f"Таймаут капчи: {config['captcha_timeout']} сек")
        app_logger.debug(f"Закрепление заголовка: {config['freeze_header']}")
        app_logger.debug(f"Парсинг всех страниц: {config['parse_all_pages']}")

    except Exception as e:
        error_msg = f"Некорректные значения параметров: {str(e)}"
        app_logger.error(error_msg)
        return False

    app_logger.debug(f"Количество кодов продуктов: {len(config['product_codes'])}")
    app_logger.debug(f"Коды продуктов: {', '.join(map(str, config['product_codes']))}")
    app_logger.debug(f"Количество стран: {len(config['countries'])}")
    app_logger.debug(f"Страны: {', '.join(config['countries'])}")
    app_logger.debug(f"Единица измерения: {config['quantity_unit']}")
    app_logger.debug(f"Уровень глубины парсинга: {config['parse_depth']}")

    app_logger.info("Конфигурация успешно прошла проверку")
    return True


def handle_captcha(driver, config: dict, stop_event: Event) -> bool:
    app_logger.debug("Проверка наличия капчи")

    if "stCaptcha.aspx" not in driver.current_url:
        app_logger.debug("Капча не обнаружена")
        return True

    app_logger.info("Обнаружена капча")
    try:
        CAPTCHA_STATE["active"] = True
        CAPTCHA_STATE["message"] = "Требуется ввод капчи"

        error_shown = False
        max_wait_time = config["captcha_timeout"]
        start_time = time.time()

        while "stCaptcha.aspx" in driver.current_url:
            if time.time() - start_time > max_wait_time:
                app_logger.error(
                    f"Превышено время ожидания ввода капчи ({max_wait_time} секунд)"
                )
                return False

            if stop_event.is_set():
                app_logger.warning("Остановка запрошена во время ожидания капчи")
                return True

            app_logger.debug(f"Ожидание ввода капчи")

            error_div = driver.find_elements(
                By.ID, "ctl00_PageContent_div_validationFailed"
            )

            if (
                error_div
                and "The characters you entered are not valid" in error_div[0].text
            ):
                if not error_shown:
                    CAPTCHA_STATE["message"] = "Капча введена неверно, попробуйте снова"
                    app_logger.warning("Неверно введена капча")
                    error_shown = True
            else:
                if error_shown:
                    CAPTCHA_STATE["message"] = "Требуется ввод капчи"
                    error_shown = False

            time.sleep(1)

            if "stCaptcha.aspx" not in driver.current_url:
                app_logger.info("Капча успешно пройдена")
                break

    except Exception as e:
        app_logger.error(f"Ошибка при обработке капчи: {str(e)}", exc_info=True)
        return False
    finally:
        CAPTCHA_STATE["active"] = False
        CAPTCHA_STATE["message"] = None

    return True


def select_parameters(
    driver, wait, product_code: str, country_code: str, config: dict, stop_event: Event
) -> bool:
    try:
        if stop_event.is_set():
            app_logger.info("Остановка запрошена перед выбором параметров")
            return True

        app_logger.debug(
            f"Начало выбора параметров для кода {product_code} и страны {country_code}"
        )
        app_logger.debug(f"Переход на страницу {PRODUCT_URL}")
        driver.get(PRODUCT_URL)

        time.sleep(config["action_delay"])
        if stop_event.is_set():
            app_logger.info("Остановка запрошена после загрузки страницы")
            return True

        app_logger.debug("Начало пошагового выбора кода продукта")
        code_length = len(product_code)

        try:
            app_logger.debug("Выбор 'All products' для обновления списка кодов")
            product_select = wait.until(
                EC.presence_of_element_located(
                    (By.ID, "ctl00_NavigationControl_DropDownList_Product")
                )
            )
            select = Select(product_select)
            select.select_by_value("TOTAL")
            time.sleep(config["action_delay"])
        except Exception as e:
            app_logger.error(f"Ошибка при выборе 'All products': {str(e)}")
            return False

        if code_length == 2:
            code_steps = [product_code]
        else:
            code_steps = []
            for i in [2, 4, 6, 10]:
                if i > code_length:
                    break
                if i == code_length:
                    code_steps.append(product_code)
                    break
                code_steps.append(product_code[:i])

            if code_length > 10:
                app_logger.warning(
                    f"Код продукта {product_code} будет усечен до 10 знаков: {product_code[:10]}"
                )
                product_code = product_code[:10]
                if product_code not in code_steps:
                    code_steps.append(product_code)

        app_logger.debug(f"Последовательность выбора кодов: {' -> '.join(code_steps)}")

        for step, current_code in enumerate(code_steps, 1):
            if stop_event.is_set():
                app_logger.info(
                    f"Остановка запрошена на шаге {step} выбора кода продукта"
                )
                return True

            attempts = 0
            while attempts < config["retry_count"]:
                try:
                    app_logger.debug(
                        f"Шаг {step}/{len(code_steps)}: Попытка выбора кода {current_code}"
                    )

                    product_select = wait.until(
                        EC.presence_of_element_located(
                            (By.ID, "ctl00_NavigationControl_DropDownList_Product")
                        )
                    )
                    select = Select(product_select)

                    available_options = [
                        opt.get_attribute("value") for opt in select.options
                    ]
                    app_logger.debug(f"Доступные коды: {', '.join(available_options)}")

                    if current_code not in available_options:
                        error_msg = (
                            f"Код {current_code} не найден в списке доступных опций"
                        )
                        app_logger.error(error_msg)
                        return False

                    select.select_by_value(current_code)
                    time.sleep(config["action_delay"])

                    if "Div_PopupRestriction" in driver.page_source:
                        error_msg = (
                            f"Аккаунт не имеет доступа к коду продукта {current_code}"
                        )
                        app_logger.error(error_msg)
                        return False

                    product_select = wait.until(
                        EC.presence_of_element_located(
                            (By.ID, "ctl00_NavigationControl_DropDownList_Product")
                        )
                    )
                    select = Select(product_select)
                    selected_value = select.first_selected_option.get_attribute("value")

                    if selected_value == current_code:
                        app_logger.info(f"Успешно выбран код {current_code}")

                        if "Div_PopupRestriction" in driver.page_source:
                            error_msg = f"Аккаунт не имеет доступа к коду продукта {current_code}"
                            app_logger.error(error_msg)
                            return False

                        if step == len(code_steps):
                            if selected_value == product_code:
                                app_logger.info(
                                    f"Достигнут целевой код продукта: {product_code}"
                                )
                            else:
                                error_msg = f"Конечный выбранный код {selected_value} не соответствует целевому {product_code}"
                                app_logger.error(error_msg)
                                return False
                        break
                    else:
                        raise ValueError(
                            f"Выбран неверный код: {selected_value} вместо {current_code}"
                        )

                except Exception as e:
                    attempts += 1
                    if attempts >= config["retry_count"]:
                        app_logger.error(
                            f"Не удалось выбрать код {current_code} после {attempts} попыток: {str(e)}"
                        )
                        return False
                    time.sleep(config["action_delay"])
                    continue

        app_logger.info(f"Код продукта {product_code} успешно выбран")

        try:
            if stop_event.is_set():
                app_logger.info("Остановка запрошена перед выбором страны")
                return True

            app_logger.debug("Попытка выбора radio button страны")
            country_radio = wait.until(
                EC.element_to_be_clickable(
                    (By.ID, "ctl00_NavigationControl_RadioButton_Country")
                )
            )
            driver.execute_script("arguments[0].click();", country_radio)
            app_logger.info("Radio button страны успешно выбран")
            time.sleep(config["action_delay"])

            if stop_event.is_set():
                app_logger.info("Остановка запрошена после выбора radio button")
                return True

        except Exception as e:
            app_logger.error(
                f"Ошибка при выборе radio button страны: {str(e)}", exc_info=True
            )
            return False

        try:
            app_logger.debug(f"Попытка выбора страны: {country_code}")
            country_select = wait.until(
                EC.presence_of_element_located(
                    (By.ID, "ctl00_NavigationControl_DropDownList_Country")
                )
            )
            select = Select(country_select)

            available_countries = [
                f"{opt.get_attribute('value')}:{opt.get_attribute('title')}"
                for opt in select.options
            ]
            app_logger.debug(f"Доступные страны: {', '.join(available_countries)}")

            country_option = next(
                (
                    opt
                    for opt in select.options
                    if opt.get_attribute("title")
                    and country_code in opt.get_attribute("title")
                ),
                None,
            )

            if not country_option:
                error_msg = f"Страна {country_code} не найдена в списке доступных стран"
                app_logger.error(error_msg)
                raise ValueError(error_msg)

            country_value = country_option.get_attribute("value")
            app_logger.debug(f"Найдено значение страны: {country_value}")

            select.select_by_value(country_value)
            app_logger.info(f"Страна {country_code} успешно выбрана")
            time.sleep(config["action_delay"])

            if stop_event.is_set():
                app_logger.info("Остановка запрошена после выбора страны")
                return True

        except Exception as e:
            app_logger.error(f"Ошибка при выборе страны: {str(e)}", exc_info=True)
            return False

        main_parameters = [
            ("ctl00_NavigationControl_DropDownList_Partner", "-2", "All"),
            ("ctl00_NavigationControl_DropDownList_TradeType", "I", "Imports"),
            (
                "ctl00_NavigationControl_DropDownList_OutputType",
                "TSM",
                "Monthly time series",
            ),
            (
                "ctl00_NavigationControl_DropDownList_OutputOption",
                "ByCountry",
                "By Country",
            ),
            ("ctl00_NavigationControl_DropDownList_MirrorDirect", "D", "Direct data"),
            ("ctl00_NavigationControl_DropDownList_TS_Indicator", "Q", "Quantities"),
        ]

        rows_parameters = [
            (
                "ctl00_PageContent_GridViewPanelControl_DropDownList_NumTimePeriod",
                "20",
                "20 per page",
            ),
            (
                "ctl00_PageContent_GridViewPanelControl_DropDownList_PageSize",
                "300",
                "300 per page",
            ),
        ]

        app_logger.debug("Начало выбора основных параметров")
        for param_id, param_value, param_name in main_parameters:
            if stop_event.is_set():
                app_logger.info(
                    f"Остановка запрошена во время настройки параметра {param_name}"
                )
                return True

            attempts = 0
            while attempts < config["retry_count"]:
                try:
                    if stop_event.is_set():
                        app_logger.info(
                            f"Прерывание настройки параметра {param_name} по запросу"
                        )
                        return True

                    app_logger.debug(
                        f"Попытка установки параметра {param_name} = {param_value} (попытка {attempts + 1})"
                    )

                    element = wait.until(
                        EC.presence_of_element_located((By.ID, param_id))
                    )
                    select = Select(element)

                    try:
                        available_options = [
                            f"{opt.get_attribute('value')}:{opt.text}"
                            for opt in select.options
                        ]
                        app_logger.debug(
                            f"Доступные значения для {param_name}: {', '.join(available_options)}"
                        )
                    except Exception as e:
                        app_logger.debug(
                            f"Ошибка получения опций: {str(e)}", exc_info=True
                        )

                    select.select_by_value(param_value)
                    time.sleep(config["action_delay"])

                    if stop_event.is_set():
                        app_logger.info(
                            f"Остановка после установки параметра {param_name}"
                        )
                        return True

                    element = wait.until(
                        EC.presence_of_element_located((By.ID, param_id))
                    )
                    select = Select(element)
                    selected_value = select.first_selected_option.get_attribute("value")

                    if selected_value == param_value:
                        app_logger.info(
                            f"Параметр {param_name} успешно установлен в {param_value}"
                        )
                        break
                    else:
                        error_msg = f"Выбрано неверное значение: {selected_value} вместо {param_value}"
                        raise ValueError(error_msg)

                except Exception as e:
                    attempts += 1
                    if attempts >= config["retry_count"]:
                        app_logger.error(
                            f"Критическая ошибка при установке параметра {param_name}: {str(e)}",
                            exc_info=True,
                        )
                        return False

                    app_logger.warning(
                        f"Повторная попытка ({attempts}/{config['retry_count']}) для параметра {param_name}"
                    )
                    time.sleep(config["action_delay"])

        app_logger.debug("Начало выбора параметров строк")
        for param_id, param_value, param_name in rows_parameters:
            if stop_event.is_set():
                app_logger.info(f"Остановка запрошена перед настройкой {param_name}")
                return True

            attempts = 0
            while attempts < config["retry_count"]:
                try:
                    if stop_event.is_set():
                        app_logger.info(
                            f"Прерывание настройки строкового параметра {param_name}"
                        )
                        return True

                    app_logger.debug(
                        f"Попытка {attempts + 1}: Поиск элемента {param_id}"
                    )

                    element = WebDriverWait(driver, config["page_timeout"]).until(
                        EC.presence_of_element_located((By.ID, param_id))
                    )
                    app_logger.debug(f"Элемент {param_id} найден")

                    select = Select(element)

                    available_options = [
                        f"{opt.get_attribute('value')}:{opt.text}"
                        for opt in select.options
                    ]
                    app_logger.debug(
                        f"Доступные значения для {param_name}: {', '.join(available_options)}"
                    )

                    select.select_by_value(param_value)
                    time.sleep(config["action_delay"])

                    if stop_event.is_set():
                        app_logger.info(f"Остановка после установки {param_name}")
                        return True

                    element = WebDriverWait(driver, config["page_timeout"]).until(
                        EC.presence_of_element_located((By.ID, param_id))
                    )
                    select = Select(element)
                    selected_value = select.first_selected_option.get_attribute("value")

                    if selected_value == param_value:
                        app_logger.info(
                            f"Параметр {param_name} успешно установлен в {param_value}"
                        )
                        break
                    else:
                        error_msg = (
                            f"Ожидалось {param_value}, получено {selected_value} "
                            f"для параметра {param_name}"
                        )
                        raise ValueError(error_msg)

                except Exception as e:
                    attempts += 1
                    app_logger.warning(
                        f"Попытка {attempts}: Ошибка установки параметра {param_name}\n"
                        f"Тип: {type(e).__name__}\nОписание: {str(e)}"
                    )

                    try:
                        page_source = driver.page_source
                        element_exists = param_id in page_source
                        app_logger.debug(
                            f"Элемент {param_id} присутствует в DOM: {element_exists}"
                        )
                    except Exception as e:
                        app_logger.debug(
                            f"Ошибка проверки DOM: {str(e)}", exc_info=True
                        )

                    time.sleep(config["action_delay"])

                    if attempts >= config["retry_count"]:
                        app_logger.error(
                            f"Неудача после {config['retry_count']} попыток для параметра {param_name}"
                        )
                        return False

        app_logger.info("Все параметры успешно установлены")
        return True

    except Exception as e:
        app_logger.error(
            f"Критическая ошибка при выборе параметров: {str(e)}\n"
            f"Трассировка: {traceback.format_exc()}"
        )
        return False


def download_data(
    driver,
    wait,
    config: dict,
    product_code: str,
    country: str,
    stop_event: Event,
    results_base_dir: str,
) -> bool:
    try:
        app_logger.debug(f"Начало обработки для кода {product_code} и страны {country}")

        if stop_event.is_set():
            app_logger.info("Запрос остановки перед началом загрузки данных")
            return True

        current_dir = os.getcwd()
        product_dir = os.path.join(results_base_dir)
        downloaded_file = None

        try:
            parse_all_pages = config["parse_all_pages"]
            all_headers = set()
            page_data_list = []
            exporters_data = {}
            max_widths = {}
            date_pattern = re.compile(r"^(\d{4}-M\d{2})")
            unit_pattern = re.compile(
                r",\s*({})\s*$".format("|".join(WEIGHT_UNITS.keys()))
            )
            page_number = 1

            while True:
                if stop_event.is_set():
                    app_logger.info("Остановка запрошена перед поиском кнопки экспорта")
                    return True

                app_logger.debug("Поиск кнопки экспорта в текстовый формат")
                text_button = wait.until(
                    EC.presence_of_element_located(
                        (
                            By.ID,
                            "ctl00_PageContent_GridViewPanelControl_ImageButton_Text",
                        )
                    )
                )

                if not text_button.is_displayed():
                    error_msg = "Кнопка экспорта не видна на странице"
                    app_logger.error(error_msg)
                    if downloaded_file and downloaded_file.is_file():
                        downloaded_file.unlink()
                    return False

                if stop_event.is_set():
                    app_logger.info("Остановка запрошена перед загрузкой файла")
                    return True

                app_logger.info("Инициирование загрузки файла")
                before_download = set(Path(current_dir).glob("*.txt"))
                driver.execute_script("arguments[0].click();", text_button)

                download_start_time = time.time()
                timeout = config["download_timeout"]
                downloaded_file = None

                while time.time() - download_start_time < timeout:
                    if stop_event.is_set():
                        app_logger.info("Прерывание во время ожидания загрузки файла")
                        return True

                    after_download = set(Path(current_dir).glob("*.txt"))
                    if new_files := after_download - before_download:
                        downloaded_file = new_files.pop()

                        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
                        new_name = downloaded_file.with_stem(
                            f"{downloaded_file.stem}_p{page_number}_{timestamp}"
                        )
                        downloaded_file.rename(new_name)
                        downloaded_file = new_name
                        page_number += 1

                        dl_time = time.time() - download_start_time
                        app_logger.info(
                            f"Файл загружен за {dl_time:.2f} сек: {downloaded_file}"
                        )
                        break
                    time.sleep(config["action_delay"])
                else:
                    error_msg = f"Не удалось загрузить файл за {timeout} секунд"
                    app_logger.error(error_msg)
                    if downloaded_file and downloaded_file.is_file():
                        downloaded_file.unlink()
                    return False

                current_page_data = []
                current_headers = []
                valid_columns = []

                with open(downloaded_file, "r", encoding="utf-8") as f:
                    raw_lines = [ln.strip() for ln in f if ln.strip()]

                for line_num, line in enumerate(raw_lines):
                    if stop_event.is_set():
                        app_logger.info("Прерывание обработки данных")
                        return True

                    parts = [p.strip('"').strip() for p in line.split("\t")]

                    if line_num == 0:
                        current_headers = ["Exporters"]
                        valid_columns = [True]

                        for idx, col in enumerate(parts[1:]):
                            if not col:
                                valid_columns.append(False)
                                continue

                            unit_match = unit_pattern.search(col)
                            if not unit_match:
                                found_unit = None
                                for unit in WEIGHT_UNITS.keys():
                                    if unit in col:
                                        found_unit = unit
                                        break

                                if not found_unit:
                                    error_msg = f"Неверный формат заголовка (отсутствует единица измерения): {col}"
                                    app_logger.error(error_msg)
                                    if downloaded_file and downloaded_file.is_file():
                                        downloaded_file.unlink()
                                    return False

                                column_unit = found_unit
                            else:
                                column_unit = unit_match.group(1)

                            if match := date_pattern.match(col):
                                header = match.group(1)
                                header = (
                                    header[:12] + "..." if len(header) > 15 else header
                                )
                                current_headers.append(header)
                                valid_columns.append(True)
                            else:
                                header = col[:12] + "..." if len(col) > 15 else col
                                valid_columns.append(False)

                        current_headers = [
                            h
                            for h, valid in zip(current_headers, valid_columns)
                            if valid
                        ]
                        all_headers.update(current_headers[1:])
                        app_logger.debug(
                            f"Обработаны заголовки: {len(current_headers)}"
                        )
                        continue

                    if len(parts) < 2 or not parts[0]:
                        continue

                    filtered_parts = []
                    for i, val in enumerate(parts):
                        if i < len(valid_columns) and valid_columns[i]:
                            filtered_parts.append(val)

                    if not filtered_parts:
                        continue

                    row_dict = {"Exporters": filtered_parts[0]}
                    for header, value in zip(current_headers[1:], filtered_parts[1:]):
                        try:
                            value = value.strip()
                            if not value or value == "-":
                                row_dict[header] = None
                                continue

                            if value.startswith("(") and value.endswith(")"):
                                value = "-" + value[1:-1]

                            value = value.replace(",", "")

                            if value.count(",") + value.count(".") > 1:
                                row_dict[header] = value
                                continue

                            value = value.replace(",", ".")

                            try:
                                if "." in value:
                                    parsed_value = float(value)
                                else:
                                    parsed_value = int(value)
                                    parsed_value = float(parsed_value)

                                source_factor = WEIGHT_UNITS[column_unit]
                                target_unit = config["quantity_unit"]
                                target_factor = WEIGHT_UNITS[target_unit]

                                converted_value = (
                                    parsed_value * source_factor / target_factor
                                )

                                if converted_value.is_integer():
                                    row_dict[header] = int(converted_value)
                                else:
                                    row_dict[header] = float(converted_value)

                            except ValueError:
                                row_dict[header] = value

                        except ValueError as e:
                            app_logger.debug(
                                f"Ошибка конвертации значения '{value}': {str(e)}"
                            )
                            row_dict[header] = value
                        except Exception as e:
                            app_logger.error(
                                f"Непредвиденная ошибка обработки значения '{value}': {str(e)}"
                            )
                            row_dict[header] = value

                    exporter = row_dict["Exporters"]

                    if parse_all_pages:
                        if exporter in exporters_data:
                            existing_data = exporters_data[exporter]
                            for header, value in row_dict.items():
                                if value is not None and (
                                    header not in existing_data or value != 0
                                ):
                                    existing_data[header] = value
                        else:
                            exporters_data[exporter] = row_dict.copy()

                        current_page_data = list(exporters_data.values())
                    else:
                        current_page_data.append(row_dict)

                if not parse_all_pages:
                    page_data_list.extend(current_page_data)
                else:
                    page_data_list = list(exporters_data.values())

                app_logger.info(
                    f"Обработано записей на текущей странице: {len(current_page_data)}"
                )

                if downloaded_file.is_file():
                    downloaded_file.unlink()

                if not parse_all_pages:
                    break

                try:
                    previous_button = wait.until(
                        EC.presence_of_element_located(
                            (
                                By.ID,
                                "ctl00_PageContent_GridViewPanelControl_ImageButton_Previous",
                            )
                        )
                    )

                    if previous_button.get_attribute("disabled"):
                        app_logger.debug("Достигнута первая страница, остановка цикла")
                        break

                    current_onclick = previous_button.get_attribute("onclick")
                    if not current_onclick:
                        app_logger.error(
                            "Атрибут onclick отсутствует у активной кнопки"
                        )
                        break

                    app_logger.debug(f"Текущий onclick перед кликом: {current_onclick}")

                    period_match = re.search(
                        r"SetValues\('prev','(\d+)'\)", current_onclick
                    )
                    if not period_match:
                        app_logger.error("Не удалось извлечь период из onclick")
                        break

                    current_period = period_match.group(1)
                    app_logger.debug(f"Текущий период: {current_period}")

                    ActionChains(driver).move_to_element(previous_button).pause(
                        config["action_delay"]
                    ).click().perform()
                    app_logger.debug("Клик выполнен")

                    def onclick_changed(driver) -> bool:
                        try:
                            new_button = driver.find_element(
                                By.ID,
                                "ctl00_PageContent_GridViewPanelControl_ImageButton_Previous",
                            )

                            if new_button.get_attribute("disabled"):
                                app_logger.debug("Кнопка стала неактивной после клика")
                                return True

                            new_onclick = new_button.get_attribute("onclick")

                            if not new_onclick:
                                app_logger.debug("Новый onclick отсутствует")
                                return False

                            new_period_match = re.search(
                                r"SetValues\('prev','(\d+)'\)", new_onclick
                            )
                            return (
                                new_period_match
                                and new_period_match.group(1) != current_period
                            )

                        except Exception as e:
                            app_logger.debug(f"Ошибка проверки: {str(e)}")
                            return False

                    try:
                        WebDriverWait(driver, config["page_timeout"]).until(
                            lambda d: (
                                onclick_changed(d)
                                or d.find_element(
                                    By.ID,
                                    "ctl00_PageContent_GridViewPanelControl_ImageButton_Previous",
                                ).get_attribute("disabled")
                            ),
                            message="Не удалось обнаружить изменение состояния",
                        )
                        app_logger.debug("Состояние кнопки изменилось")

                    except TimeoutException:
                        app_logger.error("Таймаут ожидания изменения состояния")
                        break

                    final_button = driver.find_element(
                        By.ID,
                        "ctl00_PageContent_GridViewPanelControl_ImageButton_Previous",
                    )

                    if final_button.get_attribute("disabled"):
                        app_logger.debug("Достигнута первая страница после перехода")
                        break

                    wait.until(
                        EC.presence_of_element_located(
                            (
                                By.ID,
                                "ctl00_PageContent_GridViewPanelControl_ImageButton_Text",
                            )
                        )
                    )
                    app_logger.debug("Новая страница подтверждена")

                except NoSuchElementException as e:
                    app_logger.error(f"Элемент навигации не найден: {str(e)}")
                    break
                except Exception as e:
                    app_logger.error(f"Критическая ошибка: {str(e)}")
                    break

            sorted_headers = ["Exporters"] + sorted(
                all_headers,
                key=lambda x: (int(x.split("-")[0][:4]), int(x.split("-M")[1])),
            )

            if parse_all_pages:
                max_widths = {h: len(h) for h in sorted_headers}
                for exporter_data in exporters_data.values():
                    for header in sorted_headers:
                        str_val = str(exporter_data.get(header, ""))
                        max_widths[header] = max(max_widths[header], len(str_val))

                sorted_exporters = sorted(exporters_data.keys())
                final_data = []
                for exporter in sorted_exporters:
                    exporter_data = exporters_data[exporter]
                    ordered_row = [exporter_data.get(h, None) for h in sorted_headers]
                    final_data.append(ordered_row)
            else:
                max_widths = {h: len(h) for h in sorted_headers}
                for row in page_data_list:
                    for header in sorted_headers:
                        str_val = str(row.get(header, ""))
                        max_widths[header] = max(max_widths[header], len(str_val))

                final_data = []
                for row_dict in page_data_list:
                    ordered_row = [row_dict.get(h, None) for h in sorted_headers]
                    final_data.append(ordered_row)

            if final_data:
                app_logger.debug("Создание структуры директорий")
                os.makedirs(product_dir, exist_ok=True)
                app_logger.debug(f"Директория создана: {product_dir}")

                new_filename = os.path.join(product_dir, f"{country}.xlsx")
                app_logger.debug(f"Целевой файл Excel: {new_filename}")

                with pd.ExcelWriter(new_filename, engine="xlsxwriter") as writer:
                    df = pd.DataFrame(final_data, columns=sorted_headers)

                    for col in df.columns[1:]:
                        try:
                            df[col] = pd.to_numeric(df[col])
                        except (ValueError, TypeError):
                            app_logger.debug(f"Не удалось преобразовать столбец {col}")
                            continue

                    df.to_excel(
                        writer,
                        sheet_name=country,
                        index=False,
                        startrow=1,
                        header=False,
                    )

                    workbook = writer.book
                    worksheet = writer.sheets[country]

                    header_format = workbook.add_format(
                        {
                            "border": 1,
                            "bold": True,
                            "align": "center",
                            "valign": "vcenter",
                            "text_wrap": True,
                        }
                    )

                    data_formats = [
                        workbook.add_format({"align": "left"}),
                        *[
                            workbook.add_format({"align": "right"})
                            for _ in sorted_headers[1:]
                        ],
                    ]

                    worksheet.set_row(0, 30)
                    for col_idx, header in enumerate(sorted_headers):
                        width = max_widths[header] + 2
                        fmt = (
                            data_formats[col_idx]
                            if col_idx < len(data_formats)
                            else data_formats[0]
                        )
                        worksheet.set_column(col_idx, col_idx, width, fmt)
                        worksheet.write(0, col_idx, header, header_format)

                    last_row = len(final_data)
                    last_col = len(sorted_headers) - 1

                    border_format = workbook.add_format({"border": 1})
                    worksheet.conditional_format(
                        0,
                        0,
                        last_row,
                        last_col,
                        {
                            "type": "formula",
                            "criteria": "=TRUE()",
                            "format": border_format,
                        },
                    )

                    if config["freeze_header"]:
                        worksheet.freeze_panes(1, 0)
                        app_logger.debug("Закрепление первой строки применено")

                        MAX_ROWS = 1048575
                        MAX_COLS = 16383
                        worksheet.conditional_format(
                            0,
                            0,
                            MAX_ROWS,
                            MAX_COLS,
                            {
                                "type": "formula",
                                "criteria": "=TRUE()",
                                "format": border_format,
                            },
                        )
                        app_logger.debug(
                            f"Границы применены ко всему листу A1:XFD{MAX_ROWS + 1}"
                        )

                    app_logger.info(f"Файл успешно сохранён: {new_filename}")
            else:
                app_logger.warning(
                    f"Нет данных для сохранения для кода {product_code} и страны {country}"
                )
                if downloaded_file and downloaded_file.is_file():
                    downloaded_file.unlink()
                return False
            return True
        except Exception as e:
            error_msg = f"Ошибка обработки данных: {str(e)}"
            if stop_event.is_set():
                app_logger.warning(f"Остановка по запросу: {error_msg}")
            else:
                app_logger.error(error_msg, exc_info=True)

            if downloaded_file and downloaded_file.is_file():
                try:
                    downloaded_file.unlink()
                    app_logger.debug("Временный файл удалён после ошибки")
                except Exception as file_err:
                    app_logger.error(f"Ошибка удаления файла: {str(file_err)}")

            return False

    except Exception as e:
        error_msg = f"Критическая ошибка: {str(e)}"
        app_logger.error(error_msg, exc_info=True)
        return False


def get_subproduct_codes(
    driver, wait, base_code: str, config: dict, stop_event: Event
) -> list[str]:
    try:
        if stop_event.is_set():
            app_logger.info("Остановка запрошена перед получением подкодов")
            return []

        app_logger.debug(f"Получение подкодов для базового кода {base_code}")
        product_select = wait.until(
            EC.presence_of_element_located(
                (By.ID, "ctl00_NavigationControl_DropDownList_Product")
            )
        )
        select = Select(product_select)

        if stop_event.is_set():
            app_logger.info("Остановка запрошена перед выбором базового кода")
            return []

        select.select_by_value(base_code)
        time.sleep(config["action_delay"])

        if stop_event.is_set():
            app_logger.info("Остановка запрошена после выбора базового кода")
            return []

        product_select = wait.until(
            EC.presence_of_element_located(
                (By.ID, "ctl00_NavigationControl_DropDownList_Product")
            )
        )
        select = Select(product_select)

        subcodes = []
        for option in select.options:
            if stop_event.is_set():
                app_logger.info("Остановка запрошена во время сбора подкодов")
                return []

            code = option.get_attribute("value")
            if code.startswith(base_code) and code != base_code and code.isdigit():
                subcodes.append(code)

        app_logger.debug(f"Найдено {len(subcodes)} подкодов для {base_code}")
        return sorted(subcodes)
    except Exception as e:
        app_logger.error(f"Ошибка получения подкодов для {base_code}: {str(e)}")
        return []


def process_single_code(
    driver, wait, product_code: str, config: dict, stop_event: Event, product_dir: str
) -> bool:
    try:
        app_logger.debug(f"Начало обработки одиночного кода {product_code}")

        if stop_event.is_set():
            app_logger.info("Остановка запрошена перед созданием директории")
            return True

        success = True
        total_countries = len(config["countries"])

        for idx, country in enumerate(config["countries"], 1):
            if stop_event.is_set():
                app_logger.info("Остановка запрошена во время обработки стран")
                return True

            app_logger.info(
                f"Обработка страны {country} для кода {product_code} ({idx}/{total_countries})"
            )

            if not select_parameters(
                driver, wait, product_code, country, config, stop_event
            ):
                app_logger.error(
                    f"Ошибка установки параметров для кода {product_code} и страны {country}"
                )
                success = False
                break

            if not download_data(
                driver, wait, config, product_code, country, stop_event, product_dir
            ):
                app_logger.error(
                    f"Ошибка загрузки данных для кода {product_code} и страны {country}"
                )
                success = False
                break

            app_logger.info(
                f"Успешно обработан код {product_code} для страны {country}"
            )

        return success

    except Exception as e:
        app_logger.error(f"Ошибка обработки кода {product_code}: {str(e)}")
        return False


def process_product_code(
    driver,
    wait,
    product_code: str,
    parse_depth: str,
    config: dict,
    stop_event: Event,
    results_base_dir: str,
) -> bool:
    try:
        app_logger.debug(
            f"Начало обработки кода продукта {product_code} с глубиной {parse_depth}"
        )
        code_length = len(product_code)

        target_length = {
            "level1": 2,
            "level2": 4,
            "level3": 6,
            "level4": 8,
        }[parse_depth]

        def cleanup_empty_dirs(start_path: str) -> None:
            for root, dirs, files in os.walk(start_path, topdown=False):
                for dir_name in dirs:
                    dir_path = os.path.join(root, dir_name)
                    try:
                        if not os.listdir(dir_path):
                            os.rmdir(dir_path)
                            app_logger.debug(f"Удалена пустая директория: {dir_path}")
                    except Exception as e:
                        app_logger.error(
                            f"Ошибка при удалении директории {dir_path}: {str(e)}"
                        )

        def create_hierarchy_path(code: str) -> str:
            base_dir = os.path.join(results_base_dir, code[:2])

            if len(code) <= 2:
                return base_dir

            paths = [base_dir]
            if len(code) >= 4:
                paths.append(code[:4])
            if len(code) >= 6:
                paths.append(code[:6])
            if len(code) >= 8:
                paths.append(code)

            return os.path.join(*paths)

        if parse_depth in ["level3", "level4"]:
            is_valid_length = (
                code_length == target_length
                if parse_depth == "level3"
                else 8 <= code_length <= 12
            )

            if not is_valid_length:
                current_codes = [product_code]
                final_codes = []
                processed_codes = set()

                try:
                    product_select = wait.until(
                        EC.presence_of_element_located(
                            (By.ID, "ctl00_NavigationControl_DropDownList_Product")
                        )
                    )
                    select = Select(product_select)
                    select.select_by_value("TOTAL")
                    time.sleep(config["action_delay"])
                except Exception as e:
                    app_logger.error(f"Ошибка при выборе 'TOTAL': {str(e)}")
                    return False

                while current_codes:
                    code = current_codes.pop(0)
                    if code in processed_codes:
                        continue

                    processed_codes.add(code)

                    code_steps = []
                    for i in [2, 4, 6]:
                        if i > len(code):
                            break
                        code_steps.append(code[:i])

                    for step_code in code_steps:
                        try:
                            product_select = wait.until(
                                EC.presence_of_element_located(
                                    (
                                        By.ID,
                                        "ctl00_NavigationControl_DropDownList_Product",
                                    )
                                )
                            )
                            select = Select(product_select)
                            select.select_by_value(step_code)
                            time.sleep(config["action_delay"])
                        except Exception as e:
                            app_logger.error(
                                f"Ошибка при выборе кода {step_code}: {str(e)}"
                            )
                            continue

                    subcodes = get_subproduct_codes(
                        driver, wait, code, config, stop_event
                    )

                    if parse_depth == "level3":
                        valid_codes = [c for c in subcodes if len(c) == 6]
                        next_codes = [c for c in subcodes if len(c) < 6]
                    else:
                        valid_codes = [c for c in subcodes if 8 <= len(c) <= 12]
                        next_codes = [c for c in subcodes if len(c) < 8]

                    final_codes.extend(valid_codes)
                    current_codes.extend(
                        [c for c in next_codes if c not in processed_codes]
                    )

                if not final_codes:
                    length_desc = (
                        "6 символов"
                        if parse_depth == "level3"
                        else "от 8 до 12 символов"
                    )
                    app_logger.warning(
                        f"Не найдено подкодов нужной длины ({length_desc}) для {product_code}. Пропуск обработки."
                    )
                    return True

                current_codes = sorted(set(final_codes))
                app_logger.info(
                    f"Найдены подкоды нужной длины для {product_code}: {', '.join(current_codes)}"
                )
            else:
                hierarchy_path = create_hierarchy_path(product_code)
                success = process_single_code(
                    driver, wait, product_code, config, stop_event, hierarchy_path
                )
                if not success:
                    cleanup_empty_dirs(os.path.join(results_base_dir, product_code[:2]))
                return success

        else:
            if code_length >= target_length:
                hierarchy_path = create_hierarchy_path(product_code)
                success = process_single_code(
                    driver, wait, product_code, config, stop_event, hierarchy_path
                )
                if not success:
                    cleanup_empty_dirs(os.path.join(results_base_dir, product_code[:2]))
                return success

            current_codes = [product_code]
            current_length = code_length

            while current_length < target_length:
                if stop_event.is_set():
                    app_logger.info("Остановка запрошена во время обработки подкодов")
                    return True

                next_codes = []
                for code in current_codes:
                    if stop_event.is_set():
                        app_logger.info(
                            "Остановка запрошена во время обработки подкодов"
                        )
                        return True

                    subcodes = get_subproduct_codes(
                        driver, wait, code, config, stop_event
                    )
                    next_codes.extend(subcodes)

                if not next_codes:
                    app_logger.warning(
                        f"Нет доступных подкодов для уровня {current_length}"
                    )
                    break

                current_codes = next_codes
                current_length += 2

        success = True
        processed_base_codes = set()

        app_logger.info(f"Найдено {len(current_codes)} подкодов для {product_code}")

        for code in current_codes:
            if stop_event.is_set():
                app_logger.info("Остановка запрошена во время обработки подкодов")
                return True

            hierarchy_path = create_hierarchy_path(code)

            if not process_single_code(
                driver, wait, code, config, stop_event, hierarchy_path
            ):
                success = False
                app_logger.error(f"Ошибка обработки подкода {code}")
                processed_base_codes.add(code[:2])

        for base_code in processed_base_codes:
            cleanup_empty_dirs(os.path.join(results_base_dir, base_code))

        return success

    except Exception as e:
        app_logger.error(f"Ошибка обработки кода {product_code}: {str(e)}")
        cleanup_empty_dirs(os.path.join(results_base_dir, product_code[:2]))
        return False


def process_data(driver, config: dict, stop_event: Event) -> bool:
    try:
        wait = WebDriverWait(driver, config["page_timeout"])
        app_logger.debug(f"Переход на страницу {PRODUCT_URL}")

        if stop_event.is_set():
            app_logger.info("Остановка запрошена перед загрузкой страницы")
            return True

        driver.get(PRODUCT_URL)
        app_logger.debug("Страница успешно загружена")

        if stop_event.is_set():
            app_logger.info("Остановка запрошена после загрузки страницы")
            return True

        current_dir = os.getcwd()
        current_time = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        results_base_dir = os.path.join(
            current_dir, "results", f"result_{current_time}"
        )
        app_logger.debug(f"Создание базовой директории результатов: {results_base_dir}")

        total_products = len(config["product_codes"])
        app_logger.info(f"Всего кодов продуктов для обработки: {total_products}")
        app_logger.info(f"Всего стран для обработки: {len(config['countries'])}")
        app_logger.info(f"Уровень парсинга: {config['parse_depth']}")

        try:
            app_logger.debug("Выбор 'All products' для начального состояния")
            product_select = wait.until(
                EC.presence_of_element_located(
                    (By.ID, "ctl00_NavigationControl_DropDownList_Product")
                )
            )
            select = Select(product_select)
            select.select_by_value("TOTAL")
            time.sleep(config["action_delay"])
        except Exception as e:
            app_logger.error(f"Ошибка при выборе 'All products': {str(e)}")
            return False

        for idx, product_code in enumerate(config["product_codes"], 1):
            if stop_event.is_set():
                app_logger.info("Остановка запрошена во время обработки продуктов")
                return True

            app_logger.info(
                f"\nОбработка кода продукта: {product_code} ({idx}/{total_products})"
            )

            if not validate_product_code(product_code):
                app_logger.warning(f"Неверный формат кода продукта: {product_code}")
                continue

            if stop_event.is_set():
                app_logger.info(
                    f"Остановка запрошена перед обработкой кода {product_code}"
                )
                return True

            success = process_product_code(
                driver,
                wait,
                product_code,
                config["parse_depth"],
                config,
                stop_event,
                results_base_dir,
            )

            if success:
                app_logger.info(f"Успешно завершена обработка кода {product_code}")
            else:
                app_logger.error(f"Ошибка при обработке кода {product_code}")

            if stop_event.is_set():
                app_logger.info(
                    f"Остановка запрошена после обработки кода {product_code}"
                )
                return True

            app_logger.debug("Ожидание перед следующим кодом продукта")
            time.sleep(config["action_delay"])

        app_logger.info("Обработка всех данных успешно завершена")
        return True

    except Exception as e:
        app_logger.error(
            f"Критическая ошибка при обработке данных: {str(e)}", exc_info=True
        )
        return False


def login_to_trademap(config: dict, stop_event: Event) -> bool:
    app_logger.info("Начало процесса входа в Trade Map")

    if stop_event.is_set():
        app_logger.info("Остановка запрошена перед началом входа в систему")
        return True

    if not check_chrome_installed():
        app_logger.error("Chrome не установлен. Вход невозможен")
        return False

    current_dir = os.getcwd()

    chrome_options = webdriver.ChromeOptions()
    prefs = {
        "download.default_directory": current_dir,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True,
        "profile.default_content_settings.popups": 0,
        "profile.default_content_setting_values.automatic_downloads": 1,
    }
    chrome_options.add_experimental_option("prefs", prefs)
    chrome_options.add_argument("--disable-popup-blocking")

    app_logger.debug("Инициализация драйвера Chrome")
    driver = webdriver.Chrome(options=chrome_options)
    wait = WebDriverWait(driver, config["page_timeout"])

    try:
        if stop_event.is_set():
            app_logger.info("Остановка запрошена перед загрузкой страницы")
            return True

        app_logger.debug(f"Переход на страницу {BASE_URL}")
        driver.get(BASE_URL)
        app_logger.debug("Страница успешно загружена")

        if stop_event.is_set():
            app_logger.info("Остановка запрошена перед авторизацией")
            return True

        app_logger.debug("Поиск кнопки логина")
        login_button = wait.until(
            EC.element_to_be_clickable((By.ID, "ctl00_MenuControl_marmenu_login"))
        )
        login_button.click()
        app_logger.debug("Кнопка логина успешно нажата")

        app_logger.debug("Ожидание полей ввода логина и пароля")
        username_field = wait.until(EC.presence_of_element_located((By.ID, "Username")))
        password_field = driver.find_element(By.ID, "Password")

        app_logger.debug("Ввод учетных данных")
        username_field.send_keys(config["username"])
        password_field.send_keys(config["password"])
        app_logger.debug("Учетные данные введены")

        app_logger.debug("Поиск кнопки подтверждения")
        submit_button = driver.find_element(By.CSS_SELECTOR, "button[value='login']")
        submit_button.click()
        app_logger.debug("Кнопка подтверждения нажата")

        if stop_event.is_set():
            app_logger.info("Остановка запрошена после авторизации")
            return True

        app_logger.debug("Проверка результата входа")
        if "Invalid username or password" in driver.page_source:
            error_msg = "Неверный логин или пароль"
            app_logger.error(error_msg)
            return False

        app_logger.debug("Проверка наличия капчи после входа")
        if not handle_captcha(driver, config, stop_event):
            app_logger.error("Не удалось пройти капчу")
            return False

        if stop_event.is_set():
            app_logger.info("Остановка запрошена перед обработкой данных")
            return True

        app_logger.debug("Проверка успешности входа")
        if BASE_URL not in driver.current_url:
            error_msg = "Неожиданная ошибка при входе"
            app_logger.error(error_msg)
            return False

        app_logger.info("Успешный вход в систему")

        app_logger.info("Начало обработки данных...")

        if not process_data(driver, config, stop_event):
            error_msg = "Ошибка при обработке данных"
            app_logger.error(error_msg)
            return False

        app_logger.info("Процесс успешно завершен")
        return True

    except Exception as e:
        error_msg = f"Критическая ошибка при работе с браузером: {str(e)}"
        app_logger.error(error_msg, exc_info=True)
        return False

    finally:
        app_logger.debug("Закрытие браузера")
        driver.quit()


def main(stop_event: Event) -> bool:
    try:
        app_logger.info("Запуск программы")

        if stop_event.is_set():
            app_logger.info("Остановка запрошена перед загрузкой конфигурации")
            return True

        app_logger.debug("Попытка загрузки конфигурационного файла")
        try:
            config_path = os.path.join("bot", "config.json")
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
                app_logger.debug("Конфигурационный файл успешно загружен")
        except FileNotFoundError:
            error_msg = "Файл конфигурации config.json не найден"
            app_logger.error(error_msg)
            return False
        except json.JSONDecodeError as e:
            error_msg = f"Ошибка формата JSON в файле конфигурации: {str(e)}"
            app_logger.error(error_msg)
            return False
        except Exception as e:
            error_msg = f"Непредвиденная ошибка при чтении конфига: {str(e)}"
            app_logger.error(error_msg, exc_info=True)
            return False

        if stop_event.is_set():
            app_logger.info("Остановка запрошена перед валидацией конфига")
            return True

        app_logger.debug("Начало валидации конфигурации")
        if not validate_config(config):
            app_logger.error("Валидация конфигурации не пройдена")
            return False
        app_logger.info("Валидация конфигурации успешно пройдена")

        if stop_event.is_set():
            app_logger.info("Остановка запрошена перед запуском основного процесса")
            return True

        app_logger.debug("Начало процесса входа и обработки данных")
        result = login_to_trademap(config, stop_event)

        if not result:
            app_logger.error("Процесс входа и обработки данных завершился с ошибкой")
            return False

        app_logger.info("Программа успешно завершена")
        return True

    except Exception as e:
        app_logger.critical(f"Критическая ошибка: {str(e)}", exc_info=True)
        return False
