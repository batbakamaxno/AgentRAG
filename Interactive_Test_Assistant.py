from gigachat import GigaChat
import os
from dotenv import load_dotenv
import logging
from datetime import datetime
from PyPDF2 import PdfReader
from typing import Dict, List, Optional
import json

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
ASSISTANT_PROMPT = """### Роль: Эксперт по тестированию
Ты - опытный специалист по тестированию программного обеспечения, который может отвечать на вопросы о тестировании и создавать тестовые сценарии.

### Задача
1. Проанализируй предоставленную документацию
2. Ответь на вопрос пользователя, основываясь на документации и своих знаниях
3. Если запрошено, создай тестовые сценарии по указанной теме

### Формат ответа
1. Анализ вопроса:
   - Понимание контекста
   - Ключевые аспекты

2. Ответ на вопрос:
   - Подробное объяснение
   - Примеры, если применимо
   - Ссылки на документацию, если применимо

3. Тестовые сценарии (если запрошены):
   - Название теста
   - Идентификатор (TC001, TC002 и т.д.)
   - Тип тестирования (Frontend/Backend/API)
   - Предусловия
   - Шаги
   - Ожидаемый результат
   - Тестовые данные
"""

class InteractiveTestAssistant:
    def __init__(self):
        try:
            self.gigachat = GigaChat(
                credentials=os.getenv("GIGACHAT_CREDENTIALS"),
                verify_ssl_certs=False
            )
            logger.info("GigaChat успешно инициализирован")
            self.documents = {}  # Словарь для хранения загруженных документов
            self.current_doc = None  # Текущий активный документ
        except Exception as e:
            logger.error(f"Ошибка при инициализации GigaChat: {e}")
            raise

    def load_file(self, file_path: str) -> str:
        """Загружает содержимое файла в зависимости от его типа."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Файл не найден: {file_path}")
            
        file_extension = os.path.splitext(file_path)[1].lower()
        
        if file_extension == '.txt':
            with open(file_path, 'r', encoding='utf-8') as file:
                return file.read()
        elif file_extension == '.pdf':
            reader = PdfReader(file_path)
            text = ""
            for page in reader.pages:
                text += page.extract_text() + "\n"
            return text
        else:
            raise ValueError(f"Неподдерживаемый формат файла: {file_extension}")

    def load_document(self, file_path: str) -> bool:
        """Загружает документ и сохраняет его в памяти."""
        try:
            doc_name = os.path.basename(file_path)
            doc_content = self.load_file(file_path)
            self.documents[doc_name] = doc_content
            self.current_doc = doc_name
            logger.info(f"Документ {doc_name} успешно загружен")
            return True
        except Exception as e:
            logger.error(f"Ошибка при загрузке документа {file_path}: {e}")
            return False

    def load_documents_from_directory(self, directory: str) -> int:
        """Загружает все поддерживаемые документы из указанной директории."""
        if not os.path.exists(directory):
            logger.error(f"Директория не найдена: {directory}")
            return 0
        
        doc_files = [f for f in os.listdir(directory) if f.endswith(('.txt', '.pdf'))]
        
        if not doc_files:
            logger.warning(f"В директории {directory} не найдено поддерживаемых файлов (.txt или .pdf)")
            return 0
            
        logger.info(f"Найдено {len(doc_files)} файлов документации")
        
        loaded_count = 0
        for doc_file in doc_files:
            full_path = os.path.join(directory, doc_file)
            if self.load_document(full_path):
                loaded_count += 1
                
        return loaded_count

    def process_question(self, question: str) -> str:
        """Обрабатывает вопрос пользователя и возвращает ответ."""
        try:
            # Формируем контекст из текущего документа, если он есть
            context = ""
            if self.current_doc and self.current_doc in self.documents:
                context = f"### Документация:\n{self.documents[self.current_doc]}"
            
            # Формируем полный промпт
            full_prompt = f"{ASSISTANT_PROMPT}\n\n{context}\n\n### Вопрос пользователя:\n{question}"
            
            # Получаем ответ от модели
            response = self.gigachat.chat(full_prompt)
            
            if response and hasattr(response, 'choices') and response.choices:
                return response.choices[0].message.content
            else:
                logger.error("Не удалось получить ответ от ассистента")
                return "Извините, не удалось получить ответ. Пожалуйста, попробуйте еще раз."
                
        except Exception as e:
            logger.error(f"Ошибка при обработке вопроса: {e}")
            return f"Произошла ошибка при обработке вопроса: {str(e)}"

    def generate_test_scenario(self, topic: str) -> str:
        """Генерирует тестовый сценарий по указанной теме."""
        try:
            # Формируем контекст из текущего документа, если он есть
            context = ""
            if self.current_doc and self.current_doc in self.documents:
                context = f"### Документация:\n{self.documents[self.current_doc]}"
            
            # Формируем запрос на создание тестового сценария
            prompt = f"{ASSISTANT_PROMPT}\n\n{context}\n\n### Запрос на создание тестового сценария:\nСоздай подробный тестовый сценарий для темы: {topic}"
            
            # Получаем ответ от модели
            response = self.gigachat.chat(prompt)
            
            if response and hasattr(response, 'choices') and response.choices:
                return response.choices[0].message.content
            else:
                logger.error("Не удалось создать тестовый сценарий")
                return "Извините, не удалось создать тестовый сценарий. Пожалуйста, попробуйте еще раз."
                
        except Exception as e:
            logger.error(f"Ошибка при создании тестового сценария: {e}")
            return f"Произошла ошибка при создании тестового сценария: {str(e)}"

    def save_test_scenario(self, scenario: str, topic: str):
        """Сохраняет тестовый сценарий в файл."""
        try:
            test_scenarios_dir = os.path.abspath('test_scenarios')
            if not os.path.exists(test_scenarios_dir):
                os.makedirs(test_scenarios_dir)
                logger.info(f'Создана директория {test_scenarios_dir}/')
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            formatted_content = f"""
# Тестовый сценарий
## Тема
{topic}

## Сценарий
{scenario}

### Дополнительная информация
- Дата генерации: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
- Документ: {self.current_doc if self.current_doc else "Не указан"}
"""

            filename = os.path.join(test_scenarios_dir, f"test_scenario_{topic.replace(' ', '_')}_{timestamp}.md")
            
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(formatted_content)
            logger.info(f'Тестовый сценарий успешно сохранен в файл: {filename}')
            
            return filename
            
        except Exception as e:
            logger.error(f'Ошибка при сохранении тестового сценария: {str(e)}')
            return None

    def list_documents(self) -> List[str]:
        """Возвращает список загруженных документов."""
        return list(self.documents.keys())

    def set_current_document(self, doc_name: str) -> bool:
        """Устанавливает текущий активный документ."""
        if doc_name in self.documents:
            self.current_doc = doc_name
            logger.info(f"Текущий документ установлен: {doc_name}")
            return True
        else:
            logger.warning(f"Документ не найден: {doc_name}")
            return False

def print_menu():
    """Выводит меню команд."""
    print("\n=== Интерактивный помощник по тестированию ===")
    print("1. Загрузить документ")
    print("2. Загрузить все документы из директории")
    print("3. Показать список загруженных документов")
    print("4. Выбрать текущий документ")
    print("5. Задать вопрос")
    print("6. Создать тестовый сценарий")
    print("7. Выход")
    print("=============================================")

def main():
    try:
        # Создаем ассистента
        assistant = InteractiveTestAssistant()
        
        # Загружаем документы из директории по умолчанию, если она существует
        docs_dir = "doc"
        if os.path.exists(docs_dir):
            loaded_count = assistant.load_documents_from_directory(docs_dir)
            if loaded_count > 0:
                print(f"Загружено {loaded_count} документов из директории {docs_dir}")
        
        while True:
            print_menu()
            choice = input("Выберите действие (1-7): ")
            
            if choice == "1":
                # Загрузка документа
                file_path = input("Введите путь к файлу: ")
                if assistant.load_document(file_path):
                    print(f"Документ успешно загружен: {os.path.basename(file_path)}")
                else:
                    print("Не удалось загрузить документ")
            
            elif choice == "2":
                # Загрузка всех документов из директории
                directory = input("Введите путь к директории (по умолчанию 'doc'): ") or "doc"
                loaded_count = assistant.load_documents_from_directory(directory)
                print(f"Загружено {loaded_count} документов из директории {directory}")
            
            elif choice == "3":
                # Показать список загруженных документов
                documents = assistant.list_documents()
                if documents:
                    print("Загруженные документы:")
                    for i, doc in enumerate(documents, 1):
                        current_mark = " (текущий)" if doc == assistant.current_doc else ""
                        print(f"{i}. {doc}{current_mark}")
                else:
                    print("Нет загруженных документов")
            
            elif choice == "4":
                # Выбрать текущий документ
                documents = assistant.list_documents()
                if documents:
                    print("Загруженные документы:")
                    for i, doc in enumerate(documents, 1):
                        current_mark = " (текущий)" if doc == assistant.current_doc else ""
                        print(f"{i}. {doc}{current_mark}")
                    
                    doc_index = input("Выберите номер документа: ")
                    try:
                        doc_index = int(doc_index) - 1
                        if 0 <= doc_index < len(documents):
                            if assistant.set_current_document(documents[doc_index]):
                                print(f"Текущий документ установлен: {documents[doc_index]}")
                            else:
                                print("Не удалось установить текущий документ")
                        else:
                            print("Неверный номер документа")
                    except ValueError:
                        print("Введите корректный номер")
                else:
                    print("Нет загруженных документов")
            
            elif choice == "5":
                # Задать вопрос
                if not assistant.current_doc:
                    print("Сначала выберите документ (пункт 4)")
                    continue
                
                question = input("Введите ваш вопрос: ")
                print("\nОбработка вопроса...")
                answer = assistant.process_question(question)
                print("\nОтвет:")
                print(answer)
            
            elif choice == "6":
                # Создать тестовый сценарий
                if not assistant.current_doc:
                    print("Сначала выберите документ (пункт 4)")
                    continue
                
                topic = input("Введите тему для тестового сценария: ")
                print("\nСоздание тестового сценария...")
                scenario = assistant.generate_test_scenario(topic)
                print("\nТестовый сценарий:")
                print(scenario)
                
                save = input("\nСохранить тестовый сценарий в файл? (y/n): ")
                if save.lower() == 'y':
                    filename = assistant.save_test_scenario(scenario, topic)
                    if filename:
                        print(f"Тестовый сценарий сохранен в файл: {filename}")
                    else:
                        print("Не удалось сохранить тестовый сценарий")
            
            elif choice == "7":
                # Выход
                print("До свидания!")
                break
            
            else:
                print("Неверный выбор. Пожалуйста, выберите действие от 1 до 7.")

    except Exception as e:
        logger.error(f"Ошибка в работе программы: {e}")
        logger.exception("Подробности ошибки:")
        print(f"Произошла ошибка: {str(e)}")

if __name__ == "__main__":
    main() 