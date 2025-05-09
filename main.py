import configparser, json, uuid, requests, threading, time
from datetime import datetime
import telebot
from telebot import types, TeleBot, custom_filters
from telebot.storage import StateMemoryStorage
from telebot.handler_backends import State, StatesGroup


config = configparser.ConfigParser()
conf = 'setting.ini'
config.read(conf, encoding='utf-8')
# Constants name
OZON_TOKEN = config['Ozon']['ozon_token']
OZON_CLIENT = config['Ozon']['ozon_client']
DATE_ = datetime.strptime(config['Ozon']['date_in'], '%d-%m-%Y')
SCORE_LESS_THREE = config['Ozon']['score_less_three']
SCORE_FOUR = config['Ozon']['score_four']
SCORE_FIVE = config['Ozon']['score_five']
TG_TOKEN = config['Tg']['tg_token']
TG_GROUP = config['Tg']['tg_group']
GIGA_TOKEN = config['Giga']['giga_token']
GIGA_SCOPE = config['Giga']['scope']
ACCESS_TOKEN = config['Giga']['access_token']
CONTENT = config['Giga']['content']

bot = telebot.TeleBot(TG_TOKEN)

# получение access_token
def get_access_token():
    rq_uid = str(uuid.uuid4())
    url = 'https://ngw.devices.sberbank.ru:9443/api/v2/oauth'
    payload = {
        'scope': GIGA_SCOPE
    }
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Accept': 'application/json',
        'RqUID': rq_uid,
        'Authorization': f'Basic {GIGA_TOKEN}'
    }
    try:
        response = requests.request("POST", url, headers=headers, data=payload, verify=False)
        config['Giga']['access_token'] = response.json()['access_token']
        ACCESS_TOKEN = response.json()['access_token']
        with open(conf, 'w', encoding='utf-8') as f:
            config.write(f)
        return  response.json()['access_token']
    except requests.RequestException as e:
        bot.send_message(chat_id=TG_GROUP, text=f'В коде произошла ошибка: {e}')  ### для тг
        return None


# Создание ответа на отзыв
def creating_feedback_gigachat(text, rating):
    global ACCESS_TOKEN
    url = 'https://gigachat.devices.sberbank.ru/api/v1/chat/completions'
    payload = json.dumps({
        "model": "GigaChat",
        "messages": [
            {
                "role": "system",
                "content": CONTENT
            },
            {
                "role": "user",
                "content": f'Оценка: {str(rating)}. Отзыв: {text}'
            }
        ],
        "stream": False,
        "update_interval": 0
    })
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'Authorization': f'Bearer {ACCESS_TOKEN}'
    }
    try:
        response = requests.post(url, headers=headers, data=payload, verify=False)
        if response.status_code == 200:
            response = response.json()['choices'][0]['message']['content'] # если что убрать
            return response
        elif response.status_code == 401:
            ACCESS_TOKEN = get_access_token()
            return creating_feedback_gigachat(text, rating)
    except requests.RequestException as e:
        bot.send_message(chat_id=TG_GROUP, text=f'В коде произошла ошибка: {e}')  ### для тг
        return None

# Узнаем отзывы на ozon
def list_feedback_ozon():
    url = 'https://api-seller.ozon.ru'
    method = "/v1/review/list"
    head = {
        "Api-Key": OZON_TOKEN,
        "Client-Id": OZON_CLIENT,
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    body = {
        "limit": 100,
        "sort_dir": "DESC",
        "status": "UNPROCESSED"
}
    body = json.dumps(body)  # Нужно передавать в озон именно так, потому что string он как json не понимает
    response = requests.post(url + method, headers=head, data=body)
    if response.status_code == 200:
        try:
            response_json = json.loads(response.text)
            return response_json['reviews']
        except json.JSONDecodeError as e:
            bot.send_message(chat_id=TG_GROUP, text=f'В коде произошла ошибка: {e}') ### для тг
            return None
    else:
        bot.send_message(chat_id=TG_GROUP, text=f'В коде произошла ошибка в функции list_feedback_ozon')  ### для тг
        return None


# Отправка в тг
def send_feedback_to_tg(feedback, feedback_gigachat):
    message = (f"Отработан отзыв:\n"
               f"Отзыв: {feedback['text']}\n"
               f"Рейтинг: {feedback['rating']}\n"
               f"Ответ на отзыв: {feedback_gigachat}")
    bot.send_message(chat_id=TG_GROUP, text=message)

#  функция обработки времени
def time_ozon(published_at):
    date_object = datetime.fromisoformat(published_at[:-1] + '+00:00')
    formatted_date = date_object.strftime("%d-%m-%Y %H:%M:%S")
    formatted_date = datetime.strptime(formatted_date, "%d-%m-%Y %H:%M:%S")
    return formatted_date

# Функция если нет отзыв, а просто рейтинг поставлен
def only_rating(rating):
    if rating == 5:
        return SCORE_FIVE
    elif rating == 4:
        return SCORE_FOUR
    else:
        return SCORE_LESS_THREE


# Отправка отзыва на озон
def sending_review_on_ozon(feedback, review):
    url = 'https://api-seller.ozon.ru'
    method = "/v1/review/comment/create"
    head = {
        "Api-Key": OZON_TOKEN,
        "Client-Id": OZON_CLIENT,
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    # Сюда пишем параметры запроса
    body = {
        "mark_review_as_processed": True,
        "review_id": feedback['id'], # данные по идентифик,
        "text": review # текст из giga
    }
    body = json.dumps(body)  # Нужно передавать в озон именно так, потому что string он как json не понимает
    response = requests.post(url + method, headers=head, data=body)
    if response.status_code == 200:
        try:
            response_json = json.loads(response.text)
            return True
        except json.JSONDecodeError as e:
            bot.send_message(chat_id=TG_GROUP, text=f'В коде произошла ошибка: {e}')  ### для тг
            return None ### для тг
    else:
        bot.send_message(chat_id=TG_GROUP, text=f'В коде произошла ошибка в функции sending_review_on_ozon')  ### для тг
        return None

# пока не работает, т.к выдает 400 ошибку

# def receiving_product_info(skus): # Получение информации по товару с озон
#     url = 'https://api-seller.ozon.ru'
#     method = "/v1/product/rating-by-sku"
#     head = {
#         "Client-Id": OZON_CLIENT,
#         "Api-Key": OZON_TOKEN,
#         "Content-Type": "application/json",
#         "Accept": "application/json"
#     }
#     # Сюда пишем параметры запроса
#     body = {
#         "skus": [str(skus)]
#     }
#     body = json.dumps(body)  # Нужно передавать в озон именно так, потому что string он как json не понимает
#     response = requests.post(url + method, headers=head, data=body)
#     if response.status_code == 200:
#         try:
#             response_json = json.loads(response.text)

#             return response_json
#         except json.JSONDecodeError as e:
#             print(f'закинуть в тг что ошибка: {e}')  ### для тг
#     else:
#         print(f'закинуть в тг что ошибка статус запроса {response.status_code}')  ### для тг

# Мониторин отзывов и это 2 поток # y
def monitoring_feedback():
    while True:
        new_feedback = list_feedback_ozon()
        if len(new_feedback) > 0:
            for feedback in new_feedback:
                time_ = time_ozon(feedback['published_at'])
                if time_ > DATE_:
                    if len(feedback['text']) > 0:
                        feedback_gigachat = creating_feedback_gigachat(feedback['text'],feedback['rating'])   # Получение с giga ответ на отзыв
                        # sku = receiving_product_info(feedback['sku']) # получим имя товара (не работает)
                        sending_review_on_ozon(feedback,feedback_gigachat) # отправили ответ на отзыв
                        send_feedback_to_tg(feedback, feedback_gigachat) # отправка в тг о том что отзыв отправлен
                    else:
                        feedback_no_gigachat = only_rating(feedback['rating'])
                        sending_review_on_ozon(feedback, feedback_no_gigachat) # отправили ответ на отзыв
                        send_feedback_to_tg(feedback, feedback_no_gigachat)
                time.sleep(4)
        time.sleep(100) # Проверяем отзывы каждые 100 секунд или 1,40 мин

@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(message.chat.id, 'Я бот для мониторинга отзывов Ozon!')

def start_monitoring():
    thread = threading.Thread(target=monitoring_feedback)
    thread.start()

if __name__ == '__main__':
    start_monitoring()
    bot.polling(none_stop=True)

