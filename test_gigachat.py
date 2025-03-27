from gigachat import GigaChat
import os
from dotenv import load_dotenv
import logging
import json

# Настройка логирования
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Загрузка переменных окружения
load_dotenv()

def test_gigachat_connection():
    try:
        # Получаем учетные данные
        credentials = os.getenv("GIGACHAT_CREDENTIALS")
        if not credentials:
            logger.error("GIGACHAT_CREDENTIALS не установлен в .env файле")
            return False
            
        # Инициализируем GigaChat
        gigachat = GigaChat(
            credentials=credentials,
            verify_ssl_certs=False
        )
        
        # Отправляем тестовый запрос
        response = gigachat.chat("Привет! Это тестовое сообщение.")
        
        # Логируем полный ответ для отладки
        logger.debug(f"Полный ответ от GigaChat: {response}")
        logger.debug(f"Тип ответа: {type(response)}")
        logger.debug(f"Атрибуты ответа: {dir(response)}")
        
        if response:
            if hasattr(response, 'choices'):
                logger.info(f"Choices: {response.choices}")
            if hasattr(response, 'content'):
                logger.info(f"Content: {response.content}")
            if hasattr(response, 'text'):
                logger.info(f"Text: {response.text}")
            return True
        else:
            logger.error("Не удалось получить ответ от GigaChat")
            return False
            
    except Exception as e:
        logger.error(f"Ошибка при тестировании GigaChat: {e}")
        logger.exception("Подробности ошибки:")
        return False

if __name__ == "__main__":
    test_gigachat_connection() 