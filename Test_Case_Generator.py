from gigachat import GigaChat
import os
import sys
import logging
import re
import requests
import tempfile
import shutil
import subprocess
from datetime import datetime
from dotenv import load_dotenv
import PyPDF2
import argparse
import glob
import tkinter as tk
from tkinter import filedialog

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

# RAG prompt для генерации автотестов на основе примеров
rag_prompt = """### Ты – генератор автоматизированных тестовых сценариев на основе существующих примеров.

#### Основная задача
Создание автоматизированных тестовых сценариев на основании предоставленного примера кода и ручных тест-кейсов. Язык программирования выбирается автоматически на основе примера кода.

---

#### Требования к выполнению:
1. **Анализируем шаблон**:  
   На первом этапе проанализируй структуру предоставленного примера кода. Это включает определение используемых импортов, основных классов, методов и других элементов программы.

2. **Преобразуем тест-кейсы**:  
   Для каждого ручного тест-кейса:
   - Извлекаем название и описание.
   - Разбиваем описание на конкретные шаги.
   - Переводим эти шаги в программный код, используя методы и конструкции, найденные в примере.

3. **Синтаксис и соглашения**:  
   Код должен строго следовать правилам выбранного языка программирования. Также учитываем стилистические соглашения примера, включая отступы, именование переменных и методов, использование комментариев.

---

#### Форматирование выходных данных:
Каждая часть сценария должна быть оформлена в виде функционального кода, следуя стилю примера.

---

#### Примеры:
##### Пример 1: Шаблон (Java):  
```java
public class LoginTest {
    @Test
    public void loginWithValidCredentials() {
        // Ваш код здесь
    }
}
```

##### Ручной тест-кейс:  
1. Войдите на сайт.
2. Заполните поле email: user@example.com.
3. Заполните поле password: mypassword.
4. Нажмите кнопку "Login".
5. Проверьте успешный переход на домашнюю страницу.

##### Автоматизированный тест (выход):  
```java
@Test
public void successfulLogin() {
    driver.get("https://site.example");
    driver.findElement(By.id("email")).sendKeys("user@example.com");
    driver.findElement(By.id("password")).sendKeys("mypassword");
    driver.findElement(By.id("login-button")).click();
    
    WebElement homePageTitle = driver.findElement(By.className("home-title"));
    Assert.assertTrue(homePageTitle.isDisplayed());
}
```

---

#### Примечания:
- Обратите особое внимание на уникальность каждого тест-кейса и адаптируйте его в соответствии с особенностями вашего приложения.
- Старайтесь избегать дублирования кода за счет вынесения часто используемых операций в общие методы.

---

#### Важные критерии качества:
- Четкость и точность реализации шагов тестирования.
- Корректность выбора языка программирования на основе примера.
- Поддержание единообразия стиля кода.
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

def save_response(question, response, response_type="general", language="java"):
    """
    Сохраняет ответ в структурированном формате в отдельный файл.
    
    Args:
        question (str): Вопрос пользователя
        response (str): Ответ системы
        response_type (str): Тип ответа (например, 'general', 'test_case', etc.)
        language (str): Язык программирования (например, 'java', 'python', etc.)
    """
    try:
        # Создаем директории если их нет
        responses_dir = os.path.abspath('responses')
        code_dir = os.path.join(responses_dir, language)
        
        logger.info(f"Создание директорий: {responses_dir}, {code_dir}")
        for dir_path in [responses_dir, code_dir]:
            if not os.path.exists(dir_path):
                os.makedirs(dir_path)
                logger.info(f'Создана директория {dir_path}/')
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        logger.info(f"Создание файлов с временной меткой: {timestamp}")
        
        # Определяем расширение файла на основе языка
        file_extension = {
            "java": ".java",
            "python": ".py",
            "javascript": ".js",
            "typescript": ".ts",
            "csharp": ".cs",
            "ruby": ".rb",
            "php": ".php",
            "go": ".go",
            "kotlin": ".kt",
            "swift": ".swift"
        }.get(language.lower(), ".txt")
        
        # Форматируем ответ в структурированном виде
        formatted_response = f"""
# Результат генерации автотеста
## Исходный запрос
{question}

## Сгенерированное решение
### Описание
{response.split('```')[0] if '```' in response else response}

### Код решения
```{language}
{re.search(f'```{language}\n(.*?)\n```', str(response), re.DOTALL).group(1) if f'```{language}' in response else ''}
```

### Практические рекомендации
1. Перед запуском теста убедитесь, что все необходимые зависимости установлены
2. Проверьте наличие всех импортированных классов
3. При необходимости настройте тестовое окружение
4. Запустите тест с помощью соответствующего тестового фреймворка

### Дополнительная информация
- Дата генерации: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
- Тип ответа: {response_type}
- Язык программирования: {language}
"""

        # Сохраняем форматированный ответ
        txt_filename = os.path.join(responses_dir, f"response_{response_type}_{timestamp}.md")
        logger.info(f"Сохранение ответа в файл: {txt_filename}")
        
        with open(txt_filename, 'w', encoding='utf-8') as f:
            f.write(formatted_response)
        logger.info(f'Ответ успешно сохранен в файл: {txt_filename}')
        
        # Если есть код, сохраняем его отдельно
        code_block_pattern = f'```{language}\n(.*?)\n```'
        code_match = re.search(code_block_pattern, str(response), re.DOTALL)
        if code_match:
            code = code_match.group(1)
            class_name_match = re.search(r'public class (\w+)', code) or re.search(r'class (\w+)', code)
            class_name = class_name_match.group(1) if class_name_match else "Test"
            
            code_filename = os.path.join(code_dir, f"{class_name}_{timestamp}{file_extension}")
            logger.info(f"Сохранение кода в файл: {code_filename}")
            
            with open(code_filename, 'w', encoding='utf-8') as f:
                f.write(code)
            logger.info(f'Код успешно сохранен в файл: {code_filename}')
        else:
            logger.warning(f"Не удалось извлечь код на языке {language} из ответа")
    except Exception as e:
        logger.error(f'Ошибка при сохранении ответа: {str(e)}')
        logger.exception("Подробности ошибки:")
        raise

def clone_github_repo(repo_url, branch="main"):
    """
    Клонирует репозиторий с GitHub во временную директорию.
    
    Args:
        repo_url (str): URL репозитория GitHub
        branch (str): Ветка для клонирования
        
    Returns:
        str: Путь к временной директории с клонированным репозиторием
    """
    try:
        # Создаем временную директорию
        temp_dir = tempfile.mkdtemp()
        logger.info(f"Создана временная директория: {temp_dir}")
        
        # Проверяем доступность репозитория
        logger.info(f"Проверка доступности репозитория: {repo_url}")
        try:
            # Проверяем, что URL имеет правильный формат
            if not repo_url.startswith(('http://', 'https://', 'git@')):
                repo_url = f"https://github.com/{repo_url}"
                logger.info(f"URL репозитория преобразован в: {repo_url}")
            
            # Проверяем доступность репозитория через HTTP запрос
            if repo_url.startswith(('http://', 'https://')):
                response = requests.head(repo_url, allow_redirects=True, timeout=10)
                if response.status_code != 200:
                    logger.error(f"Репозиторий недоступен. Код ответа: {response.status_code}")
                    raise ValueError(f"Репозиторий недоступен: {repo_url}")
            
            # Клонируем репозиторий
            logger.info(f"Клонирование репозитория {repo_url} в {temp_dir}")
            result = subprocess.run(
                ["git", "clone", "-b", branch, repo_url, temp_dir], 
                check=True,
                capture_output=True,
                text=True
            )
            logger.info(f"Клонирование успешно завершено: {result.stdout}")
            
            return temp_dir
        except subprocess.CalledProcessError as e:
            logger.error(f"Ошибка при клонировании репозитория: {e}")
            logger.error(f"Вывод команды: {e.stdout}")
            logger.error(f"Ошибка команды: {e.stderr}")
            
            # Проверяем наличие git в системе
            try:
                subprocess.run(["git", "--version"], check=True, capture_output=True)
            except (subprocess.CalledProcessError, FileNotFoundError):
                logger.error("Git не установлен или не доступен в системе")
                raise ValueError("Git не установлен или не доступен в системе. Пожалуйста, установите Git.")
            
            # Проверяем доступность репозитория
            if "Repository not found" in str(e.stderr):
                raise ValueError(f"Репозиторий не найден: {repo_url}. Проверьте URL и права доступа.")
            elif "Authentication failed" in str(e.stderr):
                raise ValueError(f"Ошибка аутентификации при доступе к репозиторию: {repo_url}. Возможно, требуется авторизация.")
            elif "fatal: Remote branch" in str(e.stderr) and "not found" in str(e.stderr):
                raise ValueError(f"Ветка '{branch}' не найдена в репозитории: {repo_url}")
            else:
                raise ValueError(f"Ошибка при клонировании репозитория: {e.stderr}")
    except Exception as e:
        logger.error(f"Ошибка при клонировании репозитория: {e}")
        logger.exception("Подробности ошибки:")
        raise

def extract_code_from_repo(repo_path, file_pattern="*.java"):
    """
    Извлекает код из файлов в репозитории.
    
    Args:
        repo_path (str): Путь к репозиторию
        file_pattern (str): Шаблон для поиска файлов
        
    Returns:
        list: Список словарей с содержимым файлов
    """
    try:
        code_files = []
        
        # Находим все файлы, соответствующие шаблону
        for root, _, files in os.walk(repo_path):
            for file in files:
                if file.endswith(file_pattern.replace("*", "")):
                    file_path = os.path.join(root, file)
                    logger.info(f"Обработка файла: {file_path}")
                    
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                        
                        # Определяем язык программирования по расширению файла
                        _, ext = os.path.splitext(file)
                        language = {
                            ".java": "java",
                            ".py": "python",
                            ".js": "javascript",
                            ".ts": "typescript",
                            ".cs": "csharp",
                            ".rb": "ruby",
                            ".php": "php",
                            ".go": "go",
                            ".kt": "kotlin",
                            ".swift": "swift"
                        }.get(ext, "unknown")
                        
                        code_files.append({
                            "content": content,
                            "metadata": {
                                "source": file_path,
                                "language": language,
                                "filename": file
                            }
                        })
                    except Exception as e:
                        logger.error(f"Ошибка при чтении файла {file_path}: {e}")
                        continue
        
        return code_files
    except Exception as e:
        logger.error(f"Ошибка при извлечении кода из репозитория: {e}")
        logger.exception("Подробности ошибки:")
        raise

def load_file(file_path):
    """
    Загружает файл и возвращает его содержимое.
    
    Args:
        file_path (str): Путь к файлу
        
    Returns:
        list: Список с содержимым файла
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Файл не найден: {file_path}")
    
    try:
        # Определяем тип файла по расширению
        _, ext = os.path.splitext(file_path)
        
        if ext.lower() == '.txt':
            with open(file_path, 'r', encoding='utf-8') as file:
                content = file.read()
            return [{"content": content, "metadata": {"source": file_path, "type": "txt"}}]
        
        elif ext.lower() == '.pdf':
            content = extract_text_from_pdf(file_path)
            return [{"content": content, "metadata": {"source": file_path, "type": "pdf"}}]
        
        else:
            raise ValueError(f"Неподдерживаемый формат файла: {ext}")
    
    except Exception as e:
        logger.error(f"Ошибка при загрузке файла {file_path}: {e}")
        logger.exception("Подробности ошибки:")
        raise

def extract_text_from_pdf(pdf_path):
    """
    Извлекает текст из PDF-файла.
    
    Args:
        pdf_path (str): Путь к PDF-файлу
        
    Returns:
        str: Извлеченный текст
    """
    try:
        text = ""
        with open(pdf_path, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            for page_num in range(len(reader.pages)):
                page = reader.pages[page_num]
                text += page.extract_text() + "\n"
        return text
    except Exception as e:
        logger.error(f"Ошибка при извлечении текста из PDF: {e}")
        logger.exception("Подробности ошибки:")
        raise

def detect_language_from_code(code_files):
    """
    Определяет язык программирования на основе предоставленных файлов кода.
    
    Args:
        code_files (list): Список файлов с кодом
        
    Returns:
        str: Определенный язык программирования
    """
    # Подсчитываем количество файлов для каждого языка
    language_counts = {}
    
    for file in code_files:
        language = file["metadata"].get("language", "unknown")
        if language in language_counts:
            language_counts[language] += 1
        else:
            language_counts[language] = 1
    
    # Если есть файлы с определенным языком, возвращаем наиболее часто встречающийся
    if language_counts:
        return max(language_counts.items(), key=lambda x: x[1])[0]
    
    # Если не удалось определить язык, возвращаем "java" по умолчанию
    return "java"

def generate_test_case(test_case_content, example_code_files=None):
    """
    Генерирует автоматизированный тест на основе ручного тест-кейса и примера кода.
    
    Args:
        test_case_content (str): Содержимое ручного тест-кейса
        example_code_files (list, optional): Список файлов с примером кода
        
    Returns:
        str: Сгенерированный код теста
    """
    try:
        # Определяем язык программирования на основе примера кода
        language = "java"  # По умолчанию
        if example_code_files:
            language = detect_language_from_code(example_code_files)
            logger.info(f"Определен язык программирования: {language}")
        
        # Формируем пример кода для промпта
        example_code = ""
        if example_code_files:
            # Берем первый файл с определенным языком
            for file in example_code_files:
                if file["metadata"].get("language") == language:
                    example_code = file["content"]
                    break
        
        # Формируем промпт с контекстом
        full_prompt = f"""
        {rag_prompt}
        
        ### Пример кода на языке {language}:
        ```
        {example_code}
        ```
        
        ### Ручной тест-кейс:
        {test_case_content}
        
        ### Важные требования:
        1. Ответ должен содержать полный код теста на языке {language}
        2. Код должен быть оформлен в блоке ```{language}
        3. Должны быть включены все необходимые импорты
        4. Тест должен соответствовать описанию из тест-кейса
        5. Должны быть реализованы все шаги теста
        6. Стиль кода должен соответствовать стилю примера
        """
        
        logger.info("Отправка запроса к GigaChat")
        
        # Отправляем запрос к GigaChat
        response = gigachat.chat(full_prompt)
        
        if response and hasattr(response, 'choices') and response.choices:
            response_text = response.choices[0].message.content
            logger.info(f"Получен ответ от GigaChat длиной {len(response_text)} символов")
            return response_text, language
        else:
            logger.error("Не удалось получить ответ от GigaChat")
            return "", language
        
    except Exception as e:
        logger.error(f"Ошибка при генерации теста: {e}")
        logger.exception("Подробности ошибки:")
        return "", "java"

def process_github_example(repo_url, branch="main", file_pattern="*.java"):
    """
    Обрабатывает пример кода из GitHub репозитория.
    
    Args:
        repo_url (str): URL репозитория GitHub
        branch (str): Ветка для клонирования
        file_pattern (str): Шаблон для поиска файлов
        
    Returns:
        list: Список файлов с кодом
    """
    try:
        # Проверяем, что URL не пустой
        if not repo_url or repo_url.strip() == "":
            logger.warning("URL репозитория не указан, пропускаем обработку GitHub примера")
            return None
            
        # Клонируем репозиторий
        try:
            repo_path = clone_github_repo(repo_url, branch)
            logger.info(f"Репозиторий успешно клонирован в {repo_path}")
        except ValueError as e:
            logger.error(f"Ошибка при клонировании репозитория: {e}")
            print(f"\nОшибка при клонировании репозитория: {e}")
            print("Продолжаем работу без примера из GitHub.")
            return None
        
        # Извлекаем код из файлов
        try:
            code_files = extract_code_from_repo(repo_path, file_pattern)
            logger.info(f"Извлечено {len(code_files)} файлов с кодом")
            
            if not code_files:
                logger.warning(f"Не найдено файлов, соответствующих шаблону {file_pattern}")
                print(f"\nПредупреждение: Не найдено файлов, соответствующих шаблону {file_pattern}")
                print("Продолжаем работу без примера из GitHub.")
                return None
                
            return code_files
        except Exception as e:
            logger.error(f"Ошибка при извлечении кода из репозитория: {e}")
            logger.exception("Подробности ошибки:")
            print(f"\nОшибка при извлечении кода из репозитория: {e}")
            print("Продолжаем работу без примера из GitHub.")
            return None
        finally:
            # Удаляем временную директорию
            try:
                if os.path.exists(repo_path):
                    shutil.rmtree(repo_path)
                    logger.info(f"Временная директория {repo_path} удалена")
            except Exception as e:
                logger.error(f"Ошибка при удалении временной директории: {e}")
    except Exception as e:
        logger.error(f"Ошибка при обработке примера из GitHub: {e}")
        logger.exception("Подробности ошибки:")
        print(f"\nОшибка при обработке примера из GitHub: {e}")
        print("Продолжаем работу без примера из GitHub.")
        return None

def select_file_dialog():
    """
    Открывает диалоговое окно для выбора файла.
    
    Returns:
        str: Путь к выбранному файлу
    """
    root = tk.Tk()
    root.withdraw()  # Скрываем основное окно
    
    file_path = filedialog.askopenfilename(
        title="Выберите файл с тест-кейсом",
        filetypes=[
            ("Текстовые файлы", "*.txt"),
            ("PDF файлы", "*.pdf"),
            ("Все файлы", "*.*")
        ]
    )
    
    return file_path

def interactive_mode():
    """
    Запускает интерактивный режим для выбора файла и указания ссылки на GitHub.
    
    Returns:
        tuple: (путь к файлу тест-кейса, URL репозитория GitHub, ветка, шаблон файлов)
    """
    print("\n=== Генератор автоматизированных тест-кейсов ===")
    print("Этот инструмент поможет вам создать автоматизированные тест-кейсы на основе ручных тест-кейсов и примеров кода.")
    
    # Выбор файла с тест-кейсом
    print("\nШаг 1: Выберите файл с ручным тест-кейсом (PDF или TXT)")
    print("Откроется диалоговое окно для выбора файла...")
    
    test_case_path = select_file_dialog()
    
    if not test_case_path:
        print("Файл не выбран. Используем файл по умолчанию: test_cases/login_test.txt")
        test_case_path = "test_cases/login_test.txt"
        if not os.path.exists(test_case_path):
            print(f"Ошибка: Файл {test_case_path} не найден.")
            sys.exit(1)
    
    print(f"Выбран файл: {test_case_path}")
    
    # Ввод URL репозитория GitHub
    print("\nШаг 2: Введите URL репозитория GitHub с примером кода")
    print("Пример: https://github.com/username/repo.git")
    github_url = input("URL репозитория (или нажмите Enter для пропуска): ").strip()
    
    if not github_url:
        print("URL репозитория не указан. Будет использован только ручной тест-кейс.")
        return test_case_path, None, "main", "*.java"
    
    # Ввод ветки репозитория
    print("\nШаг 3: Введите ветку репозитория (по умолчанию: main)")
    branch = input("Ветка (или нажмите Enter для использования main): ").strip() or "main"
    
    # Ввод шаблона файлов
    print("\nШаг 4: Введите шаблон для поиска файлов (по умолчанию: *.java)")
    print("Примеры: *.java, *.py, *.js, *.ts, *.cs")
    file_pattern = input("Шаблон (или нажмите Enter для использования *.java): ").strip() or "*.java"
    
    return test_case_path, github_url, branch, file_pattern

def main():
    """
    Основная функция программы.
    """
    parser = argparse.ArgumentParser(description="Генератор автоматизированных тест-кейсов")
    parser.add_argument("--test-case", "-t", help="Путь к файлу с ручным тест-кейсом (PDF или TXT)")
    parser.add_argument("--github", "-g", help="URL репозитория GitHub с примером кода")
    parser.add_argument("--branch", "-b", default="main", help="Ветка репозитория GitHub (по умолчанию: main)")
    parser.add_argument("--pattern", "-p", default="*.java", help="Шаблон для поиска файлов в репозитории (по умолчанию: *.java)")
    parser.add_argument("--interactive", "-i", action="store_true", help="Запуск в интерактивном режиме")
    
    args = parser.parse_args()
    
    # Если указан флаг интерактивного режима или не указаны обязательные параметры
    if args.interactive or (not args.test_case and not args.github):
        test_case_path, github_url, branch, file_pattern = interactive_mode()
    else:
        test_case_path = args.test_case
        github_url = args.github
        branch = args.branch
        file_pattern = args.pattern
    
    try:
        # Проверяем наличие файла тест-кейса
        if not test_case_path:
            print("Ошибка: Не указан путь к файлу с тест-кейсом.")
            print("Используйте параметр --test-case или запустите в интерактивном режиме.")
            return
            
        # Загружаем ручной тест-кейс
        try:
            test_case_documents = load_file(test_case_path)
            test_case_content = "\n".join([doc["content"] for doc in test_case_documents])
            print(f"\nЗагружен тест-кейс из файла: {test_case_path}")
        except Exception as e:
            logger.error(f"Ошибка при загрузке тест-кейса: {e}")
            logger.exception("Подробности ошибки:")
            print(f"\nОшибка при загрузке тест-кейса: {e}")
            return
        
        # Обрабатываем пример кода из GitHub, если указан
        example_code_files = None
        if github_url:
            print(f"\nЗагрузка примера кода из репозитория: {github_url}")
            example_code_files = process_github_example(github_url, branch, file_pattern)
            
            if example_code_files:
                print(f"Загружено {len(example_code_files)} файлов с примером кода")
            else:
                print("Не удалось загрузить примеры из GitHub. Продолжаем работу без них.")
        
        # Генерируем автоматизированный тест
        question = f"Создай автоматизированный тест на основе ручного тест-кейса из файла {os.path.basename(test_case_path)}"
        print("\nЗадаю вопрос для создания автотеста:", question)
        
        try:
            response, language = generate_test_case(test_case_content, example_code_files)
            
            if response:
                save_response(question, response, "test_case", language)
                print(f"\nАвтоматизированный тест успешно сгенерирован и сохранен в директорию 'responses/{language}/'")
            else:
                logger.warning("Не удалось получить ответ с кодом")
                print("\nНе удалось сгенерировать автоматизированный тест")
        except Exception as e:
            logger.error(f"Ошибка при генерации теста: {e}")
            logger.exception("Подробности ошибки:")
            print(f"\nОшибка при генерации теста: {e}")
    
    except Exception as e:
        logger.error(f"Ошибка при создании автотеста: {e}")
        logger.exception("Подробности ошибки:")
        print(f"\nПроизошла ошибка: {e}")

if __name__ == "__main__":
    main() 