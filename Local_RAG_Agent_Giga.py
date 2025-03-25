from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.schema import Document
import logging
from langchain_community.document_loaders import TextLoader, PyPDFLoader
from langchain_community.vectorstores import FAISS
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END
from typing_extensions import TypedDict
from typing import List, Annotated
import operator
import json
from langchain_community.tools.tavily_search import TavilySearchResults
from gigachat import GigaChat
import os
from dotenv import load_dotenv
from langchain_community.embeddings import HuggingFaceEmbeddings
import sys
import re
from datetime import datetime

# Настройка логирования
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)

# Загрузка переменных окружения
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
if os.path.exists(env_path):
    load_dotenv(env_path)
    logger.info("Файл .env успешно загружен")
else:
    logger.warning(f"Файл .env не найден по пути: {env_path}")

# Проверка и установка API ключа GigaChat
GIGACHAT_CREDENTIALS = os.getenv("GIGACHAT_CREDENTIALS")
if not GIGACHAT_CREDENTIALS:
    GIGACHAT_CREDENTIALS = "" # Используем тестовый ключ
    logger.warning("GIGACHAT_CREDENTIALS не установлен. Используется значение по умолчанию.")
else:
    logger.info("GIGACHAT_CREDENTIALS успешно загружен из .env")
os.environ["GIGACHAT_CREDENTIALS"] = GIGACHAT_CREDENTIALS

# Проверка и установка API ключа Tavily
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
if not TAVILY_API_KEY:
    TAVILY_API_KEY = "" # Используем тестовый ключ
    logger.warning("TAVILY_API_KEY не установлен. Используется значение по умолчанию.")
else:
    logger.info("TAVILY_API_KEY успешно загружен из .env")
os.environ["TAVILY_API_KEY"] = TAVILY_API_KEY

# Инициализация необходимых компонентов
try:
    web_search_tool = TavilySearchResults(k=3)
    logger.info("Tavily Search успешно инициализирован")
except Exception as e:
    logger.error(f"Ошибка при инициализации Tavily Search: {e}")
    web_search_tool = None

# Инструкции для маршрутизации запросов
router_instructions = """You are an expert at routing a user question to a vectorstore or web search.
    The vectorstore contains documents related to test automation.
    Use the vectorstore for questions on these topics. For all else, and especially for current events, use web-search.
    Return JSON with single key, datasource, that is 'websearch' or 'vectorstore' depending on the question."""

# RAG prompt для генерации автотестов
rag_prompt = """### Роль для модели
Ты – разработчик автоматизированных тестов на языке Java. Ты будешь преобразовывать ручной тест-кейс в автоматический тест, используя JUnit.

### Задача
Создать автоматизированный тест на языке Java из ручного тест-кейса. Для этого потребуется проанализировать каждый шаг ручного теста и реализовать соответствующие методы проверки.

#### Инструкции
1. **Анализируйте ручной тест-кейс**. Разбейте его на конкретные шаги и определите, какие условия нужно проверить.
2. **Определитесь с методами тестирования**. Используйте аннотацию `@Test` для каждого метода проверки.
3. **Проверьте корректность работы системы**. В каждом тестовом методе используйте утверждения (`assertEquals`, `assertTrue`, etc.) для подтверждения правильности поведения программы.
4. **Обрабатывайте потенциальные ошибки**. Добавьте аннотацию `@BeforeEach` или `@AfterEach` для подготовки окружения перед каждым тестом и очистки после него.

#### Пример преобразования
Допустим, у нас есть следующий ручной тест-кейс:
```
Тестирование регистрации нового пользователя:
1. Открыть страницу регистрации.
2. Заполнить поля имени и email.
3. Нажать кнопку 'Зарегистрироваться'.
4. Проверить успешность регистрации.
```

Переводим в автоматизированный тест:
```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

public class RegistrationTest {
    private UserRegistrationPage registrationPage;
    
    @BeforeEach
    public void setUp() {
        // Инициализация страницы регистрации
        this.registrationPage = new UserRegistrationPage();
    }

    @Test
    public void testSuccessfulRegistration() {
        String name = "John Doe";
        String email = "john.doe@example.com";
        
        // Шаги заполнения формы
        registrationPage.fillNameField(name);
        registrationPage.fillEmailField(email);
        registrationPage.clickRegisterButton();
        
        // Проверяем успех операции
        assertEquals("Регистрация прошла успешно!", registrationPage.getSuccessMessage());
    }
}
```

#### Формат ответа
Ваш ответ должен содержать класс Java с методами, реализующими тесты, основанными на анализе ручного тест-кейса.
"""

# Шаблоны инструкций для проверки документов и генерации ответов
doc_grader_prompt = """Here is the retrieved document: \n\n {document} \n\n Here is the user question: \n\n {question}. 
    This carefully and objectively assess whether the document contains at least some information that is relevant to the question.
    Return JSON with single key, binary_score, that is 'yes' or 'no' score to indicate whether the document contains at least some information that is relevant to the question."""

# Промпт для проверки фактической точности
fact_checking_prompt = """Ты - эксперт по проверке фактической точности. Проанализируй сгенерированный ответ и исходные документы.

Исходные документы:
{context}

Сгенерированный ответ:
{generated_response}

Оцени:
1. Соответствие фактов в ответе исходным документам
2. Наличие утверждений, которых нет в исходных документах
3. Точность технических деталей

Верни JSON в формате:
{
    "factual_accuracy": float, // от 0 до 1
    "hallucinations": [string], // список найденных галлюцинаций
    "missing_facts": [string], // важные факты из документов, пропущенные в ответе
    "technical_accuracy": float // от 0 до 1
}"""

# Промпт для сравнения ответа с документами
response_comparison_prompt = """Проанализируй соответствие сгенерированного ответа исходным документам.

Исходные документы:
{context}

Сгенерированный ответ:
{generated_response}

Вопрос пользователя:
{question}

Оцени:
1. Полноту ответа на вопрос
2. Использование информации из документов
3. Логическую связность

Верни JSON в формате:
{
    "completeness": float, // от 0 до 1
    "source_usage": float, // от 0 до 1
    "coherence": float, // от 0 до 1
    "needs_improvement": boolean,
    "improvement_areas": [string]
}"""

# Промпт для определения галлюцинаций
hallucination_check_prompt = """Проверь сгенерированный ответ на наличие галлюцинаций и необоснованных утверждений.

Исходные документы:
{context}

Сгенерированный ответ:
{generated_response}

Проверь:
1. Каждое фактическое утверждение
2. Каждую техническую деталь
3. Каждую ссылку на источники

Верни JSON в формате:
{
    "has_hallucinations": boolean,
    "hallucination_details": [
        {
            "statement": string,
            "type": "fact|technical|reference",
            "confidence": float
        }
    ],
    "safe_to_use": boolean
}"""

doc_grader_instructions = """You are a grader assessing relevance of a retrieved document to a user question.
    If the document contains keyword(s) or semantic meaning related to the question, grade it as relevant."""

# Определение структуры состояния графа
class GraphState(TypedDict):
    question: str
    generation: str
    web_search: str
    max_retries: int
    answers: int
    loop_step: Annotated[int, operator.add]
    documents: List[str]

# Настройка GigaChat
try:
    gigachat = GigaChat(
        credentials=os.getenv("GIGACHAT_CREDENTIALS"),
        verify_ssl_certs=False
    )
    logger.info("GigaChat успешно инициализирован")
except Exception as e:
    logger.error(f"Ошибка при инициализации GigaChat: {e}")
    raise Exception("Не удалось инициализировать GigaChat")

# Функции для узлов графа
def retrieve(state):
    logger.debug("---RETRIEVE---")
    question = state["question"]
    documents = state.get("documents", [])
    
    if retriever is None:
        logger.warning("Векторное хранилище недоступно")
        return {"documents": documents}
    
    try:
        # Получаем документы из векторного хранилища
        retrieved_docs = retriever.invoke(question)
        documents.extend(retrieved_docs)
        logger.info(f"Найдено {len(retrieved_docs)} релевантных документов")
    except Exception as e:
        logger.error(f"Ошибка при поиске в векторном хранилище: {e}")
    
    return {"documents": documents}

def generate(state):
    logger.debug("---GENERATE---")
    question = state["question"]
    documents = state["documents"]
    loop_step = state.get("loop_step", 0)
    
    # Подготовка контекста из документов
    context = "\n".join([doc.page_content if hasattr(doc, 'page_content') else str(doc) for doc in documents])
    
    # Формируем промпт с контекстом
    full_prompt = f"""
    {rag_prompt}
    
    ### Контекст из документов:
    {context}
    
    ### Вопрос пользователя:
    {question}
    
    ### Важные требования:
    1. Ответ должен содержать полный Java-код теста
    2. Код должен быть оформлен в блоке ```java
    3. Должны быть включены все необходимые импорты
    4. Тест должен соответствовать описанию из тест-кейса
    5. Должны быть реализованы все шаги теста
    """
    
    try:
        logger.info("Отправка запроса к GigaChat")
        messages = [
            {"role": "system", "content": "Ты - эксперт по автоматизации тестирования. Твоя задача - создать рабочий Java-тест на основе тест-кейса. Используй Rest Assured для API тестирования."},
            {"role": "user", "content": full_prompt}
        ]
        
        generation = gigachat.chat(messages)
        
        response = generation.content
        logger.info(f"Получен ответ от GigaChat длиной {len(response)} символов")
        
        # Проверяем наличие Java-кода в ответе
        if '```java' not in response:
            logger.warning("В ответе отсутствует блок с Java-кодом")
            return {"generation": "", "loop_step": loop_step + 1}
            
        # Проверяем наличие основных компонентов теста
        required_elements = [
            "import org.junit.jupiter.api",
            "public class",
            "@Test",
            "given()",
            "when()",
            "then()"
        ]
        
        missing_elements = [elem for elem in required_elements if elem not in response]
        if missing_elements:
            logger.warning(f"В ответе отсутствуют важные элементы: {missing_elements}")
            return {"generation": "", "loop_step": loop_step + 1}
            
        logger.info("Ответ успешно сгенерирован и прошел базовую валидацию")
        return {"generation": response, "loop_step": loop_step + 1}
        
    except Exception as e:
        logger.error(f"Ошибка при генерации ответа: {e}")
        logger.exception("Подробности ошибки:")
        return {"generation": "", "loop_step": loop_step + 1}

def grade_documents(state):
    logger.debug("---GRADE DOCUMENTS---")
    question = state["question"]
    documents = state["documents"]
    
    if not documents:
        logger.warning("Нет документов для оценки")
        return {"documents": documents, "web_search": "Yes"}
    
    # Оцениваем каждый документ
    relevant_docs = []
    for doc in documents:
        content = doc.page_content if hasattr(doc, 'page_content') else str(doc)
        
        # Формируем промпт для оценки
        grading_prompt = f"""
        {doc_grader_instructions}
        
        Document: {content}
        Question: {question}
        
        Is this document relevant? Return only 'yes' or 'no'.
        """
        
        try:
            result = gigachat.chat([HumanMessage(content=grading_prompt)])
            if isinstance(result.content, str) and 'yes' in result.content.lower():
                relevant_docs.append(doc)
        except Exception as e:
            logger.error(f"Ошибка при оценке документа: {e}")
    
    # Если нет релевантных документов, предлагаем использовать веб-поиск
    if not relevant_docs:
        logger.info("Не найдено релевантных документов, переключаемся на веб-поиск")
        return {"documents": documents, "web_search": "Yes"}
    
    logger.info(f"Найдено {len(relevant_docs)} релевантных документов")
    return {"documents": relevant_docs, "web_search": "No"}

def web_search(state):
    logger.debug("---WEB SEARCH---")
    question = state["question"]
    documents = state.get("documents", [])
    
    if web_search_tool is None:
        logger.warning("Веб-поиск недоступен, пропускаем этап поиска")
        return {"documents": documents}
    
    try:
        docs = web_search_tool.invoke({"query": question})
        web_results = "\n".join([d["content"] for d in docs])
        web_results = Document(page_content=web_results)
        documents.append(web_results)
        logger.info("Веб-поиск успешно выполнен")
    except Exception as e:
        logger.error(f"Ошибка при выполнении веб-поиска: {e}")
    
    return {"documents": documents}

def route_question(state):
    logger.debug("---ROUTE QUESTION---")
    if state.get("documents"):
        return "vectorstore"
    return "websearch"

def decide_to_generate(state):
    logger.debug("---DECIDE TO GENERATE---")
    return "generate"

def grade_generation(state):
    logger.debug("---GRADE GENERATION---")
    
    question = state["question"]
    generation = state.get("generation", "")
    documents = state.get("documents", [])
    
    if not generation:
        logger.warning("Получен пустой ответ")
        return "not useful"
    
    # Подготовка контекста из документов
    context = "\n".join([doc.page_content if hasattr(doc, 'page_content') else str(doc) for doc in documents])
    
    # Проверка качества ответа
    is_valid, validation_results = validate_response(context, generation, question)
    
    if not is_valid:
        logger.warning("Ответ не прошел валидацию")
        
        # Проверяем количество попыток
        if state.get("loop_step", 0) >= state.get("max_retries", 3):
            logger.warning("Достигнуто максимальное количество попыток")
            # Если есть хоть какой-то код, считаем его полезным
            if '```java' in generation:
                logger.info("Найден Java-код, считаем ответ полезным")
                return "useful"
            return "max retries"
            
        # Если есть галлюцинации или низкое качество - пробуем веб-поиск
        if validation_results["hallucination_check"].get("has_hallucinations", True):
            logger.info("Обнаружены галлюцинации, переключаемся на веб-поиск")
            return "not useful"
            
        # Если ответ неполный или требует улучшения
        if validation_results["source_comparison"].get("needs_improvement", True):
            logger.info("Ответ требует улучшения, пробуем еще раз")
            return "not useful"
    
    logger.info("Ответ прошел валидацию")
    return "useful"

# Создание и настройка графа
workflow = StateGraph(GraphState)

# Добавление узлов
workflow.add_node("websearch", web_search)
workflow.add_node("retrieve", retrieve)
workflow.add_node("grade_documents", grade_documents)
workflow.add_node("generate", generate)

# Настройка связей
workflow.set_conditional_entry_point(
    route_question,
    {
        "websearch": "websearch",
        "vectorstore": "retrieve",
    },
)
workflow.add_edge("websearch", "generate")
workflow.add_edge("retrieve", "grade_documents")
workflow.add_conditional_edges(
    "grade_documents",
    decide_to_generate,
    {
        "websearch": "websearch",
        "generate": "generate",
    },
)
workflow.add_conditional_edges(
    "generate",
    grade_generation,
    {
        "useful": END,
        "not useful": "websearch",
        "max retries": END,
    },
)

# Компиляция графа
graph = workflow.compile()

def process_documents(documents):
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1024, chunk_overlap=0)
    source_chunks = text_splitter.split_documents(documents)
    logger.debug(f"Количество созданных чанков: {len(source_chunks)}")
    
    if len(source_chunks) > 0:
        # Логируем информацию о первом чанке для примера
        logger.debug(f"Пример метаданных первого чанка: {source_chunks[0].metadata}")
        logger.debug(f"Пример содержимого первого чанка: {source_chunks[0].page_content}")
    else:
        logger.warning("Не удалось создать чанки из документов. Проверьте наличие PDF файлов в директории pdf/")

    return source_chunks 

def get_vector_store():
    """
    Функция для получения или создания векторной Базы-Знаний.
    Если база уже существует, она загружается из файла,
    иначе происходит чтение PDF-документов и создание новой базы.
    """
    logger.debug('Инициализация векторного хранилища')
    
    # Создание векторных представлений (Embeddings)
    embeddings = HuggingFaceEmbeddings(
        model_name="bert-base-uncased"
    )

    db_file_name = 'db/db_01'
    file_path = f"{db_file_name}/index.faiss"
    
    # Проверка наличия файла с векторной Базой-Знаний
    if os.path.exists(file_path):
        logger.info('Загружаем существующую векторную Базу-знаний')
        return FAISS.load_local(db_file_name, embeddings, allow_dangerous_deserialization=True)

    logger.info('Создаем новую векторную Базу-Знаний')
    
    # Создание директории pdf если её нет
    if not os.path.exists('pdf'):
        os.makedirs('pdf')
        logger.info('Создана директория pdf/')
    
    # Создание директории db если её нет
    if not os.path.exists('db'):
        os.makedirs('db')
        logger.info('Создана директория db/')
    
    documents = []
    pdf_dir = 'pdf'
    
    # Чтение всех PDF-файлов
    for root, dirs, files in os.walk(pdf_dir):
        for file in files:
            if file.endswith(".pdf"):
                file_path = os.path.join(root, file)
                logger.info(f'Обработка файла: {file_path}')
                try:
                    loader = PyPDFLoader(file_path)
                    documents.extend(loader.load())
                except Exception as e:
                    logger.error(f'Ошибка при обработке файла {file_path}: {e}')

    if not documents:
        logger.warning('Не найдено PDF файлов для обработки')
        return None

    # Разделение документов на чанки
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1024, chunk_overlap=0)
    chunks = text_splitter.split_documents(documents)
    logger.info(f'Создано {len(chunks)} чанков из документов')

    # Создание векторной Базы-Знаний
    vectorstore = FAISS.from_documents(chunks, embeddings)
    
    # Сохранение базы
    vectorstore.save_local(db_file_name)
    logger.info(f'Векторная База-Знаний сохранена в {db_file_name}')
    
    return vectorstore

# Инициализация векторного хранилища
try:
    vectorstore = get_vector_store()
    if vectorstore:
        logger.info("Векторное хранилище успешно инициализировано")
        retriever = vectorstore.as_retriever(k=3)
    else:
        logger.warning("Векторное хранилище не создано - нет PDF файлов")
        retriever = None
except Exception as e:
    logger.error(f"Ошибка при инициализации векторного хранилища: {e}")
    retriever = None

def save_response(question, response, response_type="general"):
    """
    Сохраняет ответ в структурированном формате в отдельный файл.
    
    Args:
        question (str): Вопрос пользователя
        response (str): Ответ системы
        response_type (str): Тип ответа (например, 'general', 'test_case', etc.)
    """
    try:
        # Создаем директории если их нет
        responses_dir = os.path.abspath('responses')
        java_dir = os.path.join(responses_dir, 'java')
        
        logger.info(f"Создание директорий: {responses_dir}, {java_dir}")
        for dir_path in [responses_dir, java_dir]:
            if not os.path.exists(dir_path):
                os.makedirs(dir_path)
                logger.info(f'Создана директория {dir_path}/')
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        logger.info(f"Создание файлов с временной меткой: {timestamp}")
        
        # Форматируем ответ в структурированном виде
        formatted_response = f"""
# Результат генерации автотеста
## Исходный запрос
{question}

## Сгенерированное решение
### Описание
{response.split('```')[0] if '```' in response else response}

### Код решения
```java
{re.search(r'```java\n(.*?)\n```', str(response), re.DOTALL).group(1) if '```java' in response else ''}
```

### Практические рекомендации
1. Перед запуском теста убедитесь, что все необходимые зависимости установлены
2. Проверьте наличие всех импортированных классов
3. При необходимости настройте тестовое окружение
4. Запустите тест с помощью JUnit runner

### Дополнительная информация
- Дата генерации: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
- Тип ответа: {response_type}
"""

        # Сохраняем форматированный ответ
        txt_filename = os.path.join(responses_dir, f"response_{response_type}_{timestamp}.md")
        logger.info(f"Сохранение ответа в файл: {txt_filename}")
        
        with open(txt_filename, 'w', encoding='utf-8') as f:
            f.write(formatted_response)
        logger.info(f'Ответ успешно сохранен в файл: {txt_filename}')
        
        # Если есть Java-код, сохраняем его отдельно
        if '```java' in response:
            java_code_match = re.search(r'```java\n(.*?)\n```', str(response), re.DOTALL)
            if java_code_match:
                java_code = java_code_match.group(1)
                class_name_match = re.search(r'public class (\w+)', java_code)
                class_name = class_name_match.group(1) if class_name_match else "Test"
                
                java_filename = os.path.join(java_dir, f"{class_name}_{timestamp}.java")
                logger.info(f"Сохранение Java-кода в файл: {java_filename}")
                
                with open(java_filename, 'w', encoding='utf-8') as f:
                    f.write(java_code)
                logger.info(f'Java-код успешно сохранен в файл: {java_filename}')
            else:
                logger.warning("Не удалось извлечь Java-код из ответа")
    except Exception as e:
        logger.error(f'Ошибка при сохранении ответа: {str(e)}')
        logger.exception("Подробности ошибки:")
        raise

# Функции для проверки качества ответов
def check_factual_accuracy(context, generated_response):
    """
    Проверяет фактическую точность сгенерированного ответа.
    
    Args:
        context (str): Исходные документы
        generated_response (str): Сгенерированный ответ
    
    Returns:
        dict: Результаты проверки фактической точности
    """
    try:
        prompt = fact_checking_prompt.format(
            context=context,
            generated_response=generated_response
        )
        
        result = gigachat.chat([HumanMessage(content=prompt)])
        
        if isinstance(result.content, str):
            result = json.loads(result.content)
            
        logger.info(f"Результаты проверки фактической точности: {result}")
        return result
    except Exception as e:
        logger.error(f"Ошибка при проверке фактической точности: {e}")
        return {
            "factual_accuracy": 0.0,
            "hallucinations": ["Ошибка при проверке"],
            "missing_facts": [],
            "technical_accuracy": 0.0
        }

def compare_with_sources(context, generated_response, question):
    """
    Сравнивает сгенерированный ответ с исходными документами.
    
    Args:
        context (str): Исходные документы
        generated_response (str): Сгенерированный ответ
        question (str): Вопрос пользователя
    
    Returns:
        dict: Результаты сравнения
    """
    try:
        prompt = response_comparison_prompt.format(
            context=context,
            generated_response=generated_response,
            question=question
        )
        
        result = gigachat.chat([HumanMessage(content=prompt)])
        
        if isinstance(result.content, str):
            result = json.loads(result.content)
            
        logger.info(f"Результаты сравнения с источниками: {result}")
        return result
    except Exception as e:
        logger.error(f"Ошибка при сравнении с источниками: {e}")
        return {
            "completeness": 0.0,
            "source_usage": 0.0,
            "coherence": 0.0,
            "needs_improvement": True,
            "improvement_areas": ["Ошибка при сравнении"]
        }

def check_for_hallucinations(context, generated_response):
    """
    Проверяет ответ на наличие галлюцинаций.
    
    Args:
        context (str): Исходные документы
        generated_response (str): Сгенерированный ответ
    
    Returns:
        dict: Результаты проверки на галлюцинации
    """
    try:
        prompt = hallucination_check_prompt.format(
            context=context,
            generated_response=generated_response
        )
        
        result = gigachat.chat([HumanMessage(content=prompt)])
        
        if isinstance(result.content, str):
            result = json.loads(result.content)
            
        logger.info(f"Результаты проверки на галлюцинации: {result}")
        return result
    except Exception as e:
        logger.error(f"Ошибка при проверке на галлюцинации: {e}")
        return {
            "has_hallucinations": True,
            "hallucination_details": [{"statement": "Ошибка при проверке", "type": "error", "confidence": 0.0}],
            "safe_to_use": False
        }

def validate_response(context, generated_response, question):
    """
    Комплексная проверка качества сгенерированного ответа.
    
    Args:
        context (str): Исходные документы
        generated_response (str): Сгенерированный ответ
        question (str): Вопрос пользователя
    
    Returns:
        tuple: (bool, dict) - флаг валидности и детальные результаты проверки
    """
    # Проверка фактической точности
    fact_check = check_factual_accuracy(context, generated_response)
    
    # Сравнение с источниками
    source_comparison = compare_with_sources(context, generated_response, question)
    
    # Проверка на галлюцинации
    hallucination_check = check_for_hallucinations(context, generated_response)
    
    # Агрегация результатов
    validation_results = {
        "factual_check": fact_check,
        "source_comparison": source_comparison,
        "hallucination_check": hallucination_check,
        "overall_quality": (
            fact_check.get("factual_accuracy", 0) * 0.4 +
            source_comparison.get("completeness", 0) * 0.3 +
            source_comparison.get("coherence", 0) * 0.3
        )
    }
    
    # Определение валидности ответа
    is_valid = (
        validation_results["overall_quality"] >= 0.7 and
        not hallucination_check.get("has_hallucinations", True) and
        not source_comparison.get("needs_improvement", True)
    )
    
    logger.info(f"Результаты валидации ответа: valid={is_valid}, quality={validation_results['overall_quality']}")
    
    return is_valid, validation_results

if __name__ == "__main__":
    # Пример использования системы для создания автотеста из ручного тест-кейса
    
    # Функция для загрузки файла
    def load_file(file_path):
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Файл не найден: {file_path}")
            
        if file_path.endswith('.pdf'):
            loader = PyPDFLoader(file_path)
        elif file_path.endswith('.txt'):
            loader = TextLoader(file_path, encoding='utf-8')
        else:
            raise ValueError("Поддерживаются только PDF и TXT файлы")
        return loader.load()

    # Пример использования для создания автотеста
    try:
        # Путь к директории с тест-кейсами
        test_cases_dir = "test_cases"
        
        # Проверяем существование директории
        if not os.path.exists(test_cases_dir):
            logger.error(f"Директория не найдена: {test_cases_dir}")
            logger.error(f"Текущая директория: {os.getcwd()}")
            raise FileNotFoundError(f"Директория не найдена: {test_cases_dir}")
        
        # Получаем список всех файлов в директории
        test_case_files = [f for f in os.listdir(test_cases_dir) if f.endswith('.txt')]
        
        if not test_case_files:
            logger.warning(f"В директории {test_cases_dir} не найдено текстовых файлов")
            sys.exit(1)
            
        logger.info(f"Найдено {len(test_case_files)} файлов тест-кейсов")
        
        # Обрабатываем каждый файл
        for test_case_file in test_case_files:
            full_path = os.path.join(test_cases_dir, test_case_file)
            logger.info(f"Обрабатываю файл: {full_path}")
            
            try:
                test_case_documents = load_file(full_path)
                
                inputs = {
                    "question": f"Создай автоматизированный тест на Java на основе ручного тест-кейса из файла {test_case_file}",
                    "max_retries": 3,
                    "documents": test_case_documents,
                    "loop_step": 0,  # Добавляем начальное значение для счетчика попыток
                    "answers": 0  # Добавляем счетчик ответов
                }
                print("\nЗадаю вопрос для создания автотеста:", inputs["question"])
                response = ""
                
                try:
                    for event in graph.stream(inputs, stream_mode="values"):
                        logger.debug(event)
                        if "generation" in event:
                            response = event["generation"]
                            # Если получили ответ с кодом, прерываем цикл
                            if '```java' in response:
                                logger.info("Получен ответ с Java-кодом, прерываем цикл")
                                break
                            
                            # Проверяем количество попыток
                            if event.get("loop_step", 0) >= inputs["max_retries"]:
                                logger.warning("Достигнуто максимальное количество попыток")
                                break
                                
                            # Проверяем количество ответов
                            if event.get("answers", 0) >= 5:
                                logger.warning("Достигнуто максимальное количество ответов")
                                break
                                
                except Exception as e:
                    logger.error(f"Ошибка при обработке графа: {e}")
                    if response:  # Если успели получить ответ до ошибки
                        save_response(inputs["question"], response, "test_case")
                    continue
                
                # Сохраняем ответ
                if response:
                    save_response(inputs["question"], response, "test_case")
                else:
                    logger.warning("Не удалось получить ответ с кодом")
                    
            except Exception as e:
                logger.error(f"Ошибка при создании автотеста: {e}")
                logger.exception("Подробности ошибки:")
                continue  # Продолжаем обработку следующего файла

    except Exception as e:
        logger.error(f"Ошибка при создании автотеста: {e}")
        logger.exception("Подробности ошибки:") 