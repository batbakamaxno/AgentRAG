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
import pandas as pd
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import DirectoryLoader, TextLoader
from collections import Counter
import json
from typing import Dict, List, Optional, Any, Protocol, abstractmethod
from abc import ABC, abstractmethod

# Настройка логирования
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('test_generator.log'),
        logging.StreamHandler()
    ]
)

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

# Настройка GigaChat с расширенными параметрами
try:
    gigachat = GigaChat(
        credentials=os.getenv("GIGACHAT_CREDENTIALS"),
        scope=os.getenv("GIGACHAT_API_SCOPE", "GIGACHAT_API_PERS"),
        model=os.getenv("GIGACHAT_MODEL_NAME", "GigaChat:latest"),
        verify_ssl_certs=False,
        profanity_check=False,
        timeout=600,
        top_p=0.3,
        temperature=0.1,
        max_tokens=6000
    )
    logger.info("GigaChat успешно инициализирован с расширенными параметрами")
except Exception as e:
    logger.error(f"Ошибка при инициализации GigaChat: {e}")
    raise Exception("Не удалось инициализировать GigaChat")

class FileHandler(ABC):
    """Абстрактный класс для работы с файлами"""
    
    @abstractmethod
    def load_file(self, file_path: str) -> List[Dict]:
        """Загружает содержимое файла"""
        pass
    
    @abstractmethod
    def save_file(self, file_path: str, content: str) -> None:
        """Сохраняет содержимое в файл"""
        pass

class TextFileHandler(FileHandler):
    """Класс для работы с текстовыми файлами"""
    
    def load_file(self, file_path: str) -> List[Dict]:
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                content = file.read()
            return [{"content": content, "metadata": {"source": file_path, "type": "txt"}}]
        except Exception as e:
            logger.error(f"Ошибка при загрузке текстового файла {file_path}: {e}")
            raise
    
    def save_file(self, file_path: str, content: str) -> None:
        try:
            with open(file_path, 'w', encoding='utf-8') as file:
                file.write(content)
        except Exception as e:
            logger.error(f"Ошибка при сохранении текстового файла {file_path}: {e}")
            raise

class PDFFileHandler(FileHandler):
    """Класс для работы с PDF файлами"""
    
    def load_file(self, file_path: str) -> List[Dict]:
        try:
            text = ""
            with open(file_path, 'rb') as file:
                reader = PyPDF2.PdfReader(file)
                for page_num in range(len(reader.pages)):
                    page = reader.pages[page_num]
                    text += page.extract_text() + "\n"
            return [{"content": text, "metadata": {"source": file_path, "type": "pdf"}}]
        except Exception as e:
            logger.error(f"Ошибка при загрузке PDF файла {file_path}: {e}")
            raise
    
    def save_file(self, file_path: str, content: str) -> None:
        raise NotImplementedError("Сохранение в PDF формат не поддерживается")

class CSVFileHandler(FileHandler):
    """Класс для работы с CSV файлами"""
    
    def load_file(self, file_path: str) -> List[Dict]:
        try:
            # Пытаемся определить разделитель и кодировку
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as file:
                first_line = file.readline().strip()
                delimiter = ',' if ',' in first_line else ';' if ';' in first_line else '\t'
            
            # Загружаем CSV файл с помощью pandas
            df = pd.read_csv(file_path, delimiter=delimiter, encoding='utf-8', errors='ignore')
            
            # Формируем структурированный текст из CSV
            test_cases = []
            for _, row in df.iterrows():
                test_case = {}
                for column in df.columns:
                    if pd.notna(row[column]):  # Проверяем, что значение не NaN
                        test_case[column] = str(row[column])
                
                # Форматируем тест-кейс в читаемый вид
                formatted_test_case = "### Тест-кейс\n"
                for key, value in test_case.items():
                    formatted_test_case += f"**{key}**: {value}\n"
                formatted_test_case += "\n"
                
                test_cases.append(formatted_test_case)
            
            return [{"content": "\n".join(test_cases), "metadata": {"source": file_path, "type": "csv"}}]
        except Exception as e:
            logger.error(f"Ошибка при загрузке CSV файла {file_path}: {e}")
            raise
    
    def save_file(self, file_path: str, content: str) -> None:
        try:
            # Преобразуем структурированный текст обратно в CSV
            lines = content.split('\n')
            data = []
            current_test_case = {}
            
            for line in lines:
                if line.startswith('**') and '**:' in line:
                    key, value = line.replace('**', '').split('**:', 1)
                    current_test_case[key.strip()] = value.strip()
                elif line.strip() == '' and current_test_case:
                    data.append(current_test_case)
                    current_test_case = {}
            
            if current_test_case:
                data.append(current_test_case)
            
            # Сохраняем в CSV
            df = pd.DataFrame(data)
            df.to_csv(file_path, index=False)
        except Exception as e:
            logger.error(f"Ошибка при сохранении CSV файла {file_path}: {e}")
            raise

class FileHandlerFactory:
    """Фабрика для создания обработчиков файлов"""
    
    @staticmethod
    def create_handler(file_path: str) -> FileHandler:
        _, ext = os.path.splitext(file_path)
        ext = ext.lower()
        
        if ext == '.txt':
            return TextFileHandler()
        elif ext == '.pdf':
            return PDFFileHandler()
        elif ext == '.csv':
            return CSVFileHandler()
        else:
            raise ValueError(f"Неподдерживаемый формат файла: {ext}")

class TestAnalyzer:
    """Класс для анализа тестов"""
    
    def __init__(self, project_path: str):
        self.project_path = project_path
    
    def analyze_tests(self, file_pattern: str = "**/*.java") -> Dict:
        """Анализирует существующие тесты в проекте"""
        try:
            # Загружаем все Java файлы из проекта
            loader = DirectoryLoader(self.project_path, glob=file_pattern, loader_cls=TextLoader)
            docs = loader.load()
            
            # Анализируем структуру тестов
            test_analysis = {
                "total_tests": len(docs),
                "test_classes": [],
                "test_methods": [],
                "frameworks_used": set(),
                "common_patterns": [],
                "test_categories": Counter(),
                "assertion_types": Counter(),
                "test_complexity": {
                    "simple": 0,
                    "medium": 0,
                    "complex": 0
                }
            }
            
            for doc in docs:
                content = doc.page_content
                # Анализируем использование тестовых фреймворков
                if "import org.junit" in content:
                    test_analysis["frameworks_used"].add("JUnit")
                if "import org.testng" in content:
                    test_analysis["frameworks_used"].add("TestNG")
                
                # Находим тестовые классы
                class_matches = re.finditer(r"class\s+(\w+)", content)
                for match in class_matches:
                    test_analysis["test_classes"].append(match.group(1))
                
                # Находим тестовые методы
                method_matches = re.finditer(r"@Test\s+public\s+void\s+(\w+)", content)
                for match in method_matches:
                    test_analysis["test_methods"].append(match.group(1))
                
                # Анализируем категории тестов
                if "@Category" in content:
                    category_matches = re.finditer(r"@Category\(([^)]+)\)", content)
                    for match in category_matches:
                        categories = match.group(1).split(",")
                        for category in categories:
                            category = category.strip().replace(".class", "")
                            test_analysis["test_categories"][category] += 1
                
                # Анализируем типы утверждений
                assertion_types = {
                    "assertEquals": r"assertEquals\s*\(",
                    "assertTrue": r"assertTrue\s*\(",
                    "assertFalse": r"assertFalse\s*\(",
                    "assertNotNull": r"assertNotNull\s*\(",
                    "assertNull": r"assertNull\s*\(",
                    "assertThat": r"assertThat\s*\("
                }
                
                for assertion_type, pattern in assertion_types.items():
                    if re.search(pattern, content):
                        test_analysis["assertion_types"][assertion_type] += 1
                
                # Оцениваем сложность теста
                method_count = len(re.findall(r"@Test\s+public\s+void\s+(\w+)", content))
                assertion_count = sum(test_analysis["assertion_types"].values())
                
                if method_count <= 2 and assertion_count <= 3:
                    test_analysis["test_complexity"]["simple"] += 1
                elif method_count <= 5 and assertion_count <= 10:
                    test_analysis["test_complexity"]["medium"] += 1
                else:
                    test_analysis["test_complexity"]["complex"] += 1
            
            # Преобразуем Counter в dict для сериализации
            test_analysis["test_categories"] = dict(test_analysis["test_categories"])
            test_analysis["assertion_types"] = dict(test_analysis["assertion_types"])
            test_analysis["frameworks_used"] = list(test_analysis["frameworks_used"])
            
            return test_analysis
            
        except Exception as e:
            logger.error(f"Ошибка при анализе существующих тестов: {e}")
            return {}
    
    def collect_analytics(self) -> Dict[str, Any]:
        """Собирает аналитические данные о проекте"""
        try:
            analytics = {
                "test_coverage": self._analyze_test_coverage(),
                "test_stability": self._analyze_test_stability(),
                "test_patterns": self._analyze_test_patterns(),
                "test_dependencies": self._analyze_test_dependencies()
            }
            return analytics
        except Exception as e:
            logger.error(f"Ошибка при сборе аналитических данных: {e}")
            return {}
    
    def _analyze_test_coverage(self) -> Dict[str, Any]:
        """Анализирует покрытие тестами кодовой базы"""
        return {
            "overall_coverage": 0.0,
            "class_coverage": {},
            "method_coverage": {},
            "line_coverage": {}
        }
    
    def _analyze_test_stability(self) -> Dict[str, Any]:
        """Анализирует стабильность тестов на основе истории запусков"""
        return {
            "flaky_tests": [],
            "stable_tests": [],
            "test_execution_time": {}
        }
    
    def _analyze_test_patterns(self) -> Dict[str, Any]:
        """Анализирует паттерны в тестах для выявления лучших практик"""
        test_analysis = self.analyze_tests()
        
        patterns = {
            "common_setup_methods": [],
            "common_teardown_methods": [],
            "common_test_data_sources": [],
            "common_assertion_patterns": []
        }
        
        # Анализ паттернов настройки и завершения
        for test_class in test_analysis.get("test_classes", []):
            if "@Before" in test_class:
                patterns["common_setup_methods"].append(test_class)
            if "@After" in test_class:
                patterns["common_teardown_methods"].append(test_class)
        
        # Анализ источников тестовых данных
        data_source_patterns = [
            r"@DataProvider",
            r"@Parameters",
            r"@TestData",
            r"loadTestData\(",
            r"readTestData\("
        ]
        
        for pattern in data_source_patterns:
            if re.search(pattern, str(test_analysis)):
                patterns["common_test_data_sources"].append(pattern)
        
        # Анализ паттернов утверждений
        for assertion_type, count in test_analysis.get("assertion_types", {}).items():
            if count > 0:
                patterns["common_assertion_patterns"].append(assertion_type)
        
        return patterns
    
    def _analyze_test_dependencies(self) -> Dict[str, Any]:
        """Анализирует зависимости между тестами и тестируемым кодом"""
        return {
            "test_dependencies": {},
            "code_dependencies": {},
            "shared_resources": []
        }

class GigaChatClient:
    """Класс для работы с GigaChat API"""
    
    def __init__(self):
        try:
            # Улучшенная инициализация GigaChat с дополнительными параметрами
            self.client = GigaChat(
                credentials=os.getenv("GIGACHAT_CREDENTIALS"),
                scope=os.getenv("GIGACHAT_API_SCOPE", "GIGACHAT_API_PERS"),
                model=os.getenv("GIGACHAT_MODEL_NAME", "GigaChat:latest"),
                verify_ssl_certs=False,
                profanity_check=False,
                timeout=600,
                top_p=0.3,
                temperature=0.1,
                max_tokens=6000
            )
            logger.info("GigaChat успешно инициализирован с расширенными параметрами")
        except Exception as e:
            logger.error(f"Ошибка при инициализации GigaChat: {e}")
            raise
    
    def generate_test(self, prompt: str) -> str:
        """Генерирует тест на основе промпта"""
        try:
            response = self.client.chat(prompt)
            
            if response and hasattr(response, 'choices') and response.choices:
                response_text = response.choices[0].message.content
                logger.info(f"Получен ответ от GigaChat длиной {len(response_text)} символов")
                return response_text
            else:
                logger.error("Не удалось получить ответ от GigaChat")
                return ""
                
        except Exception as e:
            logger.error(f"Ошибка при генерации теста: {e}")
            logger.exception("Подробности ошибки:")
            return ""

class TestGenerator:
    """Класс для генерации тестов"""
    
    def __init__(self, gigachat_client: GigaChatClient):
        self.gigachat_client = gigachat_client
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=2000,
            chunk_overlap=200
        )
    
    def generate_test_case(self, test_case_content: str, example_code_files: Optional[List[Dict]] = None) -> str:
        """Генерирует автоматизированный тест на основе ручного тест-кейса"""
        try:
            # Разбиваем контент на чанки
            chunks = self.text_splitter.split_text(test_case_content)
            
            # Анализируем существующие тесты
            test_analysis = {}
            analytics_data = {}
            
            if example_code_files and len(example_code_files) > 0:
                project_path = os.path.dirname(example_code_files[0].get("source", ""))
                if project_path:
                    analyzer = TestAnalyzer(project_path)
                    test_analysis = analyzer.analyze_tests()
                    analytics_data = analyzer.collect_analytics()
            
            # Формируем улучшенный промпт
            full_prompt = f"""
            ### Ручной тест-кейс:
            {test_case_content}
            
            ### Анализ существующих тестов:
            {json.dumps(test_analysis, indent=2, ensure_ascii=False)}
            
            ### Аналитические данные:
            {json.dumps(analytics_data, indent=2, ensure_ascii=False)}
            
            ### Важные требования:
            1. Ответ должен содержать полный Java-код теста
            2. Код должен быть оформлен в блоке ```java
            3. Должны быть включены все необходимые импорты
            4. Тест должен соответствовать описанию из тест-кейса
            5. Должны быть реализованы все шаги теста
            6. Стиль кода должен соответствовать существующим тестам
            7. Использовать тот же тестовый фреймворк, что и в существующих тестах
            8. Учитывать аналитические данные при генерации теста
            9. Использовать проверенные паттерны из существующих тестов
            10. Избегать нестабильных практик, выявленных в аналитике
            """
            
            # Генерируем тест
            return self.gigachat_client.generate_test(full_prompt)
            
        except Exception as e:
            logger.error(f"Ошибка при генерации теста: {e}")
            logger.exception("Подробности ошибки:")
            return ""

class TestCaseGeneratorApp:
    """Основной класс приложения"""
    
    def __init__(self):
        self.gigachat_client = GigaChatClient()
        self.test_generator = TestGenerator(self.gigachat_client)
    
    def process_github_example(self, repo_url: str, branch: str = "main", file_pattern: str = "*.java") -> Optional[List[Dict]]:
        """Обрабатывает пример кода из GitHub репозитория"""
        try:
            # Проверяем, что URL не пустой
            if not repo_url or repo_url.strip() == "":
                logger.warning("URL репозитория не указан, пропускаем обработку GitHub примера")
                return None
                
            # Клонируем репозиторий
            try:
                repo_path = self._clone_github_repo(repo_url, branch)
                logger.info(f"Репозиторий успешно клонирован в {repo_path}")
            except ValueError as e:
                logger.error(f"Ошибка при клонировании репозитория: {e}")
                print(f"\nОшибка при клонировании репозитория: {e}")
                print("Продолжаем работу без примера из GitHub.")
                return None
            
            # Извлекаем код из файлов
            try:
                code_files = self._extract_code_from_repo(repo_path, file_pattern)
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
    
    def _clone_github_repo(self, repo_url: str, branch: str = "main") -> str:
        """Клонирует репозиторий с GitHub во временную директорию"""
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
    
    def _extract_code_from_repo(self, repo_path: str, file_pattern: str = "*.java") -> List[Dict]:
        """Извлекает код из файлов в репозитории"""
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
    
    def select_file_dialog(self) -> str:
        """Открывает диалоговое окно для выбора файла"""
        root = tk.Tk()
        root.withdraw()  # Скрываем основное окно
        
        file_path = filedialog.askopenfilename(
            title="Выберите файл с тест-кейсом",
            filetypes=[
                ("Текстовые файлы", "*.txt"),
                ("PDF файлы", "*.pdf"),
                ("CSV файлы", "*.csv"),
                ("Все файлы", "*.*")
            ]
        )
        
        return file_path
    
    def interactive_mode(self) -> tuple:
        """Запускает интерактивный режим для выбора файла и указания ссылки на GitHub"""
        print("\n=== Генератор автоматизированных тест-кейсов ===")
        print("Этот инструмент поможет вам создать автоматизированные тест-кейсы на основе ручных тест-кейсов и примеров кода.")
        
        # Выбор файла с тест-кейсом
        print("\nШаг 1: Выберите файл с ручным тест-кейсом (PDF, TXT или CSV)")
        print("Откроется диалоговое окно для выбора файла...")
        
        test_case_path = self.select_file_dialog()
        
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
    
    def save_response(self, question: str, response: str, response_type: str = "general", language: str = "java") -> None:
        """Сохраняет ответ в структурированном формате"""
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
                
                code_filename = os.path.join(code_dir, f"{class_name}_{timestamp}.java")
                logger.info(f"Сохранение кода в файл: {code_filename}")
                
                with open(code_filename, 'w', encoding='utf-8') as f:
                    f.write(code)
                logger.info(f'Код успешно сохранен в файл: {code_filename}')
            
        except Exception as e:
            logger.error(f'Ошибка при сохранении ответа: {str(e)}')
            logger.exception("Подробности ошибки:")
            raise
    
    def run(self, args=None):
        """Запускает приложение"""
        parser = argparse.ArgumentParser(description="Генератор автоматизированных тест-кейсов")
        parser.add_argument("--test-case", "-t", help="Путь к файлу с ручным тест-кейсом (PDF, TXT или CSV)")
        parser.add_argument("--github", "-g", help="URL репозитория GitHub с примером кода")
        parser.add_argument("--branch", "-b", default="main", help="Ветка репозитория GitHub (по умолчанию: main)")
        parser.add_argument("--pattern", "-p", default="*.java", help="Шаблон для поиска файлов в репозитории (по умолчанию: *.java)")
        parser.add_argument("--interactive", "-i", action="store_true", help="Запуск в интерактивном режиме")
        
        args = parser.parse_args(args)
        
        # Если указан флаг интерактивного режима или не указаны обязательные параметры
        if args.interactive or (not args.test_case and not args.github):
            test_case_path, github_url, branch, file_pattern = self.interactive_mode()
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
                file_handler = FileHandlerFactory.create_handler(test_case_path)
                test_case_documents = file_handler.load_file(test_case_path)
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
                example_code_files = self.process_github_example(github_url, branch, file_pattern)
                
                if example_code_files:
                    print(f"Загружено {len(example_code_files)} файлов с примером кода")
                else:
                    print("Не удалось загрузить примеры из GitHub. Продолжаем работу без них.")
            
            # Генерируем автоматизированный тест
            question = f"Создай автоматизированный тест на основе ручного тест-кейса из файла {os.path.basename(test_case_path)}"
            print("\nЗадаю вопрос для создания автотеста:", question)
            
            try:
                response = self.test_generator.generate_test_case(test_case_content, example_code_files)
                
                if response:
                    self.save_response(question, response, "test_case")
                    print(f"\nАвтоматизированный тест успешно сгенерирован и сохранен в директорию 'responses/java/'")
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

def main():
    """Точка входа в приложение"""
    app = TestCaseGeneratorApp()
    app.run()

if __name__ == "__main__":
    main() 