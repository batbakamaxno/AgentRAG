from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage, SystemMessage
import logging
import os
from dotenv import load_dotenv
from datetime import datetime
from PyPDF2 import PdfReader
from typing import Dict, List, Optional, Any
import json
import re
import asyncio
from dataclasses import dataclass, asdict
from enum import Enum

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

# Промпты для агентов
DOCUMENTATION_ANALYZER_PROMPT = """### Роль: Аналитик документации
Ты - опытный аналитик, который анализирует документацию и создает структурированный анализ для тестирования.

### Задача
1. Проанализируй предоставленную документацию
2. Выдели ключевые компоненты системы
3. Определи функциональные требования
4. Выдели критические пути
5. Сформулируй рекомендации по тестированию

### Формат ответа (Markdown)
# Анализ документации

## Описание системы
- Компоненты:
  - Компонент 1
  - Компонент 2
- Архитектура: описание архитектуры
- Технологический стек:
  - Технология 1
  - Технология 2

## Функциональные требования
1. Требование 1
   - Описание: детальное описание
   - Параметры:
     - Параметр 1
     - Параметр 2
   - Ограничения:
     - Ограничение 1
     - Ограничение 2

2. Требование 2
   ...

## Критические пути
1. Путь 1
   - Описание: описание пути
   - Шаги:
     1. Шаг 1
     2. Шаг 2
   - Граничные случаи:
     - Случай 1
     - Случай 2

2. Путь 2
   ...

## Рекомендации по тестированию
### Приоритетные области
- Область 1
- Область 2

### Сложные сценарии
- Сценарий 1
- Сценарий 2

### Риски
- Риск 1
- Риск 2"""

TEST_CASE_CREATOR_PROMPT = """### Роль: Создатель тест-кейсов
Ты - опытный тестировщик, который создает ручные тест-кейсы на основе анализа документации.

### Задача
1. Изучи анализ документации
2. Создай ручные тест-кейсы для каждого функционального требования
3. Убедись в полноте покрытия
4. Проверь соответствие требованиям

### Формат ответа (Markdown)
# Ручные тест-кейсы

## Тест-кейс TC001
**Название:** Название тест-кейса
**Приоритет:** Высокий/Средний/Низкий
**Предусловия:**
- Условие 1
- Условие 2

**Шаги:**
1. Шаг 1
2. Шаг 2
3. Шаг 3

**Ожидаемый результат:**
Описание ожидаемого результата

**Фактический результат:**
Не выполнен

**Статус:** Не выполнен
**Статус автоматизации:** Не начат

## Тест-кейс TC002
..."""

AUTOMATION_ENGINEER_PROMPT = """### Роль: Инженер по автоматизации
Ты - опытный разработчик автоматизированных тестов на Java. Твоя задача - создать автоматизированные тесты на основе ручных тест-кейсов.

### Задача
1. Изучи ручные тест-кейсы
2. Создай автоматизированные тесты на Java с использованием JUnit
3. Реализуй все необходимые проверки
4. Добавь обработку ошибок

### Важно
- Возвращай ТОЛЬКО код Java
- Используй JUnit 5
- Добавь все необходимые импорты
- Реализуй методы setUp и tearDown
- Добавь комментарии к методам

### Формат ответа
```java
import org.junit.jupiter.api.*;
import static org.junit.jupiter.api.Assertions.*;

public class TestClassName {
    @BeforeEach
    void setUp() {
        // Инициализация тестового окружения
    }

    @Test
    void testScenario1() {
        // Реализация теста
    }

    @AfterEach
    void tearDown() {
        // Очистка после теста
    }
}
```"""

class AgentStatus(Enum):
    IDLE = "idle"
    WORKING = "working"
    COMPLETED = "completed"
    ERROR = "error"

    def __str__(self):
        return self.value

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

class AgentValidator:
    def validate_analysis(self, analysis: DocumentationAnalysis) -> bool:
        """Проверяет корректность анализа документации."""
        required_fields = ['system_description', 'functional_requirements', 'critical_paths', 'recommendations']
        return all(hasattr(analysis, field) for field in required_fields)

    def validate_test_case(self, test_case: ManualTestCase) -> bool:
        """Проверяет корректность тест-кейса."""
        required_fields = ['id', 'name', 'priority', 'prerequisites', 'steps', 'expected_result']
        return all(hasattr(test_case, field) for field in required_fields)

    def validate_automated_test(self, test: AutomatedTest) -> bool:
        """Проверяет корректность автоматизированного теста."""
        required_fields = ['id', 'name', 'class_name', 'imports', 'setup_methods', 'test_methods', 'teardown_methods']
        return all(hasattr(test, field) for field in required_fields)

class MultiAgentTestCaseGenerator:
    def __init__(self):
        try:
            self.llm = ChatOllama(
                model="llama2:7b",
                temperature=0,
                verbose=True
            )
            self.validator = AgentValidator()
            logger.info("Llama успешно инициализирована")
        except Exception as e:
            logger.error(f"Ошибка при инициализации Llama: {e}")
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

    def parse_markdown_to_dict(self, text: str) -> dict:
        """Преобразует Markdown текст в структурированный словарь."""
        try:
            # Удаляем markdown-блоки
            text = re.sub(r'```markdown\s*|\s*```', '', text)
            
            # Извлекаем компоненты
            components = re.findall(r'Компоненты:\s*(.*?)(?=\n\n|\Z)', text, re.DOTALL)
            components = [c.strip('- ').strip() for c in components[0].split('\n') if c.strip()] if components else []
            
            # Извлекаем архитектуру
            architecture = re.search(r'Архитектура:\s*(.*?)(?=\n\n|\Z)', text)
            architecture = architecture.group(1).strip() if architecture else ""
            
            # Извлекаем технологический стек
            tech_stack = re.findall(r'Технологический стек:\s*(.*?)(?=\n\n|\Z)', text, re.DOTALL)
            tech_stack = [t.strip('- ').strip() for t in tech_stack[0].split('\n') if t.strip()] if tech_stack else []
            
            # Извлекаем функциональные требования
            requirements = []
            req_blocks = re.finditer(r'(\d+)\.\s*(.*?)(?=\n\n|\Z)', text, re.DOTALL)
            for block in req_blocks:
                req_text = block.group(2)
                name = re.search(r'^(.*?)(?=\n|$)', req_text).group(1).strip()
                description = re.search(r'Описание:\s*(.*?)(?=\n|$)', req_text)
                description = description.group(1).strip() if description else ""
                
                params = re.findall(r'Параметры:\s*(.*?)(?=\n\n|\Z)', req_text, re.DOTALL)
                params = [p.strip('- ').strip() for p in params[0].split('\n') if p.strip()] if params else []
                
                constraints = re.findall(r'Ограничения:\s*(.*?)(?=\n\n|\Z)', req_text, re.DOTALL)
                constraints = [c.strip('- ').strip() for c in constraints[0].split('\n') if c.strip()] if constraints else []
                
                requirements.append({
                    "name": name,
                    "description": description,
                    "parameters": params,
                    "constraints": constraints
                })
            
            # Извлекаем критические пути
            paths = []
            path_blocks = re.finditer(r'(\d+)\.\s*(.*?)(?=\n\n|\Z)', text, re.DOTALL)
            for block in path_blocks:
                path_text = block.group(2)
                name = re.search(r'^(.*?)(?=\n|$)', path_text).group(1).strip()
                description = re.search(r'Описание:\s*(.*?)(?=\n|$)', path_text)
                description = description.group(1).strip() if description else ""
                
                steps = re.findall(r'Шаги:\s*(.*?)(?=\n\n|\Z)', path_text, re.DOTALL)
                steps = [s.strip().lstrip('1234567890. ') for s in steps[0].split('\n') if s.strip()] if steps else []
                
                edge_cases = re.findall(r'Граничные случаи:\s*(.*?)(?=\n\n|\Z)', path_text, re.DOTALL)
                edge_cases = [c.strip('- ').strip() for c in edge_cases[0].split('\n') if c.strip()] if edge_cases else []
                
                paths.append({
                    "name": name,
                    "description": description,
                    "steps": steps,
                    "edge_cases": edge_cases
                })
            
            # Извлекаем рекомендации
            priority_areas = re.findall(r'Приоритетные области:\s*(.*?)(?=\n\n|\Z)', text, re.DOTALL)
            priority_areas = [a.strip('- ').strip() for a in priority_areas[0].split('\n') if a.strip()] if priority_areas else []
            
            complex_scenarios = re.findall(r'Сложные сценарии:\s*(.*?)(?=\n\n|\Z)', text, re.DOTALL)
            complex_scenarios = [s.strip('- ').strip() for s in complex_scenarios[0].split('\n') if s.strip()] if complex_scenarios else []
            
            risks = re.findall(r'Риски:\s*(.*?)(?=\n\n|\Z)', text, re.DOTALL)
            risks = [r.strip('- ').strip() for r in risks[0].split('\n') if r.strip()] if risks else []
            
            return {
                "system_description": {
                    "components": components,
                    "architecture": architecture,
                    "tech_stack": tech_stack
                },
                "functional_requirements": requirements,
                "critical_paths": paths,
                "recommendations": {
                    "priority_areas": priority_areas,
                    "complex_scenarios": complex_scenarios,
                    "risks": risks
                }
            }
        except Exception as e:
            logger.error(f"Ошибка при парсинге Markdown: {e}")
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
            response = self.llm.invoke([
                SystemMessage(content="Ты - эксперт по анализу документации. Создай структурированный анализ в формате Markdown."),
                HumanMessage(content=full_prompt)
            ])
            
            if response:
                content = response.content
                try:
                    # Преобразуем Markdown в структурированный словарь
                    analysis_data = self.parse_markdown_to_dict(content)
                    
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
                    error="No response from Llama"
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

    def parse_test_cases_from_markdown(self, text: str) -> List[ManualTestCase]:
        """Преобразует Markdown текст с тест-кейсами в список объектов ManualTestCase."""
        try:
            # Удаляем markdown-блоки
            text = re.sub(r'```markdown\s*|\s*```', '', text)
            
            test_cases = []
            # Ищем блоки тест-кейсов
            test_case_blocks = re.finditer(r'\*\*Test Case (TC\d+): (.*?)\*\*\n(.*?)(?=\n\*\*Test Case|\Z)', text, re.DOTALL)
            
            for block in test_case_blocks:
                tc_id = block.group(1)
                tc_name = block.group(2)
                tc_content = block.group(3)
                
                # Извлекаем предусловия
                prerequisites = []
                prereq_match = re.search(r'\* Preconditions:(.*?)(?=\n\* Steps:|$)', tc_content, re.DOTALL)
                if prereq_match:
                    prereq_text = prereq_match.group(1)
                    prerequisites = [p.strip('+ ').strip() for p in prereq_text.split('\n') if p.strip()]
                
                # Извлекаем шаги
                steps = []
                steps_match = re.search(r'\* Steps:(.*?)(?=\n\* Expected result:|$)', tc_content, re.DOTALL)
                if steps_match:
                    steps_text = steps_match.group(1)
                    steps = [s.strip().lstrip('1234567890. ') for s in steps_text.split('\n') if s.strip()]
                
                # Извлекаем ожидаемый результат
                expected_result = ""
                expected_match = re.search(r'\* Expected result: (.*?)(?=\n\* Actual result:|$)', tc_content, re.DOTALL)
                if expected_match:
                    expected_result = expected_match.group(1).strip()
                
                # Создаем объект тест-кейса
                test_case = ManualTestCase(
                    id=tc_id,
                    name=tc_name,
                    priority="Средний",  # По умолчанию средний приоритет
                    prerequisites=prerequisites,
                    steps=steps,
                    expected_result=expected_result,
                    actual_result=None,
                    status="Не выполнен",
                    automation_status=AgentStatus.IDLE
                )
                
                test_cases.append(test_case)
                logger.info(f"Создан тест-кейс: {test_case.id} - {test_case.name}")
            
            return test_cases
        except Exception as e:
            logger.error(f"Ошибка при парсинге тест-кейсов из Markdown: {e}")
            logger.error(f"Исходный текст: {text[:200]}...")  # Логируем начало текста
            return []

    async def test_case_creator_phase(self, analysis: DocumentationAnalysis) -> List[ManualTestCase]:
        """Фаза создания ручных тест-кейсов."""
        try:
            if analysis.status != AgentStatus.COMPLETED:
                logger.error("Анализ документации не завершен успешно")
                return []

            # Формируем промпт с анализом документации
            analysis_text = f"""
# Анализ документации

## Функциональные требования
{json.dumps(analysis.functional_requirements, ensure_ascii=False, indent=2)}

## Критические пути
{json.dumps(analysis.critical_paths, ensure_ascii=False, indent=2)}

## Рекомендации
{json.dumps(analysis.recommendations, ensure_ascii=False, indent=2)}
"""
            
            full_prompt = f"{TEST_CASE_CREATOR_PROMPT}\n\n### Анализ документации:\n{analysis_text}"
            
            logger.info("Отправка запроса к Llama для создания тест-кейсов")
            response = self.llm.invoke([
                SystemMessage(content="Ты - эксперт по созданию тест-кейсов. Создай ручные тест-кейсы в формате Markdown на основе предоставленного анализа документации."),
                HumanMessage(content=full_prompt)
            ])
            
            if response:
                content = response.content
                logger.info(f"Получен ответ от Llama: {content[:200]}...")  # Логируем начало ответа
                
                try:
                    # Преобразуем Markdown в список тест-кейсов
                    test_cases = self.parse_test_cases_from_markdown(content)
                    logger.info(f"Извлечено {len(test_cases)} тест-кейсов из ответа")
                    
                    if not test_cases:
                        logger.error("Не удалось извлечь тест-кейсы из ответа")
                        logger.error(f"Содержимое ответа: {content}")
                        return []
                    
                    # Проверяем валидность тест-кейсов
                    valid_cases = [case for case in test_cases if self.validator.validate_test_case(case)]
                    logger.info(f"Валидных тест-кейсов: {len(valid_cases)}")
                    
                    for case in valid_cases:
                        case.status = "Создан"
                    
                    return valid_cases
                except Exception as e:
                    logger.error(f"Ошибка при обработке ответа: {e}")
                    logger.error(f"Содержимое ответа: {content}")
                    return []
            else:
                logger.error("Не получен ответ от Llama")
                return []
                
        except Exception as e:
            logger.error(f"Ошибка в создании тест-кейсов: {e}")
            logger.exception("Подробности ошибки:")
            return []

    async def automation_engineer_phase(self, test_cases: List[ManualTestCase]) -> List[AutomatedTest]:
        """Фаза создания автоматизированных тестов."""
        try:
            if not test_cases:
                return []

            full_prompt = f"{AUTOMATION_ENGINEER_PROMPT}\n\n### Ручные тест-кейсы:\n{json.dumps([case.to_dict() for case in test_cases])}"
            response = self.llm.invoke([
                SystemMessage(content="Ты - эксперт по автоматизации тестирования. Создай автотесты на Java."),
                HumanMessage(content=full_prompt)
            ])
            
            if response:
                content = response.content
                try:
                    # Ищем Java код в тексте
                    java_match = re.search(r'```java\n(.*?)\n```', content, re.DOTALL)
                    if java_match:
                        java_code = java_match.group(1)
                        
                        # Извлекаем информацию из Java кода
                        class_name_match = re.search(r'public class (\w+)', java_code)
                        imports_match = re.findall(r'import (.*?);', java_code)
                        setup_methods = re.findall(r'@BeforeEach\s+void\s+(\w+)', java_code)
                        test_methods = re.findall(r'@Test\s+void\s+(\w+)', java_code)
                        teardown_methods = re.findall(r'@AfterEach\s+void\s+(\w+)', java_code)
                        
                        # Создаем объект автоматизированного теста
                        test = AutomatedTest(
                            id=f"AT{len(test_cases)}",
                            name=test_cases[0].name if test_cases else "Default Test",
                            class_name=class_name_match.group(1) if class_name_match else "DefaultTest",
                            imports=imports_match,
                            setup_methods=setup_methods,
                            test_methods=test_methods,
                            teardown_methods=teardown_methods
                        )
                        
                        if self.validator.validate_automated_test(test):
                            test.status = AgentStatus.COMPLETED
                            return [test]
                        else:
                            test.status = AgentStatus.ERROR
                            test.error = "Validation failed"
                            return [test]
                    else:
                        logger.error("Java код не найден в ответе")
                        logger.error(f"Raw content: {content}")
                        return []
                except Exception as e:
                    logger.error(f"Error processing Java code: {e}")
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
            
            # Сохраняем анализ документации в MD формате
            analysis_filename = os.path.join(results_dir, f"doc_analysis_{os.path.splitext(doc_name)[0]}_{timestamp}.md")
            with open(analysis_filename, 'w', encoding='utf-8') as f:
                f.write(f"# Анализ документации\n\n")
                f.write(f"## Документ: {doc_name}\n")
                f.write(f"## Дата создания: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                
                # Описание системы
                f.write("## Описание системы\n")
                f.write("### Компоненты\n")
                for component in analysis.system_description.get('components', []):
                    f.write(f"- {component}\n")
                f.write("\n")
                
                f.write("### Архитектура\n")
                f.write(f"{analysis.system_description.get('architecture', '')}\n\n")
                
                f.write("### Технологический стек\n")
                for tech in analysis.system_description.get('tech_stack', []):
                    f.write(f"- {tech}\n")
                f.write("\n")
                
                # Функциональные требования
                f.write("## Функциональные требования\n")
                for i, req in enumerate(analysis.functional_requirements, 1):
                    f.write(f"{i}. {req.get('name', '')}\n")
                    f.write(f"   - Описание: {req.get('description', '')}\n")
                    if req.get('parameters'):
                        f.write("   - Параметры:\n")
                        for param in req['parameters']:
                            f.write(f"     - {param}\n")
                    if req.get('constraints'):
                        f.write("   - Ограничения:\n")
                        for constraint in req['constraints']:
                            f.write(f"     - {constraint}\n")
                    f.write("\n")
                
                # Критические пути
                f.write("## Критические пути\n")
                for i, path in enumerate(analysis.critical_paths, 1):
                    f.write(f"{i}. {path.get('name', '')}\n")
                    f.write(f"   - Описание: {path.get('description', '')}\n")
                    if path.get('steps'):
                        f.write("   - Шаги:\n")
                        for j, step in enumerate(path['steps'], 1):
                            f.write(f"     {j}. {step}\n")
                    if path.get('edge_cases'):
                        f.write("   - Граничные случаи:\n")
                        for case in path['edge_cases']:
                            f.write(f"     - {case}\n")
                    f.write("\n")
                
                # Рекомендации
                f.write("## Рекомендации по тестированию\n")
                f.write("### Приоритетные области\n")
                for area in analysis.recommendations.get('priority_areas', []):
                    f.write(f"- {area}\n")
                f.write("\n")
                
                f.write("### Сложные сценарии\n")
                for scenario in analysis.recommendations.get('complex_scenarios', []):
                    f.write(f"- {scenario}\n")
                f.write("\n")
                
                f.write("### Риски\n")
                for risk in analysis.recommendations.get('risks', []):
                    f.write(f"- {risk}\n")
                f.write("\n")
            
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

    async def generate_test_cases(self, doc_path: str):
        """Основной метод генерации тест-кейсов."""
        try:
            doc_name = os.path.basename(doc_path)
            doc_content = self.load_file(doc_path)
            
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
        for doc_file in doc_files:
            full_path = os.path.join(docs_dir, doc_file)
            logger.info(f"Обрабатываю файл: {full_path}")
            
            try:
                await generator.generate_test_cases(full_path)
            except Exception as e:
                logger.error(f"Ошибка при обработке файла {doc_file}: {e}")
                continue

    except Exception as e:
        logger.error(f"Ошибка при создании тест-кейсов: {e}")
        logger.exception("Подробности ошибки:")

if __name__ == "__main__":
    asyncio.run(main()) 