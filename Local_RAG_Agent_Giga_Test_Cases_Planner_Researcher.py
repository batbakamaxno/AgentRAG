from gigachat import GigaChat
import os
from dotenv import load_dotenv
import logging
from datetime import datetime
from langchain_community.document_loaders import TextLoader
from PyPDF2 import PdfReader
from typing import Dict, List, Optional

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
    GIGACHAT_CREDENTIALS = ""
    logger.warning("GIGACHAT_CREDENTIALS не установлен. Используется значение по умолчанию.")
else:
    logger.info("GIGACHAT_CREDENTIALS успешно загружен из .env")
os.environ["GIGACHAT_CREDENTIALS"] = GIGACHAT_CREDENTIALS

# Промпты для агентов
PLANNER_PROMPT = """### Роль: Планировщик тест-кейсов
Ты - опытный планировщик тестирования, который анализирует документацию и создает структурированный план тестирования.

### Задача
1. Проанализируй предоставленную документацию
2. Определи ключевые области для тестирования
3. Создай структурированный план тестирования
4. Определи приоритеты тестирования
5. Выдели основные риски

### Формат ответа
1. Анализ документации:
   - Основные компоненты системы
   - Ключевые функции
   - Критические пути

2. План тестирования:
   - Категории тестов
   - Приоритеты
   - Зависимости

3. Рекомендации для исследователя:
   - Ключевые области для детального анализа
   - Специфические аспекты для тестирования
   - Потенциальные сложности
"""

RESEARCHER_PROMPT = """### Роль: Исследователь тест-кейсов
Ты - опытный тестировщик, который создает детальные тест-кейсы на основе плана тестирования.

### Задача
1. Изучи план тестирования от планировщика
2. Создай детальные тест-кейсы для каждой категории
3. Убедись в полноте покрытия
4. Проверь соответствие требованиям

### Формат тест-кейса
1. Название теста
2. Идентификатор (TC001, TC002 и т.д.)
3. Тип тестирования (Frontend/Backend/API)
4. Предусловия
5. Шаги
6. Ожидаемый результат
7. Тестовые данные

### Требования к тест-кейсам
- Покрытие позитивных и негативных сценариев
- Учет граничных случаев
- Проверка обработки ошибок
- Тестирование безопасности
- Проверка производительности
"""

class TestCaseGenerator:
    def __init__(self):
        try:
            self.gigachat = GigaChat(
                credentials=os.getenv("GIGACHAT_CREDENTIALS"),
                verify_ssl_certs=False
            )
            logger.info("GigaChat успешно инициализирован")
        except Exception as e:
            logger.error(f"Ошибка при инициализации GigaChat: {e}")
            raise

    def load_file(self, file_path: str) -> str:
        """Загружает содержимое файла в зависимости от его типа."""
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

    def planner_phase(self, doc_content: str) -> str:
        """Фаза планирования: анализ документации и создание плана тестирования."""
        try:
            full_prompt = f"{PLANNER_PROMPT}\n\n### Документация:\n{doc_content}"
            response = self.gigachat.chat(full_prompt)
            
            if response and hasattr(response, 'choices') and response.choices:
                return response.choices[0].message.content
            else:
                logger.error("Не удалось получить ответ от планировщика")
                return ""
                
        except Exception as e:
            logger.error(f"Ошибка в фазе планирования: {e}")
            return ""

    def researcher_phase(self, doc_content: str, plan: str) -> str:
        """Фаза исследования: создание тест-кейсов на основе плана."""
        try:
            full_prompt = f"{RESEARCHER_PROMPT}\n\n### Документация:\n{doc_content}\n\n### План тестирования:\n{plan}"
            response = self.gigachat.chat(full_prompt)
            
            if response and hasattr(response, 'choices') and response.choices:
                return response.choices[0].message.content
            else:
                logger.error("Не удалось получить ответ от исследователя")
                return ""
                
        except Exception as e:
            logger.error(f"Ошибка в фазе исследования: {e}")
            return ""

    def save_test_cases(self, doc_name: str, plan: str, test_cases: str):
        """Сохраняет план тестирования и тест-кейсы в структурированном формате."""
        try:
            test_cases_dir = os.path.abspath('ft_test_cases')
            if not os.path.exists(test_cases_dir):
                os.makedirs(test_cases_dir)
                logger.info(f'Создана директория {test_cases_dir}/')
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            formatted_content = f"""
# Тест-кейсы на основе документации
## Исходный документ
{doc_name}

## План тестирования
{plan}

## Сгенерированные тест-кейсы
{test_cases}

### Дополнительная информация
- Дата генерации: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
"""

            filename = os.path.join(test_cases_dir, f"test_cases_{os.path.splitext(doc_name)[0]}_{timestamp}.md")
            
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(formatted_content)
            logger.info(f'Тест-кейсы успешно сохранены в файл: {filename}')
            
        except Exception as e:
            logger.error(f'Ошибка при сохранении тест-кейсов: {str(e)}')
            raise

    def generate_test_cases(self, doc_path: str):
        """Основной метод генерации тест-кейсов с использованием двухфазного подхода."""
        try:
            doc_name = os.path.basename(doc_path)
            doc_content = self.load_file(doc_path)
            
            # Фаза 1: Планирование
            logger.info("Начало фазы планирования")
            plan = self.planner_phase(doc_content)
            if not plan:
                logger.error("Не удалось создать план тестирования")
                return
            
            # Фаза 2: Исследование
            logger.info("Начало фазы исследования")
            test_cases = self.researcher_phase(doc_content, plan)
            if not test_cases:
                logger.error("Не удалось создать тест-кейсы")
                return
            
            # Сохранение результатов
            self.save_test_cases(doc_name, plan, test_cases)
            
        except Exception as e:
            logger.error(f"Ошибка при генерации тест-кейсов: {e}")
            logger.exception("Подробности ошибки:")

def main():
    try:
        # Путь к директории с документацией
        docs_dir = "doc"
        
        if not os.path.exists(docs_dir):
            logger.error(f"Директория не найдена: {docs_dir}")
            raise FileNotFoundError(f"Директория не найдена: {docs_dir}")
        
        # Получаем список всех поддерживаемых файлов
        doc_files = [f for f in os.listdir(docs_dir) if f.endswith(('.txt', '.pdf'))]
        
        if not doc_files:
            logger.warning(f"В директории {docs_dir} не найдено поддерживаемых файлов (.txt или .pdf)")
            return
            
        logger.info(f"Найдено {len(doc_files)} файлов документации")
        
        # Создаем генератор тест-кейсов
        generator = TestCaseGenerator()
        
        # Обрабатываем каждый файл
        for doc_file in doc_files:
            full_path = os.path.join(docs_dir, doc_file)
            logger.info(f"Обрабатываю файл: {full_path}")
            
            try:
                generator.generate_test_cases(full_path)
            except Exception as e:
                logger.error(f"Ошибка при обработке файла {doc_file}: {e}")
                continue

    except Exception as e:
        logger.error(f"Ошибка при создании тест-кейсов: {e}")
        logger.exception("Подробности ошибки:")

if __name__ == "__main__":
    main() 