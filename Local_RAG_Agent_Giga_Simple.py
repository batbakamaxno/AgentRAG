from gigachat import GigaChat
import os
from dotenv import load_dotenv
import logging
import re
from datetime import datetime
from langchain_community.document_loaders import TextLoader

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

def generate_test_case(test_case_content):
    """
    Генерирует автоматизированный тест на основе ручного тест-кейса.
    
    Args:
        test_case_content (str): Содержимое ручного тест-кейса
    
    Returns:
        str: Сгенерированный код теста
    """
    try:
        # Формируем промпт с контекстом
        full_prompt = f"""
        {rag_prompt}
        
        ### Ручной тест-кейс:
        {test_case_content}
        
        ### Важные требования:
        1. Ответ должен содержать полный Java-код теста
        2. Код должен быть оформлен в блоке ```java
        3. Должны быть включены все необходимые импорты
        4. Тест должен соответствовать описанию из тест-кейса
        5. Должны быть реализованы все шаги теста
        """
        
        logger.info("Отправка запроса к GigaChat")
        
        # Отправляем запрос к GigaChat
        response = gigachat.chat(full_prompt)
        
        if response and hasattr(response, 'content'):
            response_text = response.content
            logger.info(f"Получен ответ от GigaChat длиной {len(response_text)} символов")
            return response_text
        else:
            logger.error("Не удалось получить ответ от GigaChat")
            return ""
        
    except Exception as e:
        logger.error(f"Ошибка при генерации теста: {e}")
        logger.exception("Подробности ошибки:")
        return ""

if __name__ == "__main__":
    # Пример использования системы для создания автотеста из ручного тест-кейса
    
    # Функция для загрузки файла
    def load_file(file_path):
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Файл не найден: {file_path}")
            
        if file_path.endswith('.txt'):
            loader = TextLoader(file_path, encoding='utf-8')
        else:
            raise ValueError("Поддерживаются только TXT файлы")
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
                test_case_content = "\n".join([doc.page_content for doc in test_case_documents])
                
                question = f"Создай автоматизированный тест на Java на основе ручного тест-кейса из файла {test_case_file}"
                print("\nЗадаю вопрос для создания автотеста:", question)
                
                response = generate_test_case(test_case_content)
                
                if response:
                    save_response(question, response, "test_case")
                else:
                    logger.warning("Не удалось получить ответ с кодом")
                    
            except Exception as e:
                logger.error(f"Ошибка при создании автотеста: {e}")
                logger.exception("Подробности ошибки:")
                continue  # Продолжаем обработку следующего файла

    except Exception as e:
        logger.error(f"Ошибка при создании автотеста: {e}")
        logger.exception("Подробности ошибки:") 