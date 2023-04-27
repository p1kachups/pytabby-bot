import os
import re
import logging
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.utils import executor
import psycopg2


MESSAGES = {
    'start': 'Добрый день!',
    'help': '/start - начать диалог\n/help - вывести это меню\n/reset - сбросить данные',
    'reset': 'Данные сброшены. Напишите /start чтобы ввести новые данные',
    'no_context': 'Напишите /help для вывода доступных комманд',
    'get_fullname': 'Введите Ваше полное ФИО в формате \n"Иванов Иван Иванович"',
    'get_email': 'Введите Ваш адрес электронной почты в формате \n"example@mail.ru"',
    'email_incorrect': 'Некоректный имейл. Имейл должен быть в формате example@mail.ru. Попробуйте еще раз',
    'data_is_correct?': 'Данные верны?',
    'not_invited': 'Извините, вы не являетесь ответсвенным для доступа к чату. Свяжитесь с администратором @mirick',
    'invited': 'Ссылка для вступления в чат: https://t.me/+Xl4qCdHEil05ZDE6'
            }

print(open('cat.txt', 'r').read())

FORMAT = '%(asctime)s %(levelname)s %(name)s %(message)s'
logging.basicConfig(level=logging.INFO, format=FORMAT)
# Инициализация бота и диспетчера
if not "TELEGRAM_BOT_TOKEN" in os.environ:
    value = input('Введите токен: ')
    os.system(f"setx TELEGRAM_BOT_TOKEN {value}")
API_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)


class Common(StatesGroup):
    waiting_for_fullname = State()
    waiting_for_email = State()
    waiting_for_the_approval = State()


@dp.message_handler(commands=['start'])
async def process_start_command(message: types.Message, state: FSMContext):
    await message.answer(MESSAGES['start'])
    await asyncio.sleep(3.0)
    await message.answer(MESSAGES['get_fullname'])
    await state.set_state(Common.waiting_for_fullname.state)


@dp.message_handler(commands=['help'])
async def process_help_command(message: types.Message):
    await message.reply(MESSAGES['help'])


@dp.message_handler(commands=['reset'])
async def process_reset_command(message: types.Message, state: FSMContext):
    await message.reply(MESSAGES['reset'])
    await state.reset_state(with_data=False)


@dp.message_handler()
async def no_context(message: types.Message):
    await message.reply(MESSAGES['no_context'])


@dp.message_handler(state=Common.waiting_for_fullname)
async def ctx_get_fullname(message: types.Message, state: FSMContext):
    await message.answer(MESSAGES['get_email'])
    await state.update_data(fullname=message.text)
    await state.set_state(Common.waiting_for_email.state)
    

@dp.message_handler(state=Common.waiting_for_email)
async def ctx_get_email(message: types.Message, state: FSMContext):
    email_regex = r'^[\w\.-]+@[\w\.-]+\.\w+$'

    if not re.match(email_regex, message.text):
        await message.answer(MESSAGES['email_incorrect'])
        return
    
    await state.update_data(email=message.text)
    user_data = await state.get_data()

    buttons = [
        InlineKeyboardButton('Да', callback_data='yes'),
        InlineKeyboardButton('Нет', callback_data='no')
    ]
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(*buttons)
    await message.answer(f"{MESSAGES['data_is_correct?']}\nФИО:\t{user_data['fullname']}\nEmail:\t{user_data['email']}", reply_markup=keyboard)
    
    await state.set_state(Common.waiting_for_the_approval.state)


@dp.callback_query_handler(state=Common.waiting_for_the_approval, text='no')
async def ctx_approval_no(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer(MESSAGES['get_fullname'])
    await state.set_state(Common.waiting_for_fullname.state)


@dp.callback_query_handler(state=Common.waiting_for_the_approval, text='yes')
async def ctx_approval_yes(callback: types.CallbackQuery, state: FSMContext):
    user_data = await state.get_data()

    try:
        conn = psycopg2.connect(user="pytabbybot_root",
                                password="strongpass",
                                host="127.0.0.1",
                                port="5432",
                                database="pytabbybot_db")

        with conn.cursor() as curs:
            curs.execute(f'''INSERT INTO pyt_users (fullname, email) VALUES ('{user_data["fullname"]}', '{user_data["email"]}');''')
            with open(".\\data\\users.exported.csv", "w") as file:
                curs.copy_expert("COPY (SELECT * FROM pyt_users) TO STDOUT WITH CSV DELIMITER ';'", file)
            conn.commit()
            logging.log(msg=f"New user added: \n\temail:{user_data['email']}\n\tfullname:{user_data['fullname']}", level=20)

    except psycopg2.Error as e:
        logging.error(msg=f"{type(e).__module__.removesuffix('.errors')}:{type(e).__name__}: {str(e).rstrip()}")
    
    # Проверяем есть ли почта в базе
    file_path = os.path.join('data', 'users.txt')

    if not user_data['email'] in open(file_path, 'r').read():
        await callback.message.answer(MESSAGES['not_invited'])
        return
    
    await callback.message.answer(MESSAGES['invited'])
    await state.finish()


async def shutdown(dispatcher: Dispatcher):
    await dispatcher.storage.close()
    await dispatcher.storage.wait_closed()

if __name__ == '__main__':
    executor.start_polling(dp, on_shutdown=shutdown)
