import logging
import os
import sys
import time
from http import HTTPStatus

import requests
import vk_api
from dotenv import load_dotenv
from vk_api.utils import get_random_id

load_dotenv()


PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
VK_TOKEN = os.getenv('VK_TOKEN')
VK_USER_ID = os.getenv('VK_USER_ID')

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


def check_tokens():
    """Проверка доступности переменных окружения."""
    tokens = {
        'PRACTICUM_TOKEN': PRACTICUM_TOKEN,
        'VK_TOKEN': VK_TOKEN,
        'VK_USER_ID': VK_USER_ID,
    }
    missing_tokens = [name for name, value in tokens.items() if not value]
    if missing_tokens:
        missing_tokens_str = ', '.join(missing_tokens)
        logging.critical(
            f'Отсутствуют обязательные переменные окружения: '
            f'{missing_tokens_str}'
        )
        return False
    return True


def send_message(vk, message):
    """Отправка сообщения в VK-чат."""
    logging.debug(f'Начинаем отправку сообщения: "{message}"')
    try:
        vk.messages.send(
            user_id=int(VK_USER_ID),
            message=message,
            random_id=get_random_id()
        )
    except (vk_api.ApiError, requests.RequestException) as error:
        logging.exception(f'Сбой при отправке сообщения в VK: {error}')
        return False
    logging.info(f'Бот отправил сообщение: "{message}"')
    return True


def get_api_answer(timestamp):
    """Запрос к единственному эндпоинту API-сервиса."""
    payload = {'from_date': timestamp}
    logging.debug(
        f'Отправляем запрос к {ENDPOINT} с параметрами {payload}'
    )
    try:
        response = requests.get(ENDPOINT, headers=HEADERS, params=payload)
    except requests.RequestException as error:
        raise ConnectionError(
            f'Ошибка при запросе к API {ENDPOINT} '
            f'с параметрами {payload}: {error}'
        ) from error
    if response.status_code != HTTPStatus.OK:
        status_code = response.status_code
        response_text = response.text
        raise ConnectionError(
            f'Эндпоинт {ENDPOINT} недоступен. '
            f'Параметры запроса: {payload}. '
            f'Код ответа: {status_code}. '
            f'Текст ответа: {response_text}'
        )
    return response.json()


def check_response(response):
    """Проверка ответа API на соответствие документации."""
    logging.debug('Начинаем проверку ответа API.')
    if not isinstance(response, dict):
        response_type = type(response)
        raise TypeError(
            f'Ответ API не является словарём. Получен тип: {response_type}'
        )
    if 'homeworks' not in response:
        raise KeyError('В ответе API отсутствует ключ "homeworks".')
    if 'current_date' not in response:
        raise KeyError('В ответе API отсутствует ключ "current_date".')
    homeworks = response['homeworks']
    if not isinstance(homeworks, list):
        homeworks_type = type(homeworks)
        raise TypeError(
            f'Значение ключа "homeworks" не является списком. '
            f'Получен тип: {homeworks_type}'
        )
    return homeworks


def parse_status(homework):
    """Извлечение статуса конкретной домашней работы из информации."""
    if 'homework_name' not in homework:
        raise KeyError('В словаре homework отсутствует ключ "homework_name".')
    if 'status' not in homework:
        raise KeyError('В словаре homework отсутствует ключ "status".')
    homework_name = homework['homework_name']
    status = homework['status']
    if status not in HOMEWORK_VERDICTS:
        raise ValueError(f'Неизвестный статус домашней работы: {status}')
    verdict = HOMEWORK_VERDICTS[status]
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы программы."""
    if not check_tokens():
        sys.exit(
            'Программа принудительно остановлена из-за отсутствия токенов.'
        )
    vk_session = vk_api.VkApi(token=VK_TOKEN)
    vk = vk_session.get_api()
    timestamp = int(time.time())
    last_error_message = ''
    while True:
        try:
            response = get_api_answer(timestamp)
            homeworks = check_response(response)
            if homeworks:
                message = parse_status(homeworks[0])
                if send_message(vk, message):
                    timestamp = response.get('current_date', timestamp)
                    last_error_message = ''
            else:
                logging.debug('Новых статусов в ответе API нет.')
                timestamp = response.get('current_date', timestamp)
                last_error_message = ''
        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            logging.exception(message)
            if message != last_error_message and send_message(vk, message):
                last_error_message = message
        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s [%(levelname)s] %(message)s',
        handlers=(logging.StreamHandler(sys.stdout),),
    )
    main()
