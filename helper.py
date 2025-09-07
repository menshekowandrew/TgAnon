import asyncio
import logging
import os
from typing import Dict, Optional
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, \
    InlineKeyboardButton
from aiogram.filters import CommandStart, Text, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# Загрузка переменных окружения
load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN1')
ADMIN_CHAT_ID = os.getenv('ADMIN_CHAT_ID1')

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не найден в переменных окружения")
if not ADMIN_CHAT_ID:
    raise ValueError("ADMIN_CHAT_ID не найден в переменных окружения")

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


# База данных в памяти
class Database:
    def __init__(self):
        self.user_messages = {}  # {message_id: user_id}
        self.admin_messages = {}  # {admin_message_id: original_message_id}

    def add_user_message(self, user_message_id: int, user_id: int):
        self.user_messages[user_message_id] = user_id

    def get_user_by_message(self, message_id: int) -> Optional[int]:
        return self.user_messages.get(message_id)

    def add_admin_message(self, admin_message_id: int, original_message_id: int):
        self.admin_messages[admin_message_id] = original_message_id

    def get_original_message(self, admin_message_id: int) -> Optional[int]:
        return self.admin_messages.get(admin_message_id)


db = Database()


# Клавиатуры
def get_main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📨 Написать администрации")],
            [KeyboardButton(text="ℹ️ О боте")]
        ],
        resize_keyboard=True
    )


def get_cancel_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="❌ Отмена")]
        ],
        resize_keyboard=True
    )


def get_reply_keyboard(message_id: int):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💬 Ответить", callback_data=f"reply_{message_id}")]
        ]
    )


# Состояния FSM
class FeedbackState(StatesGroup):
    waiting_for_message = State()


class ReplyState(StatesGroup):
    waiting_for_reply = State()


# Обработчики
@dp.message(CommandStart())
async def cmd_start(message: Message):
    welcome_text = """
🤖 Добро пожаловать в бот обратной связи!

Здесь вы можете написать сообщение администрации и получить ответ.

Для начала нажмите кнопку "📨 Написать администрации" или просто напишите ваше сообщение.
    """
    await message.answer(welcome_text, reply_markup=get_main_keyboard())


@dp.message(Text("📨 Написать администрации"))
async def start_feedback(message: Message, state: FSMContext):
    await message.answer(
        "✍️ Напишите ваше сообщение администрации:",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(FeedbackState.waiting_for_message)


@dp.message(Text("❌ Отмена"))
async def cancel_feedback(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "❌ Отменено",
        reply_markup=get_main_keyboard()
    )


@dp.message(FeedbackState.waiting_for_message)
async def process_feedback(message: Message, state: FSMContext):
    # Пересылаем сообщение в чат админов
    admin_text = f"""
📨 Новое сообщение от пользователя:

👤 User ID: {message.from_user.id}
📛 Имя: {message.from_user.full_name}
@{message.from_user.username}

💬 Сообщение:
{message.text}
    """

    # Отправляем сообщение админам
    admin_message = await bot.send_message(
        chat_id=ADMIN_CHAT_ID,
        text=admin_text,
        reply_markup=get_reply_keyboard(message.message_id)
    )

    # Сохраняем в базу данных
    db.add_user_message(message.message_id, message.from_user.id)
    db.add_admin_message(admin_message.message_id, message.message_id)

    await message.answer(
        "✅ Ваше сообщение отправлено администрации! Ожидайте ответа.",
        reply_markup=get_main_keyboard()
    )
    await state.clear()


@dp.message(Text("ℹ️ О боте"))
async def about_bot(message: Message):
    about_text = """
🤖 О боте

Этот бот создан для связи с администрацией.
Отправляйте свои вопросы и получайте ответы!
    """
    await message.answer(about_text)


@dp.callback_query(Text(startswith="reply_"))
async def start_reply(callback: CallbackQuery, state: FSMContext):
    message_id = int(callback.data.split("_")[1])
    user_id = db.get_user_by_message(message_id)

    if not user_id:
        await callback.answer("Сообщение не найдено")
        return

    await state.update_data(user_id=user_id, original_message_id=message_id)
    await callback.message.answer(
        "✍️ Напишите ответ пользователю:",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(ReplyState.waiting_for_reply)
    await callback.answer()


@dp.message(ReplyState.waiting_for_reply)
async def send_reply(message: Message, state: FSMContext):
    data = await state.get_data()
    user_id = data['user_id']
    original_message_id = data['original_message_id']

    try:
        # Отправляем ответ пользователю
        reply_text = f"""
📩 Ответ от администрации:

{message.text}

---
Для нового вопроса нажмите /start
        """

        await bot.send_message(
            chat_id=user_id,
            text=reply_text
        )

        # Уведомляем админов об отправке
        admin_notification = f"""
✅ Ответ отправлен пользователю {user_id}
💬 Текст ответа: {message.text[:50]}...
        """

        await message.answer(admin_notification)

        # Редактируем оригинальное сообщение админам чтобы показать что ответили
        try:
            original_admin_message = message.reply_to_message
            if original_admin_message:
                await bot.edit_message_text(
                    chat_id=ADMIN_CHAT_ID,
                    message_id=original_admin_message.message_id,
                    text=f"✅ ОТВЕЧЕНО: {original_admin_message.text}",
                    reply_markup=None
                )
        except:
            pass  # Если не удалось отредактировать - не критично

    except Exception as e:
        await message.answer(f"❌ Ошибка при отправке: {e}")

    await state.clear()


@dp.message(F.text)
async def handle_text_message(message: Message, state: FSMContext):
    # Если пользователь просто написал текст без команды
    current_state = await state.get_state()
    if not current_state and message.text not in ["📨 Написать администрации", "ℹ️ О боте", "❌ Отмена"]:
        await message.answer(
            "Нажмите '📨 Написать администрации' чтобы отправить сообщение администрации",
            reply_markup=get_main_keyboard()
        )


# Команда для админов чтобы проверить работу
@dp.message(Command("admin"))
async def admin_check(message: Message):
    if str(message.chat.id) == ADMIN_CHAT_ID:
        await message.answer("✅ Бот работает корректно в этом чате!")
    else:
        await message.answer("Этот чат не является админ-чатом")


async def main():
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())