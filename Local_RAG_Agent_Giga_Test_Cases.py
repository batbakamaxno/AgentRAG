from gigachat import GigaChat
import os
from dotenv import load_dotenv
import logging
import re
from datetime import datetime
from langchain_community.document_loaders import TextLoader
from PyPDF2 import PdfReader

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

# RAG prompt для генерации ручных тест-кейсов
rag_prompt = """### Роль
Ты создаёшь ручные тест-кейсы на основе технической документации продукта.

### Задача
На основании документации разработай набор тест-кейсов, используя различные техники тестирования и принципы тестирования ПО.

#### Шаги
1. Изучи документацию продукта, чтобы выявить функциональность и предполагаемые области риска.
2. Раздели тестирование на два типа:
   - Функциональное тестирование (проверяет соответствие требованиям);
   - Нефункциональное тестирование (производительность, безопасность, удобство использования и др.).
   
3. Примени следующие методы тестирования:
   - Эквивалентное разбиение;
   - Границы значений;
   - Тестирование состояний переходов;
   - Случайное тестирование;
   - Смок-тестирование;
   - Регрессионное тестирование.

4. При создании каждого тест-кейса учитывай следующую структуру:
   - Название теста;
   - Идентификатор;
   - Предусловия;
   - Шаги;
   - Ожидаемый результат.

5. Создавай тестовые данные, основываясь на реальных сценариях использования системы.

#### Пример тест-кейса:
*Название:* Проверка ввода некорректного email.
*Идентификатор:* TC001.
*Предусловие:* Пользователь находится на странице регистрации.
*Шаги:*
1. Ввести некорректный email (например, без символа @).
2. Нажать кнопку "Зарегистрироваться".
*Ожидаемый результат:* Появляется сообщение об ошибке с текстом "Некорректный email".

#### Примечание
Убедись, что каждый тест покрывает конкретный сценарий работы программы.

#### Критерии успеха
Тест-кейс считается успешным, если реальный результат совпадает с ожидаемым результатом после выполнения всех шагов.
"""

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

def save_test_cases(doc_name, response):
    """
    Сохраняет сгенерированные тест-кейсы в структурированном формате.
    
    Args:
        doc_name (str): Имя исходного документа
        response (str): Ответ системы с тест-кейсами
    """
    try:
        # Создаем директории если их нет
        test_cases_dir = os.path.abspath('ft_test_cases')
        logger.info(f"Создание директории: {test_cases_dir}")
        
        if not os.path.exists(test_cases_dir):
            os.makedirs(test_cases_dir)
            logger.info(f'Создана директория {test_cases_dir}/')
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        logger.info(f"Создание файла с временной меткой: {timestamp}")
        
        # Форматируем ответ в структурированном виде
        formatted_response = f"""
# Тест-кейсы на основе документации
## Исходный документ
{doc_name}

## Сгенерированные тест-кейсы
{response}

### Дополнительная информация
- Дата генерации: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
"""

        # Сохраняем форматированный ответ
        filename = os.path.join(test_cases_dir, f"test_cases_{os.path.splitext(doc_name)[0]}_{timestamp}.md")
        logger.info(f"Сохранение тест-кейсов в файл: {filename}")
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(formatted_response)
        logger.info(f'Тест-кейсы успешно сохранены в файл: {filename}')
        
    except Exception as e:
        logger.error(f'Ошибка при сохранении тест-кейсов: {str(e)}')
        logger.exception("Подробности ошибки:")
        raise

def generate_test_cases(doc_content, doc_name):
    """
    Генерирует ручные тест-кейсы на основе документации.
    
    Args:
        doc_content (str): Содержимое документа
        doc_name (str): Имя документа
    
    Returns:
        str: Сгенерированные тест-кейсы
    """
    try:
        # Формируем промпт с контекстом
        full_prompt = f"""
        {rag_prompt}
        
        ### Документация:
        {doc_content}
        
        ### Важные требования:
        1. Создай набор тест-кейсов на основе предоставленной документации
        2. Используй различные методы тестирования
        3. Каждый тест-кейс должен иметь четкую структуру
        4. Тест-кейсы должны покрывать как позитивные, так и негативные сценарии
        5. Учитывай все аспекты функционального и нефункционального тестирования
        """
        
        logger.info("Отправка запроса к GigaChat")
        
        # Отправляем запрос к GigaChat
        response = gigachat.chat(full_prompt)
        
        if response and hasattr(response, 'choices') and response.choices:
            response_text = response.choices[0].message.content
            logger.info(f"Получен ответ от GigaChat длиной {len(response_text)} символов")
            return response_text
        else:
            logger.error("Не удалось получить ответ от GigaChat")
            return ""
        
    except Exception as e:
        logger.error(f"Ошибка при генерации тест-кейсов: {e}")
        logger.exception("Подробности ошибки:")
        return ""

def load_file(file_path):
    """
    Загружает содержимое файла в зависимости от его типа.
    
    Args:
        file_path (str): Путь к файлу
        
    Returns:
        str: Содержимое файла
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Файл не найден: {file_path}")
        
    file_extension = os.path.splitext(file_path)[1].lower()
    
    if file_extension == '.txt':
        loader = TextLoader(file_path, encoding='utf-8')
        documents = loader.load()
        return "\n".join([doc.page_content for doc in documents])
    elif file_extension == '.pdf':
        reader = PdfReader(file_path)
        text = ""
        for page in reader.pages:
            text += page.extract_text() + "\n"
        return text
    else:
        raise ValueError(f"Неподдерживаемый формат файла: {file_extension}")

if __name__ == "__main__":
    try:
        # Путь к директории с документацией
        docs_dir = "doc"
        
        # Проверяем существование директории
        if not os.path.exists(docs_dir):
            logger.error(f"Директория не найдена: {docs_dir}")
            logger.error(f"Текущая директория: {os.getcwd()}")
            raise FileNotFoundError(f"Директория не найдена: {docs_dir}")
        
        # Получаем список всех поддерживаемых файлов в директории
        doc_files = [f for f in os.listdir(docs_dir) if f.endswith(('.txt', '.pdf'))]
        
        if not doc_files:
            logger.warning(f"В директории {docs_dir} не найдено поддерживаемых файлов (.txt или .pdf)")
            sys.exit(1)
            
        logger.info(f"Найдено {len(doc_files)} файлов документации")
        
        # Обрабатываем каждый файл
        for doc_file in doc_files:
            full_path = os.path.join(docs_dir, doc_file)
            logger.info(f"Обрабатываю файл: {full_path}")
            
            try:
                doc_content = load_file(full_path)
                
                response = generate_test_cases(doc_content, doc_file)
                
                if response:
                    save_test_cases(doc_file, response)
                else:
                    logger.warning("Не удалось получить ответ с тест-кейсами")
                    
            except Exception as e:
                logger.error(f"Ошибка при создании тест-кейсов: {e}")
                logger.exception("Подробности ошибки:")
                continue  # Продолжаем обработку следующего файла

    except Exception as e:
        logger.error(f"Ошибка при создании тест-кейсов: {e}")
        logger.exception("Подробности ошибки:") 