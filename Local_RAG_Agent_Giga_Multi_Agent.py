from gigachat import GigaChat
import os
from dotenv import load_dotenv
import logging
import re
from datetime import datetime
from typing import Dict, List, Optional, Any
from PyPDF2 import PdfReader
import json
import asyncio
from dataclasses import dataclass, asdict
from enum import Enum
import concurrent.futures
from queue import Queue
import threading

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
DOCUMENTATION_ANALYZER_PROMPT = """### Роль: Аналитик документации
Ты - опытный аналитик, который анализирует документацию и преобразует её в структурированный формат для создания тест-кейсов.

### Задача
1. Проанализируй предоставленную документацию
2. Выдели ключевые компоненты системы
3. Определи основные функции и их параметры
4. Выдели критические пути и сценарии использования
5. Определи граничные условия и особые случаи

### Формат ответа (JSON)
{
    "system_description": {
        "components": [],
        "architecture": "",
        "tech_stack": []
    },
    "functional_requirements": [
        {
            "name": "",
            "description": "",
            "parameters": [],
            "constraints": []
        }
    ],
    "critical_paths": [
        {
            "name": "",
            "description": "",
            "steps": [],
            "edge_cases": []
        }
    ],
    "recommendations": {
        "priority_areas": [],
        "complex_scenarios": [],
        "risks": []
    }
}

### Важно
- Ответ должен быть в формате JSON
- Все поля должны быть заполнены
- Используйте пустые массивы [] или строки "" для отсутствующих данных
"""

TEST_CASE_CREATOR_PROMPT = """### Роль: Создатель ручных тест-кейсов
Ты - опытный тестировщик, который создает детальные ручные тест-кейсы на основе анализа документации.

### Задача
1. Изучи анализ документации
2. Создай структурированные ручные тест-кейсы
3. Обеспечь полное покрытие функциональности
4. Включи позитивные и негативные сценарии

### Формат ответа (JSON)
[
    {
        "id": "TC_001",
        "name": "",
        "priority": "High/Medium/Low",
        "prerequisites": [],
        "steps": [],
        "expected_result": "",
        "actual_result": null,
        "status": "Not Executed"
    }
]

### Требования к тест-кейсам
- Уникальность идентификаторов
- Четкое описание шагов
- Измеримые результаты
- Покрытие граничных случаев

### Важно
- Ответ должен быть в формате JSON
- Все обязательные поля должны быть заполнены
- Используйте null для отсутствующих данных
"""

AUTOMATION_ENGINEER_PROMPT = """### Роль: Инженер по автоматизации
Ты - опытный разработчик автоматизированных тестов, который создает автотесты на основе ручных тест-кейсов.

### Задача
1. Изучи ручные тест-кейсы
2. Создай автоматизированные тесты на Java
3. Используй JUnit и необходимые фреймворки
4. Реализуй все проверки из ручных тест-кейсов

### Формат ответа (JSON)
[
    {
        "id": "AT_001",
        "name": "",
        "class_name": "",
        "imports": [],
        "setup_methods": [],
        "test_methods": [],
        "teardown_methods": []
    }
]

### Требования к автотестам
- Чистый и поддерживаемый код
- Изолированность тестов
- Корректная обработка ошибок
- Логирование результатов

### Важно
- Ответ должен быть в формате JSON
- Все обязательные поля должны быть заполнены
- Используйте пустые массивы [] для отсутствующих методов
"""

class AgentStatus(Enum):
    IDLE = "idle"
    WORKING = "working"
    COMPLETED = "completed"
    ERROR = "error"

    def __str__(self):
        return self.value

class CustomJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, AgentStatus):
            return obj.value
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)

@dataclass
class DocumentationAnalysis:
    system_description: Dict[str, Any]
    functional_requirements: List[Dict[str, Any]]
    critical_paths: List[Dict[str, Any]]
    recommendations: Dict[str, Any]
    status: AgentStatus = AgentStatus.IDLE
    error: Optional[str] = None

    def to_dict(self):
        return {
            'system_description': self.system_description,
            'functional_requirements': self.functional_requirements,
            'critical_paths': self.critical_paths,
            'recommendations': self.recommendations,
            'status': str(self.status),
            'error': self.error
        }

@dataclass
class ManualTestCase:
    id: str
    name: str
    priority: str
    prerequisites: List[str]
    steps: List[str]
    expected_result: str
    actual_result: Optional[str] = None
    status: str = "Not Executed"
    automation_status: AgentStatus = AgentStatus.IDLE
    error: Optional[str] = None

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'priority': self.priority,
            'prerequisites': self.prerequisites,
            'steps': self.steps,
            'expected_result': self.expected_result,
            'actual_result': self.actual_result,
            'status': self.status,
            'automation_status': str(self.automation_status),
            'error': self.error
        }

@dataclass
class AutomatedTest:
    id: str
    name: str
    class_name: str
    imports: List[str]
    setup_methods: List[str]
    test_methods: List[str]
    teardown_methods: List[str]
    status: AgentStatus = AgentStatus.IDLE
    error: Optional[str] = None

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'class_name': self.class_name,
            'imports': self.imports,
            'setup_methods': self.setup_methods,
            'test_methods': self.test_methods,
            'teardown_methods': self.teardown_methods,
            'status': str(self.status),
            'error': self.error
        }

class AgentCommunication:
    def __init__(self):
        self.analysis_queue = Queue()
        self.test_cases_queue = Queue()
        self.automation_queue = Queue()
        self.feedback_queue = Queue()
        self.lock = threading.Lock()

    def send_analysis(self, analysis: DocumentationAnalysis):
        self.analysis_queue.put(analysis)

    def send_test_cases(self, test_cases: List[ManualTestCase]):
        self.test_cases_queue.put(test_cases)

    def send_automated_tests(self, tests: List[AutomatedTest]):
        self.automation_queue.put(tests)

    def send_feedback(self, source: str, target: str, data: Any):
        self.feedback_queue.put({
            "source": source,
            "target": target,
            "data": data
        })

    def get_feedback(self) -> Optional[Dict]:
        try:
            return self.feedback_queue.get_nowait()
        except:
            return None

class AgentValidator:
    @staticmethod
    def validate_analysis(analysis: DocumentationAnalysis) -> bool:
        required_fields = ['system_description', 'functional_requirements', 'critical_paths', 'recommendations']
        return all(hasattr(analysis, field) for field in required_fields)

    @staticmethod
    def validate_test_case(test_case: ManualTestCase) -> bool:
        required_fields = ['id', 'name', 'priority', 'prerequisites', 'steps', 'expected_result']
        return all(hasattr(test_case, field) for field in required_fields)

    @staticmethod
    def validate_automated_test(test: AutomatedTest) -> bool:
        required_fields = ['id', 'name', 'class_name', 'imports', 'test_methods']
        return all(hasattr(test, field) for field in required_fields)

class MultiAgentTestCaseGenerator:
    def __init__(self):
        try:
            self.gigachat = GigaChat(
                credentials=os.getenv("GIGACHAT_CREDENTIALS"),
                verify_ssl_certs=False
            )
            self.communication = AgentCommunication()
            self.validator = AgentValidator()
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

    def parse_text_to_json(self, text: str) -> dict:
        """Преобразует текстовый ответ в JSON формат."""
        try:
            # Удаляем markdown-блоки
            text = re.sub(r'```json\s*|\s*```', '', text)
            
            # Ищем JSON в тексте
            json_match = re.search(r'\{[\s\S]*\}', text)
            if json_match:
                try:
                    json_data = json.loads(json_match.group())
                    # Проверяем наличие обязательных полей
                    required_fields = ['system_description', 'functional_requirements', 'critical_paths', 'recommendations']
                    if all(field in json_data for field in required_fields):
                        return json_data
                except json.JSONDecodeError:
                    pass
            
            # Если JSON не найден или невалиден, создаем структурированный ответ
            return {
                "system_description": {
                    "components": [],
                    "architecture": "",
                    "tech_stack": []
                },
                "functional_requirements": [
                    {
                        "name": "Default Requirement",
                        "description": "Default description",
                        "parameters": [],
                        "constraints": []
                    }
                ],
                "critical_paths": [
                    {
                        "name": "Default Path",
                        "description": "Default description",
                        "steps": [],
                        "edge_cases": []
                    }
                ],
                "recommendations": {
                    "priority_areas": [],
                    "complex_scenarios": [],
                    "risks": []
                }
            }
        except Exception as e:
            logger.error(f"Ошибка при парсинге текста в JSON: {e}")
            return {
                "system_description": {
                    "components": [],
                    "architecture": "",
                    "tech_stack": []
                },
                "functional_requirements": [],
                "critical_paths": [],
                "recommendations": {
                    "priority_areas": [],
                    "complex_scenarios": [],
                    "risks": []
                }
            }

    async def documentation_analyzer_phase(self, doc_content: str) -> DocumentationAnalysis:
        """Фаза анализа документации."""
        try:
            full_prompt = f"{DOCUMENTATION_ANALYZER_PROMPT}\n\n### Документация:\n{doc_content}"
            response = self.gigachat.chat(full_prompt)
            
            if response and hasattr(response, 'choices') and response.choices:
                content = response.choices[0].message.content
                try:
                    # Преобразуем текстовый ответ в JSON
                    analysis_data = self.parse_text_to_json(content)
                    
                    # Создаем объект анализа
                    analysis = DocumentationAnalysis(
                        system_description=analysis_data.get('system_description', {}),
                        functional_requirements=analysis_data.get('functional_requirements', []),
                        critical_paths=analysis_data.get('critical_paths', []),
                        recommendations=analysis_data.get('recommendations', {})
                    )
                    
                    if self.validator.validate_analysis(analysis):
                        analysis.status = AgentStatus.COMPLETED
                        return analysis
                    else:
                        analysis.status = AgentStatus.ERROR
                        analysis.error = "Validation failed"
                        return analysis
                except Exception as e:
                    logger.error(f"Error processing response: {e}")
                    logger.error(f"Raw content: {content}")
                    return DocumentationAnalysis(
                        system_description={},
                        functional_requirements=[],
                        critical_paths=[],
                        recommendations={},
                        status=AgentStatus.ERROR,
                        error=f"Failed to process response: {str(e)}"
                    )
            else:
                return DocumentationAnalysis(
                    system_description={},
                    functional_requirements=[],
                    critical_paths=[],
                    recommendations={},
                    status=AgentStatus.ERROR,
                    error="No response from GigaChat"
                )
                
        except Exception as e:
            return DocumentationAnalysis(
                system_description={},
                functional_requirements=[],
                critical_paths=[],
                recommendations={},
                status=AgentStatus.ERROR,
                error=str(e)
            )

    async def test_case_creator_phase(self, analysis: DocumentationAnalysis) -> List[ManualTestCase]:
        """Фаза создания ручных тест-кейсов."""
        try:
            if analysis.status != AgentStatus.COMPLETED:
                return []

            full_prompt = f"{TEST_CASE_CREATOR_PROMPT}\n\n### Анализ документации:\n{json.dumps(analysis.to_dict())}"
            response = self.gigachat.chat(full_prompt)
            
            if response and hasattr(response, 'choices') and response.choices:
                content = response.choices[0].message.content
                try:
                    # Ищем JSON в тексте
                    json_match = re.search(r'\[[\s\S]*\]|\{[\s\S]*\}', content)
                    if json_match:
                        json_str = json_match.group()
                        # Очищаем JSON от возможных markdown-блоков
                        json_str = re.sub(r'```json\s*|\s*```', '', json_str)
                        test_cases_data = json.loads(json_str)
                        
                        # Если получили один тест-кейс, преобразуем его в список
                        if isinstance(test_cases_data, dict):
                            test_cases_data = [test_cases_data]
                            
                        test_cases = [ManualTestCase(**case) for case in test_cases_data]
                        valid_cases = [case for case in test_cases if self.validator.validate_test_case(case)]
                        for case in valid_cases:
                            case.status = "Created"
                        return valid_cases
                    else:
                        logger.error("JSON не найден в ответе")
                        logger.error(f"Raw content: {content}")
                        return []
                except json.JSONDecodeError as e:
                    logger.error(f"JSON parsing error: {e}")
                    logger.error(f"Raw content: {content}")
                    return []
            return []
                
        except Exception as e:
            logger.error(f"Error in test case creation: {e}")
            return []

    async def automation_engineer_phase(self, test_cases: List[ManualTestCase]) -> List[AutomatedTest]:
        """Фаза создания автоматизированных тестов."""
        try:
            if not test_cases:
                return []

            full_prompt = f"{AUTOMATION_ENGINEER_PROMPT}\n\n### Ручные тест-кейсы:\n{json.dumps([case.to_dict() for case in test_cases])}"
            response = self.gigachat.chat(full_prompt)
            
            if response and hasattr(response, 'choices') and response.choices:
                content = response.choices[0].message.content
                try:
                    # Очищаем ответ от возможных markdown-блоков
                    content = re.sub(r'```json\s*|\s*```', '', content)
                    tests_data = json.loads(content)
                    tests = [AutomatedTest(**test) for test in tests_data]
                    valid_tests = [test for test in tests if self.validator.validate_automated_test(test)]
                    for test in valid_tests:
                        test.status = AgentStatus.COMPLETED
                    return valid_tests
                except json.JSONDecodeError as e:
                    logger.error(f"JSON parsing error: {e}")
                    logger.error(f"Raw content: {content}")
                    return []
            return []
                
        except Exception as e:
            logger.error(f"Error in automation phase: {e}")
            return []

    def save_results(self, doc_name: str, analysis: DocumentationAnalysis, 
                    test_cases: List[ManualTestCase], automated_tests: List[AutomatedTest]):
        """Сохраняет результаты работы всех агентов."""
        try:
            # Создаем директории для результатов
            results_dir = os.path.abspath('test_results')
            manual_dir = os.path.join(results_dir, 'manual')
            automated_dir = os.path.join(results_dir, 'automated')
            
            for dir_path in [results_dir, manual_dir, automated_dir]:
                if not os.path.exists(dir_path):
                    os.makedirs(dir_path)
                    logger.info(f'Создана директория {dir_path}/')
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # Сохраняем анализ документации
            analysis_filename = os.path.join(results_dir, f"doc_analysis_{os.path.splitext(doc_name)[0]}_{timestamp}.json")
            with open(analysis_filename, 'w', encoding='utf-8') as f:
                json.dump(analysis.to_dict(), f, indent=2)
            logger.info(f'Анализ документации сохранен в: {analysis_filename}')
            
            # Сохраняем ручные тест-кейсы в MD формате
            manual_filename = os.path.join(manual_dir, f"manual_test_cases_{os.path.splitext(doc_name)[0]}_{timestamp}.md")
            with open(manual_filename, 'w', encoding='utf-8') as f:
                f.write(f"# Ручные тест-кейсы\n\n")
                f.write(f"## Документ: {doc_name}\n")
                f.write(f"## Дата создания: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                
                for case in test_cases:
                    f.write(f"### Тест-кейс {case.id}\n\n")
                    f.write(f"**Название:** {case.name}\n")
                    f.write(f"**Приоритет:** {case.priority}\n")
                    f.write(f"**Статус:** {case.status}\n\n")
                    
                    f.write("**Предусловия:**\n")
                    for prereq in case.prerequisites:
                        f.write(f"- {prereq}\n")
                    f.write("\n")
                    
                    f.write("**Шаги:**\n")
                    for i, step in enumerate(case.steps, 1):
                        f.write(f"{i}. {step}\n")
                    f.write("\n")
                    
                    f.write(f"**Ожидаемый результат:**\n{case.expected_result}\n\n")
                    if case.actual_result:
                        f.write(f"**Фактический результат:**\n{case.actual_result}\n\n")
                    
                    f.write("---\n\n")
            
            logger.info(f'Ручные тест-кейсы сохранены в: {manual_filename}')
            
            # Сохраняем автоматизированные тесты в Java формате
            for test in automated_tests:
                test_filename = os.path.join(automated_dir, f"{test.class_name}_{timestamp}.java")
                with open(test_filename, 'w', encoding='utf-8') as f:
                    # Импорты
                    f.write("import org.junit.jupiter.api.*;\n")
                    f.write("import static org.junit.jupiter.api.Assertions.*;\n")
                    for imp in test.imports:
                        f.write(f"import {imp};\n")
                    f.write("\n")
                    
                    # Класс теста
                    f.write(f"public class {test.class_name} {{\n\n")
                    
                    # Методы настройки
                    for setup in test.setup_methods:
                        f.write(f"    @BeforeEach\n")
                        f.write(f"    void {setup}() {{\n")
                        f.write(f"        // TODO: Implement setup\n")
                        f.write(f"    }}\n\n")
                    
                    # Тестовые методы
                    for test_method in test.test_methods:
                        f.write(f"    @Test\n")
                        f.write(f"    void {test_method}() {{\n")
                        f.write(f"        // TODO: Implement test\n")
                        f.write(f"    }}\n\n")
                    
                    # Методы очистки
                    for teardown in test.teardown_methods:
                        f.write(f"    @AfterEach\n")
                        f.write(f"    void {teardown}() {{\n")
                        f.write(f"        // TODO: Implement teardown\n")
                        f.write(f"    }}\n\n")
                    
                    f.write("}\n")
                logger.info(f'Автоматизированный тест сохранен в: {test_filename}')
            
        except Exception as e:
            logger.error(f'Ошибка при сохранении результатов: {str(e)}')
            raise

    async def process_feedback(self):
        """Обработка обратной связи между агентами."""
        while True:
            feedback = self.communication.get_feedback()
            if feedback:
                logger.info(f"Получена обратная связь от {feedback['source']} к {feedback['target']}")
                # Здесь можно добавить логику обработки обратной связи
            await asyncio.sleep(0.1)

    async def generate_test_cases(self, doc_path: str):
        """Основной метод генерации тест-кейсов с использованием мультиагентного подхода."""
        try:
            doc_name = os.path.basename(doc_path)
            doc_content = self.load_file(doc_path)
            
            # Запускаем обработку обратной связи
            feedback_task = asyncio.create_task(self.process_feedback())
            
            # Фаза 1: Анализ документации
            logger.info("Начало фазы анализа документации")
            analysis = await self.documentation_analyzer_phase(doc_content)
            if analysis.status != AgentStatus.COMPLETED:
                logger.error(f"Не удалось проанализировать документацию: {analysis.error}")
                return
            
            # Фаза 2: Создание ручных тест-кейсов
            logger.info("Начало фазы создания ручных тест-кейсов")
            test_cases = await self.test_case_creator_phase(analysis)
            if not test_cases:
                logger.error("Не удалось создать ручные тест-кейсы")
                return
            
            # Фаза 3: Создание автоматизированных тестов
            logger.info("Начало фазы создания автоматизированных тестов")
            automated_tests = await self.automation_engineer_phase(test_cases)
            if not automated_tests:
                logger.error("Не удалось создать автоматизированные тесты")
                return
            
            # Сохранение результатов
            self.save_results(doc_name, analysis, test_cases, automated_tests)
            
            # Отменяем задачу обработки обратной связи
            feedback_task.cancel()
            
        except Exception as e:
            logger.error(f"Ошибка при генерации тест-кейсов: {e}")
            logger.exception("Подробности ошибки:")

async def main():
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
        generator = MultiAgentTestCaseGenerator()
        
        # Обрабатываем каждый файл
        tasks = []
        for doc_file in doc_files:
            full_path = os.path.join(docs_dir, doc_file)
            logger.info(f"Обрабатываю файл: {full_path}")
            tasks.append(generator.generate_test_cases(full_path))
        
        # Запускаем все задачи параллельно
        await asyncio.gather(*tasks)

    except Exception as e:
        logger.error(f"Ошибка при создании тест-кейсов: {e}")
        logger.exception("Подробности ошибки:")

if __name__ == "__main__":
    asyncio.run(main()) 