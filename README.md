# TeleBOSS

Telegram-бот для модерации чатов через голосования: бан, кик, настройки, админы и прочее — решает группа, а не один админ.

Сейчас **3.3.2** «Deuterium Discharge».

## Запуск

```bash
pip install -r requirements.txt
# положи токен и настройки в конфиг бота
python main.py
```

Для разработки тестов: `pip install -r requirements-dev.txt`, затем `pytest`.

## Что где лежит

- `main.py` — точка входа
- `teleboss/` — основной код (shared, voting, domain, app, плагины)
- корневые `utils.py`, `prevote.py`, `postvote.py` и т.п. — тонкие шимы для старых импортов
- `plugins/` рядом с установкой — свои команды (если есть)

## Changelog и версии

- История релизов: корневой [`CHANGELOG.md`](CHANGELOG.md).
- Версия / дата сборки / мин. совместимость: `teleboss/shared/config.py` (`ConfigData`).
- Бот при апгрейде дополнительно показывает тело релизного git-коммита.
- Бамп версии — только осознанный релиз (не «заодно» с обычным фиксом); на релиз синхронизируй `ConfigData` + `CHANGELOG.md` + коммит.
