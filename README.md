## Запуск в Docker

```bash
docker-compose up -d --build
```

API будет доступно на `http://localhost:8000`.


## Эндпоинты

- `POST /documents/upload` - загрузка файла через multipart/form-data
- `POST /documents/from-path` - загрузка по пути к локальному файлу
- `GET /documents` - список документов
- `GET /documents/{document_id}` - данные документа и сохраненная структура текста
- `GET /search/word?query=...&exact=true|false` - поиск по словам
- `GET /search/sentence?query=...` - поиск по предложениям
- `GET /search/paragraph?query=...` - поиск по абзацам
- `GET /search/phrase?query=...` - поиск по фразе
