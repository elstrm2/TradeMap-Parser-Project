# TradeMap Parser Project 🤖

Проект для автоматизированного сбора данных с TradeMap с графическим интерфейсом

## 📝 Описание

Программа автоматизирует сбор и анализ торговых данных с TradeMap Имеет два интерфейса:

- 🖥️ Desktop GUI на CustomTkinter с поддержкой системного трея
- 🌐 Web интерфейс на Flask

### ✨ Основные возможности:

- 🔄 Автоматизированный сбор данных через Selenium WebDriver
- 🖥️ Десктопный и веб-интерфейсы управления
- 📊 Экспорт данных в Excel через Pandas
- ⚙️ Гибкая настройка через JSON конфигурацию
- 🔒 Поддержка авторизации на TradeMap
- 🎯 Настраиваемая глубина парсинга (4 уровня)
- 🌓 Темная/светлая тема интерфейса
- 🔔 Системные уведомления через Pystray
- 🖼️ Обработка изображений через Pillow
- 🔄 Асинхронные HTTP запросы через Requests
- 🤖 Автоматическая обработка капчи
- 📑 Подробное логирование операций

## 🛠 Технологический стек:

### Backend:

- Python 3.x - основной язык
- Selenium WebDriver - автоматизация браузера
- Flask - веб-сервер
- Requests - HTTP клиент
- Pandas - обработка данных

### Frontend:

- CustomTkinter - десктопный GUI
- HTML/CSS/JS - веб-интерфейс
- Pystray - системный трей
- Pillow - обработка изображений

## 🔧 Установка

### 1. Использование готовых файлов (рекомендуется):

Готовые исполняемые файлы и исходный код доступны в разделе [Releases](https://github.com/elstrm2/TradeMap-Parser-Project/releases):

- 📥 **TradeMap-Parser-vX.X.X.zip** - архив с исполняемыми файлами
  - 🖥️ gui_app.exe - для запуска графического интерфейса
  - 🌐 app.exe - для запуска веб-версии
- 📦 **Source code (zip)** - архив с исходным кодом
- 📦 **Source code (tar.gz)** - исходный код в формате tar.gz

Для установки:

1. Скачайте последний релиз **TradeMap-Parser-vX.X.X.zip**
2. Распакуйте архив в удобное место
3. Запустите нужный файл:
   - 🖥️ gui_app.exe - для графического интерфейса
   - 🌐 app.exe - для веб-версии

### 2. Клонирование репозитория:

⚠️ Важно: Для корректной загрузки исполняемых файлов необходим Git LFS!

1. Установите Git LFS:

   - Скачайте установщик с [git-lfs.github.com](https://git-lfs.github.com/)
   - Запустите установщик
   - Выполните команду: `git lfs install`

2. Склонируйте репозиторий:
   ```bash
   git clone https://github.com/elstrm2/TradeMap-Parser-Project.git
   cd TradeMap-Parser-Project
   git lfs pull
   ```

### 3. Сборка из исходников:

1. Клонируйте репозиторий или скачайте исходный код из Releases
2. Создайте виртуальное окружение:
   ```bash
   python -m venv venv
   .\venv\Scripts\activate
   ```
3. Установите зависимости:
   ```bash
   pip install -r requirements.txt
   pip install pyinstaller
   ```
4. Соберите exe файлы:
   ```bash
   pyinstaller --onefile gui_app.py
   pyinstaller --onefile app.py
   ```
5. Готовые файлы появятся в папке dist/

### 4. Запуск из исходников:

1. Выполните шаги 1-3 из варианта "Сборка из исходников"
2. Скачайте ChromeDriver для вашей версии Chrome
3. Добавьте путь к драйверу в системные переменные
4. Запустите скрипты:
   ```bash
   python gui_app.py  # для GUI версии
   python app.py      # для веб-версии
   ```

## 📦 Запуск

### 🖥️ Использование GUI версии:

1. Запустите gui_app.exe
2. Используйте интерфейс для управления парсером
3. Поддерживается сворачивание в трей

#### Описание GUI интерфейса:

- 🔵 **Start Server** - Запуск сервера парсера
- 🔴 **Stop Server** - Остановка работы сервера
- ⬇️ **Minimize to Tray** - Сворачивание программы в трей
- 🌐 **Open Server Interface** - Открытие веб-интерфейса в браузере
- 🌓 **Theme Switch** - Переключение между светлой/темной темой (☀/☾)

#### Индикаторы:

- 📊 **Progress Bar** - Показывает статус загрузки сервера
- 💬 **Server Log** - Отображает системные сообщения и ошибки
- 🚦 **Server Status** - Текущий статус сервера:
  - 🔴 Stopped - Сервер остановлен
  - 🟡 Starting - Сервер запускается
  - 🟢 Running - Сервер работает

### 🌐 Использование Web версии:

1. Запустите app.exe
2. Откройте браузер и перейдите по адресу [localhost](http://localhost:5000)
3. Используйте веб-интерфейс для управления

#### Описание Web интерфейса:

#### Основные элементы управления:

- 🟢 **Запустить** - Запуск процесса парсинга
- 🔴 **Остановить** - Остановка парсинга
- 🌓 **Переключатель темы** - Смена светлой/темной темы интерфейса

#### Панель конфигурации:

- 📝 **Логин/Пароль** - Учетные данные для TradeMap
- 📦 **Коды товаров** - Список кодов через запятую (например "3102")
- 🌍 **Страны** - Список стран на английском через запятую
- ⚙️ **Настройки парсинга**:
  - ⏱️ Задержка действий (0.1-10 сек)
  - ⌛ Таймаут страницы (1-60 сек)
  - 🔄 Количество попыток (1-10)
  - 📥 Таймаут загрузки (5-300 сек)
  - 🤖 Таймаут капчи (30-300 сек)
  - 📌 Закрепление заголовка (да/нет)
  - 📄 Парсинг страниц (все/последняя)
  - ⚖️ Единица измерения (кг/тонны)
  - 🎯 Глубина парсинга (уровни 1-4)

#### Индикаторы:

- 🚦 **Статус бота** - Текущее состояние парсера
- 🕒 **Время обновления** - Последнее обновление статуса
- ❌ **Последняя ошибка** - Информация об ошибках
- 🔄 **Очистка ошибок** - Слайдер для сброса ошибок

## ⚙️ Конфигурация

Настройки парсера хранятся в файле `config.json`:

### Параметры авторизации:

- 👤 `username` - email для входа на TradeMap
- 🔑 `password` - пароль для входа

## ⚙️ Параметры конфигурации

### 🔑 Параметры авторизации

| Параметр   | Описание                     | Значение по умолчанию |
| ---------- | ---------------------------- | --------------------- |
| `username` | Email для входа на TradeMap  | `""` (пустой)         |
| `password` | Пароль для входа на TradeMap | `""` (пустой)         |

### 📊 Параметры сбора данных

| Параметр          | Описание                                     | Значение по умолчанию |
| ----------------- | -------------------------------------------- | --------------------- |
| `product_codes`   | Коды товаров для анализа (например ["3102"]) | `[]`                  |
| `countries`       | Список стран для анализа (на английском)     | `[]`                  |
| `parse_depth`     | Глубина анализа данных (level1-level4)       | `"level1"`            |
| `quantity_unit`   | Единица измерения количества                 | `"Kilograms"`         |
| `parse_all_pages` | Парсинг всех доступных страниц               | `false`               |

### ⚡ Технические параметры

| Параметр           | Описание                     | Диапазон   | По умолчанию |
| ------------------ | ---------------------------- | ---------- | ------------ |
| `action_delay`     | Задержка между действиями    | 0.1-10 сек | `0.5`        |
| `page_timeout`     | Ожидание загрузки страницы   | 1-60 сек   | `5`          |
| `retry_count`      | Количество повторных попыток | 1-10       | `3`          |
| `download_timeout` | Таймаут загрузки             | 5-300 сек  | `30`         |
| `captcha_timeout`  | Время ожидания капчи         | 30-300 сек | `60`         |
| `freeze_header`    | Фиксация заголовков таблицы  | true/false | `true`       |

### Пример конфигурации:

```json
{
  "username": "user@example.com",
  "password": "password123",
  "product_codes": ["3102"],
  "countries": ["Canada"],
  "action_delay": 0.5,
  "page_timeout": 5,
  "retry_count": 3,
  "download_timeout": 30,
  "captcha_timeout": 60,
  "freeze_header": false,
  "parse_all_pages": false,
  "quantity_unit": "Kilograms",
  "parse_depth": "level4"
}
```

### ⚙️ Настройка конфигурации:

Есть два способа настройки параметров:

1. 📝 Ручное редактирование:

- Откройте файл bot/config.json в любом текстовом редакторе
- Измените нужные параметры
- Сохраните файл

2. 🌐 Через веб-интерфейс:

- Запустите программу
- Откройте [localhost](http://localhost:5000) в браузере
- Используйте форму настройки для изменения параметров
- Все изменения сохранятся автоматически

⚠️ Важно: для работы программы необходимы валидные учетные данные TradeMap

## 📄 Лицензия

Проект распространяется под MIT лицензией с ограничением на коммерческое использование.
Подробности в файле [LICENSE](LICENSE.txt).

## 📞 Контакты

При возникновении вопросов или проблем создавайте issue в репозитории.
