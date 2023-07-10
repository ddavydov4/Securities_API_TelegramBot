import threading
import time

import requests
import json
import os
import psycopg2 as pg
from datetime import date, timedelta
from aiogram import Bot, Dispatcher, executor, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.dispatcher import FSMContext
from aiogram.types import Message
import logging


conn = pg.connect(
    user='postgres',
    password='postgres',
    host='localhost',
    port='5432',
    database='DB'
)
cur = conn.cursor()


user_commands = [
    types.BotCommand(command='/start', description='Начать'),
    types.BotCommand(command='/add_security', description='Добавить ценную бумагу к портфелю отслеживания'),
    types.BotCommand(command='/securities_indicators', description='Узнать показатели отслеживаемых ценных бумаг')
]


bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
bot = Bot(token=bot_token)
dp = Dispatcher(bot, storage=MemoryStorage())


interval = 10
api_key = 'NBOZXCZTMQIP2TN7'


class Form(StatesGroup):
    save = State()


def get_avg(name):
    data = fetch_data(name)
    if data.get('Error Message'):
        return 'null', 'null'
    max_days = 30
    n = 30
    total = 0
    period = 0
    day_offset = 0
    days_counted = 0
    matter = []
    dates = []
    avgs = []
    while days_counted < max_days:
        day = (date.today() - timedelta(days=day_offset)).isoformat()
        day_info = data['Time Series (Daily)'].get(day)
        day_offset += 1
        if day_info is None:
            continue
        dates.append(day)
        value = float(day_info['4. close'])
        matter.append(value)
        total += value
        period += 1
        if period == n:
            avg = round(total / n, 2)
            avgs.append(avg)
            period = 0
            total
    matter.reverse()
    avgs.reverse()
    dates.reverse()
    return avgs


async def add_stock_to_portfolio(user_id, stock_name):
    avg = get_avg(stock_name)
    cur.execute("""SELECT * FROM stock WHERE user_id = %s AND stock_name = %s""",(user_id, stock_name))
    users = cur.fetchall()
    if len(users) == 0:
        cur.execute("""INSERT INTO stock (user_id, stock_name, averages) VALUES (%s, %s, %s)""",(user_id, stock_name, avg))
        conn.commit()
        return f'Ценная бумага {stock_name} добавлена к отслеживаемым'
    else:
        cur.execute(
            """UPDATE stock SET averages = %s WHERE user_id = %s AND stock_name = %s""",
            (avg, user_id, stock_name)
        )
    conn.commit()
    return f'Ценная бумага {stock_name} обновлена в портфеле'


def get_stock_info_by_name(names):
    msg = ''
    cur.execute(f"""SELECT * FROM stock where user_id = %s""", (names,))
    stocks = cur.fetchall()
    for _, user_id, stock_name, averages in stocks:
        if averages == 'null':
            msg += f'Для ценной бумаги {stock_name} не найдено значений\n\n'
        else:
            msg += f'Акция {stock_name} имеет\nсреднее значение {averages}\n\n'
    return msg


async def recalculate_portfolio():
    cur.execute("""SELECT * FROM stock""")
    stocks = cur.fetchall()
    for row in stocks:
        user_id, stock_name = row[1], row[2]
        averages = get_avg(stock_name)
        cur.execute("""UPDATE stock SET averages = %s WHERE user_id = %s AND stock_name = %s""",(averages, user_id, stock_name))
        conn.commit()


@dp.message_handler(commands=['start'])
async def start_command(message: Message):
    await message.answer('Привет, напиши команду /add_security, если хочешь добавить ценную бумагу в портфель и /securities_indicators, если хочешь узнать показатели ценных бумаг')


@dp.message_handler(commands=['add_security'])
async def add_stock(message: Message):
    await message.answer('Введите название ценной бумаги, которую хотите добавить')
    await Form.save.set()


@dp.message_handler(state=Form.save)
async def save_stock(message: Message, state: FSMContext):
    user_id = message.from_id
    stock_name = message.text
    msg = await add_stock_to_portfolio(user_id, stock_name)
    await message.answer(msg)
    await state.finish()


@dp.message_handler(commands=['securities_indicators'])
async def show_portfolio(message: Message):
    data = message.from_id
    msg = get_stock_info_by_name(data)
    await message.answer(msg)


def fetch_data(name):
    try:
        url = f"https://www.alphavantage.co/query?function=TIME_SERIES_DAILY_ADJUSTED&symbol={name}&apikey={api_key}"
        response = requests.get(url)
        return json.loads(response.text)
    except requests.exceptions.RequestException as e:
        print(e)
        return None


def recalculate_stocks():
    cur.execute(f"""SELECT * FROM stock""")
    stocks = cur.fetchall()
    for id, user_id, stock_name, averages in stocks:
        averages = get_avg(stock_name)
        cur.execute(f"""UPDATE stock SET averages = '{averages}'WHERE stock_name = '{stock_name}'""")


def recalculate_stock():
    cur.execute("""SELECT stock_name, averages FROM stock WHERE stock_name = %s""")


def periodically_recalculate_stocks():
    while True:
        recalculate_stocks()
        time.sleep(60*60*24)


if __name__ == '__main__':
    thread = threading.Thread(target=periodically_recalculate_stocks)
    thread.start()
    logging.basicConfig(level=logging.INFO)
    cur = conn.cursor()
    executor.start_polling(dp, skip_updates=True)