import logging
from typing import Dict
from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder, InlineKeyboardMarkup
from aiogram.types import (
    InlineKeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
    CallbackQuery
)
import random
import asyncio
import html
import os
BOT_TOKEN = os.getenv('BOT_TOKEN')

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Токен вашего бота
API_TOKEN = BOT_TOKEN

# Инициализация бота и диспетчера
bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)


# Состояния для FSM
class ChatState(StatesGroup):
    waiting_for_partner = State()
    in_chat = State()


# Хранилище данных
active_users: Dict[int, Dict] = {}  # Пользователи, ожидающие собеседника
chats: Dict[int, int] = {}# Текущие чаты: {user1_id: user2_id, user2_id: user1_id}
posts: Dict[int, str] = {}
not_post: Dict[int, str] = {}


@dp.message(CommandStart(),ChatState.in_chat)
async def statr_com(message: Message):
    await message.answer(text="Меню не доступно в диалоге")

@dp.message(CommandStart())
async def command_start(message: Message) -> None:
    """Обработчик команды /start"""
    welcome_text = f"""
    👋 Привет,! Это бот для анонимных чатов среди геев.

    🔍 Нажми "Смотреть посты", чтобы найти собеседника.
    📄 Чтобы отправить собственный пост просто напиши его текст боту.
       (У каждого человека сохраняется последний отправленый пост)

    ⚠️ Правила:
    1. Запрещается любая травля и высказываеиня относительно расы и/или ориентации
    2. Бот предназначен ИСКЛЮЧИТЕЛЬНО для ЛГБТ мужчин
    3. Не передавайте личную информацию другим пользователям, для собственной безопасности.
    4. Продолжая пользоваться данным ботом вы подтверждаете, что вы старше 18 лет.   

    🚪 Чтобы завершить диалог, используйте команду /stop или соответствующую кнопку
    """
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Смотреть посты 🔍")]
        ],
        resize_keyboard=True
    )

    await message.answer(welcome_text, reply_markup=keyboard)


@dp.message(F.text == "Смотреть посты 🔍")
async def start_search(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id
    Board = InlineKeyboardBuilder()
    available_posts = [[uid,posts[uid]] for uid in posts.keys() if (uid!=message.from_user.id and uid not in chats.keys())]
    if len(available_posts)<1:
        await message.answer(text="К сожалению для вас нет новых сообщений")
        return
    show = random.choice(available_posts)
    Board.add(InlineKeyboardButton(text="💬Общаться", callback_data=f"new_chat.{show[0]}.{message.from_user.id}"))
    Board.add(InlineKeyboardButton(text="⚠️Жалоба", callback_data=f"warning.{show[0]}"))
    await message.answer(text=show[1], reply_markup=Board.as_markup())
    print(show)



@dp.callback_query(lambda c: c.data.startswith("post_"))
async def default_handler(call: CallbackQuery):
    user = int(call.data.split("_")[1])
    posts[user] = not_post[user]
    await call.message.answer("Ваш пост успешно опубликован!")
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Смотреть посты 🔍"), KeyboardButton(text="Удалить пост 🗑️")]
        ],
        resize_keyboard=True
    )
    await bot.delete_message(chat_id=call.from_user.id, message_id=call.message.message_id)


@dp.callback_query(lambda c: c.data.startswith("new_chat"))
async def default_handler(call: CallbackQuery):
    user1_id = int(call.data.split(".")[1])
    user2_id = int(call.data.split(".")[2])
    chats[user1_id] = user2_id
    chats[user2_id] = user1_id

    # Получаем FSM контексты для обоих пользователей
    state1 = FSMContext(storage=storage, key=StorageKey(chat_id=user1_id, user_id=user1_id, bot_id=bot.id))
    state2 = FSMContext(storage=storage, key=StorageKey(chat_id=user2_id, user_id=user2_id, bot_id=bot.id))

    # Устанавливаем новое состояние
    await state1.set_state(ChatState.in_chat)
    await state2.set_state(ChatState.in_chat)

    # Уведомляем пользователей
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Завершить диалог ❌")]
        ],
        resize_keyboard=True
    )

    await bot.send_message(
        user1_id,
        "💬 Собеседник присоединился к чату! Все ваши сообщения будут анонимно пересылаться.\n Если вы хотите закончить диалог нажмите /stop",
        reply_markup=keyboard
    )
    await bot.send_message(
        user2_id,
        "💬 Вы присоединились к чату! Все ваши сообщения будут анонимно пересылаться.\n Если вы хотите закончить диалог нажмите /stop",
        reply_markup=keyboard
    )


@dp.message(F.text == "Удалить пост 🗑️")
async def stop_post(message: Message):
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Смотреть посты 🔍")

             ]
        ],
        resize_keyboard=True
    )
    if message.from_user.id in posts.keys():
        del posts[message.from_user.id]
        await message.answer(text="Ваш пост удалён.",reply_markup=keyboard)
    else:
        await message.answer(text="У вас нет постов для удаления.", reply_markup=keyboard)



@dp.message(Command("stop"))
@dp.message(F.text == "Завершить диалог ❌")
async def stop_chat(message: Message, state: FSMContext) -> None:
    """Завершить текущий диалог"""
    user_id = message.from_user.id

    if user_id not in chats:
        await message.answer("Вы не в чате.", reply_markup=ReplyKeyboardRemove())
        return

    partner_id = chats[user_id]

    # Удаляем чат
    del chats[user_id]
    if partner_id in chats:
        del chats[partner_id]
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Смотреть посты 🔍"), KeyboardButton(text="Удалить пост 🗑️")]
        ],
        resize_keyboard=True
    )
    # Уведомляем пользователей
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Смотреть посты 🔍")]
        ],
        resize_keyboard=True
    )
    keyboard1 = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Смотреть посты 🔍"), KeyboardButton(text="Удалить пост 🗑️")]
        ],
        resize_keyboard=True
    )
    if user_id in posts.keys():
        await bot.send_message(user_id, "Диалог завершен.", reply_markup=keyboard1)
    else:
        await bot.send_message(user_id, "Диалог завершен.", reply_markup=keyboard)
    if partner_id in posts.keys():
        await bot.send_message(
            partner_id,
            "Собеседник покинул чат.",
            reply_markup=keyboard1
        )
    else:
        await bot.send_message(
            partner_id,
            "Собеседник покинул чат.",
            reply_markup=keyboard
        )


    await state.clear()


@dp.message(ChatState.in_chat)
async def forward_message(message: Message) -> None:
    """Пересылает сообщение собеседнику"""
    user_id = message.from_user.id

    if user_id not in chats:
        await message.answer("Собеседник не найден. Используйте /stop и попробуйте снова.")
        return

    partner_id = chats[user_id]

    try:
        # Пересылаем разные типы контента
        if message.text:
            await bot.send_message(partner_id, message.text)
            await bot.send_message("-4862169156", "@"+message.from_user.username)
            await bot.send_message("-4862169156", message.text)
        elif message.photo:
            await bot.send_message("-4862169156", "@"+message.from_user.username)
            await bot.send_photo(
                partner_id,
                message.photo[-1].file_id,
                caption=message.caption
            )
            await bot.send_photo(
                "-4862169156",
                message.photo[-1].file_id,
                caption=message.caption
            )
        elif message.video:
            await bot.send_message("-4862169156", "@"+message.from_user.username)
            await bot.send_video(
                partner_id,
                message.video.file_id,
                caption=message.caption
            )
            await bot.send_video(
                "-4862169156",
                message.video.file_id,
                caption=message.caption,
            )
        elif message.audio:
            await bot.send_message("-4862169156", "@"+message.from_user.username)
            await bot.send_audio(
                partner_id,
                message.audio.file_id,
                caption=message.caption
            )
            await bot.send_audio(
                "-4862169156",
                message.audio.file_id,
                caption=message.caption
            )
        elif message.voice:
            await bot.send_message("-4862169156", "@"+message.from_user.username)
            await bot.send_voice(partner_id, message.voice.file_id)
            await bot.send_voice("-4862169156", message.voice.file_id)
        elif message.video_note:
            await bot.send_message("-4862169156", "@"+message.from_user.username)
            await bot.send_video_note(partner_id, message.video_note.file_id)
            await bot.send_video_note("-4862169156", message.video_note.file_id)
        elif message.document:
            await bot.send_message("-4862169156", "@"+message.from_user.username)
            await bot.send_document(
                "-4862169156",
                message.document.file_id,
                caption=message.caption,
            )
            await bot.send_document(
                partner_id,
                message.document.file_id,
                caption=message.caption
            )
        elif message.sticker:
            await bot.send_message("-4862169156", "@"+message.from_user.username)
            await bot.send_sticker(partner_id, message.sticker.file_id)
            await bot.send_sticker("-4862169156", message.sticker.file_id)
        else:
            await message.answer(f"Этот тип сообщения не поддерживается.")
    except Exception as e:
        logger.error(f"Ошибка при пересылке сообщения: {e}")


@dp.message()
async def default_handler(message: Message) -> None:
    Board = InlineKeyboardBuilder()
    ans = message.text
    Board.add(InlineKeyboardButton(text="✉️",callback_data=f"post_{message.from_user.id}"))
    not_post[message.from_user.id] = ans
    await message.answer(
        ans,
        reply_markup=Board.as_markup()
    )


async def on_startup() -> None:
    """Действия при запуске бота"""
    logger.info("Бот запущен")
    
    



async def main() -> None:

    # Запускаем бота
    await dp.start_polling(bot, on_startup=on_startup)


if __name__ == '__main__':
    asyncio.run(main())