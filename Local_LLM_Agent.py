from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage, SystemMessage
import logging
import os
from dotenv import load_dotenv
from datetime import datetime
import re
import sys

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)

# Промпт для генерации автотестов
llm_prompt = """### Роль для модели
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

# Настройка LLM
try:
    local_llm = "llama2:7b"  # Используем установленную модель
    llm = ChatOllama(
        model=local_llm,
        temperature=0,
        verbose=True
    )
    # Проверка доступности модели
    llm.invoke([HumanMessage(content="test")])
    logger.info(f"Модель {local_llm} успешно инициализирована")
except Exception as e:
    logger.error(f"Ошибка при инициализации модели {local_llm}: {e}")
    raise Exception("Не удалось инициализировать модель LLM")

def save_response(question, response, response_type="general"):
    """
    Сохраняет ответ в структурированном формате в отдельный файл.
    
    Args:
        question (str): Вопрос пользователя
        response (str): Ответ системы
        response_type (str): Тип ответа (например, 'general', 'test_case', etc.)
    """
    # Создаем директории если их нет
    responses_dir = 'responses'
    java_dir = os.path.join(responses_dir, 'java')
    for dir_path in [responses_dir, java_dir]:
        if not os.path.exists(dir_path):
            os.makedirs(dir_path)
            logger.info(f'Создана директория {dir_path}/')
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
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
    txt_filename = f"{responses_dir}/response_{response_type}_{timestamp}.md"
    try:
        with open(txt_filename, 'w', encoding='utf-8') as f:
            f.write(formatted_response)
        logger.info(f'Ответ сохранен в файл: {txt_filename}')
        
        # Если есть Java-код, сохраняем его отдельно
        if '```java' in response:
            java_code_match = re.search(r'```java\n(.*?)\n```', str(response), re.DOTALL)
            if java_code_match:
                java_code = java_code_match.group(1)
                class_name_match = re.search(r'public class (\w+)', java_code)
                class_name = class_name_match.group(1) if class_name_match else "Test"
                
                java_filename = f"{java_dir}/{class_name}_{timestamp}.java"
                with open(java_filename, 'w', encoding='utf-8') as f:
                    f.write(java_code)
                logger.info(f'Java-код сохранен в файл: {java_filename}')
    except Exception as e:
        logger.error(f'Ошибка при сохранении ответа: {e}')

def generate_test_from_description(test_description):
    """
    Генерирует автоматизированный тест на основе описания ручного тест-кейса.
    
    Args:
        test_description (str): Описание ручного тест-кейса
    
    Returns:
        str: Сгенерированный код автотеста
    """
    try:
        # Формируем промпт с описанием тест-кейса
        full_prompt = f"""
        {llm_prompt}
        
        Ручной тест-кейс для автоматизации:
        {test_description}
        """
        
        # Генерируем ответ с помощью LLM
        response = llm.invoke([
            SystemMessage(content="Ты - эксперт по автоматизации тестирования. Создай автотест на Java."),
            HumanMessage(content=full_prompt)
        ])
        
        return str(response.content)
    except Exception as e:
        logger.error(f"Ошибка при генерации теста: {e}")
        return None

if __name__ == "__main__":
    # Путь к директории с тест-кейсами
    test_cases_dir = "test_cases"
    
    try:
        # Проверяем существование директории
        if not os.path.exists(test_cases_dir):
            logger.error(f"Директория не найдена: {test_cases_dir}")
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
                # Читаем содержимое файла
                with open(full_path, 'r', encoding='utf-8') as f:
                    test_description = f.read()
                
                # Генерируем автотест
                generated_test = generate_test_from_description(test_description)
                
                if generated_test:
                    # Сохраняем результат
                    test_name = os.path.splitext(test_case_file)[0]
                    save_response(f"Создать автотест на основе {test_case_file}", 
                                generated_test, 
                                f"test_case_{test_name}")
                    print(f"Автотест для {test_case_file} успешно сгенерирован и сохранен!")
                else:
                    print(f"Не удалось сгенерировать автотест для {test_case_file}")
                    
            except Exception as e:
                logger.error(f"Ошибка при обработке файла {test_case_file}: {e}")
                logger.exception("Подробности ошибки:")
                continue
            
    except Exception as e:
        logger.error(f"Ошибка в основном блоке программы: {e}")
        logger.exception("Подробности ошибки:") 