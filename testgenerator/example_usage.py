from Enhanced_TestCase_Generator import EnhancedTestCaseGenerator
import os
from dotenv import load_dotenv
import logging
import json

# Настройка логирования
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Загрузка переменных окружения
load_dotenv()

def main():
    try:
        # Создаем экземпляр генератора тестов
        generator = EnhancedTestCaseGenerator()
        
        # Путь к файлу с тест-кейсом (поддерживаются TXT, PDF и CSV)
        test_case_path = "test_cases/example_test_case.csv"  # Теперь можно использовать CSV файл
        
        # Путь к проекту с существующими тестами (опционально)
        project_path = "path/to/your/project"
        
        # Загружаем тест-кейс
        test_case_content = generator.load_file(test_case_path)
        logger.info(f"Загружен тест-кейс из файла: {test_case_path}")
        
        # Анализируем существующие тесты
        test_analysis = generator.analyze_existing_tests(project_path)
        logger.info(f"Анализ существующих тестов: {json.dumps(test_analysis, indent=2, ensure_ascii=False)}")
        
        # Собираем аналитические данные
        analytics_data = generator.collect_analytics_data(project_path)
        logger.info(f"Аналитические данные: {json.dumps(analytics_data, indent=2, ensure_ascii=False)}")
        
        # Генерируем новый тест с учетом аналитических данных
        response = generator.generate_test_case(test_case_content)
        
        # Сохраняем результат
        generator.save_response(
            question="Создать автоматизированный тест на основе тест-кейса",
            response=response,
            response_type="test_case",
            language="java"
        )
        
        logger.info("Тест успешно сгенерирован и сохранен")
        
    except Exception as e:
        logger.error(f"Ошибка при генерации теста: {e}")
        logger.exception("Подробности ошибки:")

if __name__ == "__main__":
    main() 