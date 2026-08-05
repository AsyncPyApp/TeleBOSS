# TeleBOSS

[![Version](https://img.shields.io/badge/version-5.0.0-blue)](CHANGELOG.md)
[![Status](https://img.shields.io/badge/status-beta%20%7C%20в%20разработке-orange)](#)
[![Codename](https://img.shields.io/badge/codename-Deuterium%20Discharge-8A2BE2)](src/teleboss/shared/config.py)
[![Python](https://img.shields.io/badge/python-3.14.6%2B-yellow?logo=python&logoColor=white)](#запуск)
[![GitHub stars](https://img.shields.io/github/stars/AsyncPyApp/TeleBOSS?style=flat)](https://github.com/AsyncPyApp/TeleBOSS/stargazers)
[![GitHub forks](https://img.shields.io/github/forks/AsyncPyApp/TeleBOSS?style=flat)](https://github.com/AsyncPyApp/TeleBOSS/forks)
[![GitHub issues](https://img.shields.io/github/issues/AsyncPyApp/TeleBOSS)](https://github.com/AsyncPyApp/TeleBOSS/issues)
[![Last commit](https://img.shields.io/github/last-commit/AsyncPyApp/TeleBOSS)](https://github.com/AsyncPyApp/TeleBOSS/commits/main)
[![Contributors](https://img.shields.io/github/contributors/AsyncPyApp/TeleBOSS)](https://github.com/AsyncPyApp/TeleBOSS/graphs/contributors)

Telegram-бот для модерации чатов через голосования: бан, кик, настройки, админы и прочее — решает группа, а не один админ.

## Происхождение

Это **самостоятельный** репозиторий (своя линия развития), а не активный форк для синхронизации с upstream.

Исходный TeleBOSS создал **[Allnorm](https://github.com/Allnorm)** (aka DvadCat): [Allnorm/TeleBOSS](https://github.com/Allnorm/TeleBOSS).  
История коммитов и changelog сохранены в дань уважения автору — без них этого проекта не было бы.

## Запуск

Требуется **Python 3.14.6+** (более старые версии не поддерживаются).

Разработка (editable, из корня репозитория):

```bash
pip install -e .
# положи токен и настройки в конфиг бота
teleboss
# или: python main.py
```

Продакшен: обычная (не editable) установка пакета с зафиксированной версией. Для тестов: `pip install -r requirements-dev.txt`, затем `pytest`. Локально предпочтительно использовать `.venv` репозитория.

## Что где лежит

- `main.py` — тонкая точка входа (проверка Python 3.14.6+ до импорта продукта); консольная команда `teleboss` из `pyproject.toml`
- `src/teleboss/` — пакет (`app`, `domain`, `shared`, `voting`, `plugin_loader`); импорты `teleboss.*`
- `plugins/` рядом с установкой — каталог плагинов и/или entry points `teleboss.plugins` (по конфигу)

## Changelog и версии

- История релизов: корневой [`CHANGELOG.md`](CHANGELOG.md).
- Версия / дата сборки / мин. совместимость: `src/teleboss/shared/config.py` (`ConfigData`).
- Бот при апгрейде дополнительно показывает тело релизного git-коммита.
- Бамп версии — только осознанный релиз (не «заодно» с обычным фиксом); на релиз синхронизируй `ConfigData` + `CHANGELOG.md` + коммит.

## Backlog

Отложенные эпики и долг (не в текущей работе): [`.cursor/plans/BACKLOG.md`](.cursor/plans/BACKLOG.md).
