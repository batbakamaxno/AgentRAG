from gigachat import GigaChat
import os
import logging
from datetime import datetime
from PyPDF2 import PdfReader
from typing import Dict, List, Optional, Any
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import DirectoryLoader, TextLoader
import json
import re
import csv
import pandas as pd
from collections import Counter

# Настройка логирования
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)

class EnhancedTestCaseGenerator:
    def __init__(self):
        try:
            # Улучшенная инициализация GigaChat с дополнительными параметрами
            self.gigachat = GigaChat(
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
        elif file_extension == '.csv':
            return self._load_csv_file(file_path)
        else:
            raise ValueError(f"Неподдерживаемый формат файла: {file_extension}")
    
    def _load_csv_file(self, file_path: str) -> str:
        """Загружает и обрабатывает CSV файл с тест-кейсами."""
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
            
            return "\n".join(test_cases)
        except Exception as e:
            logger.error(f"Ошибка при загрузке CSV файла: {e}")
            raise

    def split_text_into_chunks(self, text: str, chunk_size: int = 2000, chunk_overlap: int = 200) -> List[str]:
        """Разбивает текст на чанки для лучшей обработки."""
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap
        )
        return text_splitter.split_text(text)

    def analyze_existing_tests(self, project_path: str, file_pattern: str = "**/*.java") -> Dict:
        """Анализирует существующие тесты в проекте."""
        try:
            # Загружаем все Java файлы из проекта
            loader = DirectoryLoader(project_path, glob=file_pattern, loader_cls=TextLoader)
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
    
    def collect_analytics_data(self, project_path: str) -> Dict[str, Any]:
        """Собирает аналитические данные о проекте для улучшения генерации тестов."""
        try:
            analytics = {
                "test_coverage": self._analyze_test_coverage(project_path),
                "test_stability": self._analyze_test_stability(project_path),
                "test_patterns": self._analyze_test_patterns(project_path),
                "test_dependencies": self._analyze_test_dependencies(project_path)
            }
            return analytics
        except Exception as e:
            logger.error(f"Ошибка при сборе аналитических данных: {e}")
            return {}
    
    def _analyze_test_coverage(self, project_path: str) -> Dict[str, Any]:
        """Анализирует покрытие тестами кодовой базы."""
        # Здесь можно добавить интеграцию с инструментами анализа покрытия кода
        # Например, JaCoCo, Cobertura.
        return {
            "overall_coverage": 0.0,
            "class_coverage": {},
            "method_coverage": {},
            "line_coverage": {}
        }
    
    def _analyze_test_stability(self, project_path: str) -> Dict[str, Any]:
        """Анализирует стабильность тестов на основе истории запусков."""
        # Здесь можно добавить анализ истории запусков тестов
        # Например, из CI/CD систем или систем управления тестами (TestOps)
        return {
            "flaky_tests": [],
            "stable_tests": [],
            "test_execution_time": {}
        }
    
    def _analyze_test_patterns(self, project_path: str) -> Dict[str, Any]:
        """Анализирует паттерны в тестах для выявления лучших практик."""
        test_analysis = self.analyze_existing_tests(project_path)
        
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
    
    def _analyze_test_dependencies(self, project_path: str) -> Dict[str, Any]:
        """Анализирует зависимости между тестами и тестируемым кодом."""
        # Здесь можно добавить анализ зависимостей между тестами и тестируемым кодом
        # Например, с помощью инструментов статического анализа кода
        return {
            "test_dependencies": {},
            "code_dependencies": {},
            "shared_resources": []
        }

    def generate_test_case(self, test_case_content: str, example_code_files: Optional[List[Dict]] = None) -> str:
        """Генерирует автоматизированный тест на основе ручного тест-кейса."""
        try:
            # Разбиваем контент на чанки, если он слишком большой
            chunks = self.split_text_into_chunks(test_case_content)
            
            # Анализируем существующие тесты, если путь к проекту предоставлен
            test_analysis = {}
            analytics_data = {}
            
            if example_code_files and len(example_code_files) > 0:
                project_path = os.path.dirname(example_code_files[0].get("source", ""))
                if project_path:
                    test_analysis = self.analyze_existing_tests(project_path)
                    analytics_data = self.collect_analytics_data(project_path)
            
            # Формируем промпт с учетом анализа существующих тестов и аналитических данных
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
            
            logger.info("Отправка запроса к GigaChat")
            
            # Отправляем запрос к GigaChat
            response = self.gigachat.chat(full_prompt)
            
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

    def save_response(self, question: str, response: str, response_type: str = "general", language: str = "java"):
        """Сохраняет ответ в структурированном формате."""
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