# Book Parser API

API-сервис для загрузки книг в форматах `PDF` и `DOCX`, извлечения текста, разбиения на абзацы, предложения и слова, сохранения в SQLite и поиска по содержимому.

## Структура

- `main.py` - API
- `parser.py` - загрузка и парсинг файлов
- `splitter.py` - разбиение текста
- `database.py` - SQLite и модели таблиц
- `search.py` - поиск по словам, предложениям и абзацам
- `storage/uploads` - загруженные файлы
- `storage/db` - база данных SQLite

## Запуск

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
uvicorn main:app --reload
```

## Запуск в Docker

```bash
docker-compose up -d --build
```

API будет доступно на `http://localhost:8000`.

Данные сохраняются в локальную папку `storage`, которая примонтирована в контейнер.

## Эндпоинты

- `POST /documents/upload` - загрузка файла через multipart/form-data
- `POST /documents/from-path` - загрузка по пути к локальному файлу
- `GET /documents` - список документов
- `GET /documents/{document_id}` - данные документа и сохраненная структура текста
- `GET /search/word?query=...&exact=true|false` - поиск по словам
- `GET /search/sentence?query=...` - поиск по предложениям
- `GET /search/paragraph?query=...` - поиск по абзацам
- `GET /search/phrase?query=...` - поиск по фразе
