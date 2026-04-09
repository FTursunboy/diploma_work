## Запуск в Docker

```bash
docker-compose up -d --build
```

Веб-интерфейс и API будут доступны на `http://localhost:8000`.


## Веб-интерфейс

Откройте в браузере `http://localhost:8000`:

- список документов (фильтр по имени)
- загрузка PDF/DOCX
- поиск по словам/предложениям/абзацам/фразе (по всем документам или по выбранному документу)
- просмотр текста и структуры (абзацы/предложения/слова)
- скачивание исходного файла
- удаление документа

API-документация: `http://localhost:8000/docs`.


## Эндпоинты

- `POST /documents/upload` - загрузка файла через multipart/form-data
- `POST /documents/from-path` - загрузка по пути к локальному файлу
- `GET /documents` - список документов
- `GET /documents/{document_id}` - данные документа и сохраненная структура текста
- `GET /documents/{document_id}/file` - скачать исходный файл
- `DELETE /documents/{document_id}` - удалить документ
- `GET /search/word?query=...&exact=true|false` - поиск по словам
- `GET /search/sentence?query=...` - поиск по предложениям
- `GET /search/paragraph?query=...` - поиск по абзацам
- `GET /search/phrase?query=...` - поиск по фразе

Во всех `GET /search*` эндпоинтах можно передать `document_id=...`, чтобы искать только внутри одного документа.
