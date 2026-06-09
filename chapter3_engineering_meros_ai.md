# ГЛАВА 3. ПРОЕКТИРОВАНИЕ И ПРОГРАММНАЯ РЕАЛИЗАЦИЯ MVP-СИСТЕМЫ MEROS.AI

## 3.1. Архитектура MVP-системы Meros.AI

MVP-система Meros.AI представляет собой веб-приложение для загрузки, хранения, структурной обработки и интеллектуального поиска по электронным документам. Система разработана для работы с текстовыми файлами форматов PDF, DOC и DOCX и предназначена для анализа содержания документов, поиска информации и получения краткой AI-аннотации.

Архитектура системы построена по клиент-серверному принципу. Пользователь взаимодействует с системой через веб-интерфейс, реализованный на HTML, CSS и JavaScript. Серверная часть реализована на языке Python с использованием фреймворка FastAPI. Для хранения данных используется реляционная база данных, доступ к которой выполняется через SQLAlchemy ORM. В Docker-среде применяется MySQL.

Поставить главный экран системы.

Рис. 3.1. Главный экран MVP-системы Meros.AI

В состав системы входят следующие основные подсистемы:

- подсистема авторизации и разграничения прав доступа;
- подсистема загрузки и хранения документов;
- подсистема извлечения и структурирования текста;
- подсистема обычного поиска;
- подсистема семантического поиска;
- подсистема генерации AI-аннотации;
- подсистема журналирования AI-запросов;
- административная панель.

Общая схема работы системы представлена следующим образом:

```text
Пользователь
    |
    v
Frontend HTML/CSS/JS
    |
    v
REST API FastAPI
    |
    +--> Авторизация и роли пользователей
    |
    +--> Загрузка PDF/DOC/DOCX
    |
    +--> Извлечение текста
    |
    +--> Разбиение текста на абзацы, предложения, слова
    |
    +--> Сохранение структуры в базе данных
    |
    +--> Фоновая AI-обработка
           |
           +--> создание embeddings
           +--> семантическая индексация
           +--> генерация AI-аннотации
           +--> запись AI-логов
```

Поставить схему архитектуры системы.

Рис. 3.2. Архитектура MVP-системы Meros.AI

Ключевая особенность архитектуры заключается в том, что обычная обработка документа и AI-обработка разделены. После загрузки файла система сразу выполняет базовый парсинг: извлекает текст, разбивает его на структурные элементы и сохраняет в базе данных. После этого запускается фоновая AI-задача, которая создаёт embedding-векторы и AI-аннотацию. Это позволяет не заставлять пользователя ждать завершения обращений к OpenAI API.

Фоновый запуск AI-обработки реализован через отдельный поток. Фрагмент кода представлен в листинге 3.1.

```python
def run_ai_processing_job(document_id: int) -> None:
    db = SessionLocal()
    try:
        DocumentParserService(db).run_ai_processing_for_document(document_id=document_id)
    finally:
        db.close()


def start_ai_processing_job(document_id: int) -> None:
    thread = threading.Thread(
        target=run_ai_processing_job,
        args=(document_id,),
        name=f"ai-processing-document-{document_id}",
        daemon=True,
    )
    thread.start()
```

Листинг 3.1. Запуск фоновой AI-обработки документа

Данный подход решает проблему длительной загрузки документа. Пользователь получает ответ от сервера после основного парсинга, а AI-индексация продолжается отдельно.

## 3.2. Реализация подсистемы обработки текстовых данных

Подсистема обработки текстовых данных отвечает за преобразование загруженного файла в структурированную форму. На вход система получает электронный документ, а на выходе формирует полный текст, абзацы, предложения и слова.

Загрузка документа выполняется через endpoint `POST /documents/upload`. Пользователь передаёт файл и метаданные: название, автора, издательство, год публикации и библиографическое описание.

Поставить экран загрузки документа.

Рис. 3.3. Форма загрузки документа

После получения файла сервер проверяет его расширение и сохраняет файл во внутреннее хранилище. Затем создаётся запись в таблице `documents`.

Фрагмент реализации загрузки документа представлен в листинге 3.2.

```python
@router.post("/documents/upload")
def upload_document(
    file: UploadFile = File(...),
    title: str | None = Form(None),
    author: str | None = Form(None),
    publication_year: int | None = Form(None),
    publisher: str | None = Form(None),
    bibliography: str | None = Form(None),
    db: Session = Depends(get_db),
    _=Depends(require_moderator),
) -> dict:
    parser = DocumentParserService(db)
    file_type, stored_path = parser.save_upload_file(file)

    document = parser.create_uploaded_document(
        filename=file.filename,
        file_type=file_type,
        stored_path=stored_path,
        title=(title or "").strip() or None,
        author=(author or "").strip() or None,
        publisher=(publisher or "").strip() or None,
        publication_year=publication_year,
        bibliography=(bibliography or "").strip() or None,
    )

    counts = parser.parse_document(document)
    db.refresh(document)

    if document.status == "parsed":
        start_ai_processing_job(document.id)
```

Листинг 3.2. Endpoint загрузки документа

Для PDF-файлов используется библиотека `pypdf`, для DOCX-файлов используется `python-docx`, а для DOC-файлов применяется извлечение текста через соответствующий обработчик. После извлечения текст нормализуется: удаляются лишние переносы строк, приводятся к единому виду пробелы и пустые строки.

Основной pipeline обработки документа:

```text
Файл
  -> проверка формата
  -> сохранение файла
  -> извлечение текста
  -> нормализация текста
  -> разбиение на абзацы
  -> разбиение абзацев на предложения
  -> разбиение предложений на слова
  -> сохранение в базу данных
```

Фрагмент структурного разбиения текста представлен в листинге 3.3.

```python
paragraphs = split_paragraphs(structured_text)
sentence_counter = 0
word_counter = 0

for paragraph_index, paragraph_text in enumerate(paragraphs, start=1):
    paragraph = Paragraph(
        document_id=document.id,
        paragraph_index=paragraph_index,
        text=paragraph_text,
    )
    self._db.add(paragraph)
    self._db.flush()

    sentences = split_sentences(paragraph_text)
    for sentence_index, sentence_text in enumerate(sentences, start=1):
        sentence_counter += 1
        sentence = Sentence(
            document_id=document.id,
            paragraph_id=paragraph.id,
            sentence_index=sentence_index,
            text=sentence_text,
        )
        self._db.add(sentence)
        self._db.flush()

        for word_text in split_words(sentence_text):
            word_counter += 1
            self._db.add(
                Word(
                    document_id=document.id,
                    sentence_id=sentence.id,
                    word_index=word_counter,
                    word=word_text,
                )
            )
```

Листинг 3.3. Разбиение текста на абзацы, предложения и слова

Такое представление данных позволяет выполнять поиск на разных уровнях: по отдельным словам, предложениям, абзацам и фразам.

Поставить экран просмотра структуры документа.

Рис. 3.4. Структурное представление документа

## 3.3. Реализация подсистемы семантического анализа

Семантический анализ в системе Meros.AI построен на основе embedding-векторов. Embedding представляет собой числовой вектор, отражающий смысл текста. В отличие от обычного поиска по совпадению символов, семантический поиск позволяет находить фрагменты, близкие к запросу по смыслу.

Для получения embedding-векторов используется OpenAI Embeddings API. В системе применяется модель `text-embedding-3-small`, так как она подходит для семантического поиска и является экономичной.

Класс получения embeddings представлен в листинге 3.4.

```python
class EmbeddingService:
    def __init__(self, *, model: str | None = None):
        self.model = model or os.getenv(
            "OPENAI_EMBEDDING_MODEL",
            "text-embedding-3-small",
        )
        if not self.is_configured():
            raise RuntimeError("OPENAI_API_KEY is not configured.")

        from openai import OpenAI
        self._client = OpenAI()

    def get_embedding_result(self, text: str) -> EmbeddingResult:
        normalized = " ".join((text or "").split())
        if not normalized:
            raise ValueError("Text for embedding must not be empty.")

        started = time.perf_counter()
        response = self._client.embeddings.create(
            model=self.model,
            input=normalized,
            encoding_format="float",
        )
        duration_ms = int((time.perf_counter() - started) * 1000)

        return EmbeddingResult(
            embedding=list(response.data[0].embedding),
            model=str(getattr(response, "model", None) or self.model),
            prompt_tokens=response.usage.prompt_tokens,
            total_tokens=response.usage.total_tokens,
            duration_ms=duration_ms,
        )
```

Листинг 3.4. Получение embedding-вектора через OpenAI API

После загрузки документа система создаёт два типа семантических индексов:

- chunks документа;
- блоки абзацев.

Chunks используются как резервный механизм семантического поиска. Блоки абзацев применяются как основной способ, потому что они лучше соответствуют логической структуре текста и позволяют возвращать пользователю более точные фрагменты.

Формирование embedding-блоков абзацев выполняется в методе `index_document_paragraphs`. Упрощённая логика представлена ниже:

```text
Абзацы документа
  -> объединение коротких абзацев в блоки
  -> отправка каждого блока в embeddings API
  -> получение vector
  -> сохранение в paragraph_embedding_blocks
  -> запись операции в ai_request_logs
```

Фрагмент создания embedding-блоков представлен в листинге 3.5.

```python
for block_index, block in enumerate(blocks, start=1):
    result = embedding_service.get_embedding_result(block["text"])
    embedding_json = json.dumps(result.embedding, separators=(",", ":"))

    self._db.add(
        ParagraphEmbeddingBlock(
            document_id=document.id,
            block_index=block_index,
            start_paragraph_index=block["start_paragraph_index"],
            end_paragraph_index=block["end_paragraph_index"],
            block_text=block["text"],
            embedding=embedding_json,
            embedding_model=result.model,
        )
    )
```

Листинг 3.5. Сохранение embedding-блока абзацев

Для сравнения запроса пользователя с сохранёнными embedding-векторами используется cosine similarity. Формула косинусного сходства:

```text
similarity(A, B) = (A · B) / (||A|| * ||B||)
```

Реализация cosine similarity представлена в листинге 3.6.

```python
def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0

    dot = 0.0
    left_norm = 0.0
    right_norm = 0.0
    for a, b in zip(left, right):
        dot += a * b
        left_norm += a * a
        right_norm += b * b

    if left_norm <= 0 or right_norm <= 0:
        return 0.0
    return dot / (math.sqrt(left_norm) * math.sqrt(right_norm))
```

Листинг 3.6. Вычисление косинусной близости векторов

В системе используется не только чистое векторное сходство. Для повышения качества поиска итоговый score формируется как гибридная оценка:

```text
final_score =
    semantic_score * 0.50
  + lexical_score  * 0.20
  + expansion_score * 0.15
  + structure_score * 0.15
```

Гибридный подход позволяет учитывать не только смысловую близость, но и совпадение ключевых слов, расширение запроса и структурное положение абзаца в документе.

Фрагмент ранжирования результатов представлен в листинге 3.7.

```python
semantic_score = cosine_similarity(query_embedding, paragraph_embedding)
lexical_score = _lexical_score(query, block_text)
expansion_score = _expansion_score(expanded_terms, block_text)
structure_score = _structural_score(
    block_text,
    int(block.start_paragraph_index),
    int(totals.get(int(block.document_id), 0)),
)

final_score = round(
    max(0.0, semantic_score) * 0.5
    + lexical_score * 0.2
    + expansion_score * 0.15
    + structure_score * 0.15,
    4,
)
```

Листинг 3.7. Расчёт итоговой оценки релевантности

После первичного ранжирования применяется дополнительный этап reranking с использованием модели `gpt-5-nano`. На этом этапе системе передаются только лучшие кандидаты, а модель возвращает порядок их релевантности.

```text
Запрос пользователя
  -> embedding запроса
  -> cosine similarity
  -> гибридный score
  -> top candidates
  -> reranking
  -> итоговый список результатов
```

Поставить экран семантического поиска.

Рис. 3.5. Результаты семантического поиска

## 3.4. Реализация генерации AI-аннотации

Помимо семантического поиска, в системе реализована автоматическая генерация краткой аннотации документа. Аннотация создаётся после загрузки документа в фоновом режиме и сохраняется в поле `ai_summary`.

Для генерации аннотации используется модель `gpt-5-nano`. В prompt передаются метаданные документа и выбранные фрагменты текста. Ответ формируется на таджикском языке кириллицей.

Фрагмент prompt представлен в листинге 3.8.

```python
return (
    "Составь краткую аннотацию книги для электронной библиотеки.\n"
    "Ответь на таджикском языке, кириллицей, 2 коротких абзаца, без списков.\n"
    "Опирайся в первую очередь на фрагменты текста и метаданные. "
    "Если информации недостаточно, не выдумывай факты.\n\n"
    f"Метаданные:\n{meta}\n\n"
    f"Фрагменты текста книги:\n{context}"
)
```

Листинг 3.8. Prompt для генерации AI-аннотации

Для снижения стоимости и ускорения ответа в запросе указывается минимальный уровень reasoning:

```python
response = client.responses.create(
    model=self.model,
    input=prompt,
    reasoning={"effort": "minimal"},
    max_output_tokens=1200,
)
```

Листинг 3.9. Генерация AI-аннотации через OpenAI Responses API

Перед отправкой текста в модель система выбирает наиболее информативные фрагменты. Для этого применяется ранжирование абзацев по ключевым словам и положению в документе. Приоритет получают фрагменты, содержащие слова, связанные с целью, задачами, результатами, выводами и актуальностью.

Поставить экран AI-аннотации.

Рис. 3.6. AI-аннотация документа

## 3.5. Проектирование базы данных и модели хранения информации

Для хранения данных используется реляционная модель. Работа с базой данных организована через SQLAlchemy ORM. Основные модели данных представлены в файле `database.py`.

Ключевые таблицы системы:

- `users`;
- `documents`;
- `paragraphs`;
- `sentences`;
- `words`;
- `document_chunks`;
- `paragraph_embedding_blocks`;
- `ai_request_logs`.

Поставить ER-диаграмму базы данных.

Рис. 3.7. ER-диаграмма базы данных Meros.AI

Модель `Document` хранит основную информацию о загруженном документе: имя файла, тип, путь хранения, метаданные, полный текст, AI-аннотацию и статусы обработки.

Фрагмент модели документа представлен в листинге 3.10.

```python
class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str] = mapped_column(String(10), nullable=False)
    stored_path: Mapped[str] = mapped_column(String(500), nullable=False)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    author: Mapped[str | None] = mapped_column(String(255), nullable=True)
    publisher: Mapped[str | None] = mapped_column(String(255), nullable=True)
    publication_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bibliography: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_status: Mapped[str] = mapped_column(String(20), default="pending")
    full_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="uploaded")
```

Листинг 3.10. Модель документа

Для хранения embedding-векторов используется текстовое поле, в котором вектор сохраняется как JSON-массив. Такой подход упрощает реализацию MVP и не требует отдельной vector database.

Фрагмент модели embedding-блока представлен в листинге 3.11.

```python
class ParagraphEmbeddingBlock(Base):
    __tablename__ = "paragraph_embedding_blocks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"))
    block_index: Mapped[int] = mapped_column(Integer, nullable=False)
    start_paragraph_index: Mapped[int] = mapped_column(Integer, nullable=False)
    end_paragraph_index: Mapped[int] = mapped_column(Integer, nullable=False)
    block_text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[str | None] = mapped_column(Text, nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(100))
```

Листинг 3.11. Модель хранения embedding-блоков

Для контроля AI-операций используется таблица `ai_request_logs`. Она хранит отправленный текст, результат, модель, статус, ошибку, количество токенов и время выполнения.

```python
class AiRequestLog(Base):
    __tablename__ = "ai_request_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id"))
    operation: Mapped[str] = mapped_column(String(80), nullable=False)
    model: Mapped[str | None] = mapped_column(String(100))
    request_text: Mapped[str | None] = mapped_column(Text)
    response_text: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    total_tokens: Mapped[int | None] = mapped_column(Integer)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
```

Листинг 3.12. Модель журнала AI-запросов

## 3.6. Реализация REST API и серверной части системы

Серверная часть системы реализована с использованием FastAPI. Основная точка входа находится в `main.py`, где создаётся приложение, подключаются роутеры и статические файлы.

API разделено на логические группы:

- авторизация;
- документы;
- поиск;
- аналитические инструменты;
- административная панель.

Основные endpoints документов:

```text
POST   /documents/upload
POST   /documents/from-path
GET    /documents
GET    /documents/{document_id}
GET    /documents/{document_id}/file
DELETE /documents/{document_id}
```

Основные endpoints поиска:

```text
GET  /search
GET  /search/word
GET  /search/sentence
GET  /search/paragraph
GET  /search/phrase
POST /search/semantic
```

Endpoint семантического поиска представлен в листинге 3.13.

```python
@router.post("/search/semantic")
def api_search_semantic(
    payload: SemanticSearchRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> list[dict]:
    limit = min(50, max(1, int(payload.limit or 10)))
    document_id = payload.document_id if payload.document_id and payload.document_id > 0 else None
    return VectorSearchService(db).search(
        query=payload.query,
        document_id=document_id,
        limit=limit,
        user_id=current_user.id,
    )
```

Листинг 3.13. Endpoint семантического поиска

Запрос и ответ имеют JSON-формат:

```json
{
  "query": "таъсири маориф ба ҷомеа",
  "document_id": 1,
  "limit": 10
}
```

Ответ содержит найденные фрагменты, оценку релевантности и номер абзаца:

```json
[
  {
    "document_id": 1,
    "paragraph_index": 12,
    "paragraph_end_index": 13,
    "text": "...",
    "score": 0.8421,
    "semantic_score": 0.7712,
    "keyword_score": 0.6000
  }
]
```

Поставить экран Swagger-документации FastAPI.

Рис. 3.8. REST API системы в Swagger UI

Для защиты endpoints используется bearer token. Пользователь получает токен после авторизации, а затем передаёт его в заголовке запроса.

## 3.7. Реализация пользовательского интерфейса системы

Frontend системы реализован с использованием HTML, CSS и JavaScript. Интерфейс включает главную страницу, страницы входа и регистрации, а также административную панель.

На главной странице пользователь видит список документов, форму поиска, вкладки аналитических инструментов и область просмотра выбранного документа.

Поставить главный экран системы.

Рис. 3.9. Интерфейс работы с документами

Форма загрузки документа позволяет указать метаданные и выбрать файл. После загрузки документ появляется в общем списке, а AI-обработка выполняется в фоне.

Поставить экран формы загрузки документа.

Рис. 3.10. Загрузка нового документа

Для поиска реализованы режимы:

- фраза;
- слово;
- предложение;
- абзац;
- семантический поиск.

Поставить экран выбора семантического поиска.

Рис. 3.11. Выбор режима семантического поиска

Дополнительно доступны инструменты Concordance, Wordlist и N-grams.

Поставить экран Concordance.

Рис. 3.12. Concordance-анализ

Поставить экран Wordlist.

Рис. 3.13. Частотный список слов

Поставить экран N-grams.

Рис. 3.14. Анализ n-грамм

Административная панель содержит управление пользователями, список файлов и AI-логи.

Поставить экран административной панели.

Рис. 3.15. Административная панель

В AI-логах фиксируются операции:

- `embedding_chunk`;
- `embedding_paragraph_block`;
- `semantic_search`;
- `semantic_search_rerank`;
- `summary_generation`.

Поставить экран AI-логов.

Рис. 3.16. Журнал AI-запросов

## 3.8. Тестирование и оценка эффективности системы

Тестирование MVP-системы Meros.AI проводилось по основным функциональным сценариям:

- регистрация и авторизация пользователя;
- загрузка PDF, DOC и DOCX-документов;
- извлечение текста;
- структурирование текста;
- обычный поиск;
- семантический поиск;
- генерация AI-аннотации;
- запись AI-логов;
- работа административной панели.

При тестировании загрузки документа проверялось, что файл сохраняется в системе, текст извлекается корректно, а в базе данных создаются записи документа, абзацев, предложений и слов.

При тестировании AI-обработки проверялось изменение статуса:

```text
pending -> processing -> ready
```

Если API-ключ не задан или возникает ошибка OpenAI API, статус изменяется на:

```text
error
```

Семантический поиск проверялся на запросах, которые отличались от текста документа дословно, но были близки по смыслу. Система возвращала релевантные абзацы и показывала итоговый score.

Поставить экран результатов семантического поиска.

Рис. 3.17. Проверка работы семантического поиска

AI-аннотация проверялась после завершения фоновой обработки. Система формировала краткое описание документа на таджикском языке и сохраняла его в поле `ai_summary`.

Поставить экран AI-аннотации.

Рис. 3.18. Проверка генерации AI-аннотации

Работа AI-логов проверялась через административную панель. В журнале фиксировались успешные и ошибочные операции, модель, количество токенов и время выполнения.

Поставить экран AI-логов после обработки документа.

Рис. 3.19. Проверка журналирования AI-запросов

По результатам тестирования установлено, что система корректно выполняет загрузку и обработку документов, обеспечивает обычный и семантический поиск, формирует AI-аннотацию и сохраняет технические логи AI-операций. Реализованная архитектура позволяет использовать Meros.AI как основу для интеллектуальной электронной библиотеки и системы анализа текстовых документов.

