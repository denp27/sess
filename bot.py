import os
import asyncio
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message, FSInputFile
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError

# ================= НАСТРОЙКИ =================
API_ID = 1234567               # Ваш API_ID с my.telegram.org
API_HASH = 'your_api_hash'     # Ваш API_HASH с my.telegram.org
BOT_TOKEN = 'your_bot_token'   # Токен вашего бота от @BotFather
ADMIN_ID = 123456789           # Ваш Telegram ID (узнать в @userinfobot)
# =============================================

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

class AuthStates(StatesGroup):
    waiting_for_phone = State()
    waiting_for_code = State()
    waiting_for_password = State()

@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    # Проверка доступа по ID
    if message.from_user.id != ADMIN_ID:
        await message.answer("У вас нет доступа к этому боту.")
        return

    await message.answer("Введите номер телефона в международном формате (например, +79991234567):")
    await state.set_state(AuthStates.waiting_for_phone)

@dp.message(AuthStates.waiting_for_phone, F.text)
async def process_phone(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return

    phone = message.text.strip()
    session_name = f"session_{message.from_user.id}"
    
    client = TelegramClient(session_name, API_ID, API_HASH)
    await client.connect()
    
    try:
        sent_code = await client.send_code_request(phone)
        await state.update_data(
            phone=phone, 
            session_name=session_name, 
            phone_code_hash=sent_code.phone_code_hash,
            client=client
        )
        await message.answer("Код отправлен в Telegram. Введите код подтверждения:")
        await state.set_state(AuthStates.waiting_for_code)
    except Exception as e:
        await client.disconnect()
        await message.answer(f"Ошибка: {e}\nПопробуйте снова /start")
        await state.clear()

@dp.message(AuthStates.waiting_for_code, F.text)
async def process_code(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return

    code = message.text.strip()
    data = await state.get_data()
    
    client: TelegramClient = data['client']
    phone = data['phone']
    phone_code_hash = data['phone_code_hash']
    session_name = data['session_name']
    
    try:
        await client.sign_in(phone=phone, code=code, phone_code_hash=phone_code_hash)
        await finish_auth(message, client, session_name, state)
    except SessionPasswordNeededError:
        await message.answer("У вас включена двухэтапная аутентификация. Введите облачный пароль (пароль 2FA):")
        await state.set_state(AuthStates.waiting_for_password)
    except PhoneCodeInvalidError:
        await message.answer("Неверный код. Введите правильный код подтверждения:")
    except Exception as e:
        await client.disconnect()
        await message.answer(f"Ошибка авторизации: {e}\nНачните заново /start")
        await state.clear()

@dp.message(AuthStates.waiting_for_password, F.text)
async def process_password(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return

    password = message.text.strip()
    data = await state.get_data()
    
    client: TelegramClient = data['client']
    session_name = data['session_name']
    
    try:
        await client.sign_in(password=password)
        await finish_auth(message, client, session_name, state)
    except Exception as e:
        await client.disconnect()
        await message.answer(f"Неверный пароль или ошибка: {e}\nНачните заново /start")
        await state.clear()

async def finish_auth(message: Message, client: TelegramClient, session_name: str, state: FSMContext):
    await client.disconnect()
    
    session_file = f"{session_name}.session"
    if os.path.exists(session_file):
        file_to_send = FSInputFile(session_file)
        await message.answer_document(file_to_send, caption="Ваш файл сессии успешно создан!")
        
        # Автоматическое удаление файла с сервера
        os.remove(session_file)
    else:
        await message.answer("Не удалось найти созданный файл сессии.")
        
    await state.clear()

async def main():
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
