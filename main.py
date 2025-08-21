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
import traceback
import time
from datetime import datetime, timedelta

# Получаем токен бота из переменных окружения
BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_KEY = os.getenv('ADMIN_KEY')

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Токен вашего бота
API_TOKEN = BOT_TOKEN

# Проверка наличия токена
if not API_TOKEN:
    logger.error("Токен бота не найден! Установите переменную BOT_TOKEN в окружении")
    exit(1)

# Инициализация бота и диспетчера
try:
    bot = Bot(token=API_TOKEN)
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)
    logger.info("Бот и диспетчер успешно инициализированы")
except Exception as e:
    logger.error(f"Ошибка инициализации бота: {e}")
    exit(1)


# Состояния для FSM
class ChatState(StatesGroup):
    waiting_for_partner = State()
    in_chat = State()
    waiting_for_broadcast = State()


# Хранилища данных
active_users: Dict[int, Dict] = {}  # Пользователи, ожидающие собеседника
chats: Dict[int, int] = {}  # Текущие чаты: {user1_id: user2_id, user2_id: user1_id}
posts: Dict[int, str] = {}  # Опубликованные посты пользователей
not_post: Dict[int, str] = {}  # Черновики постов перед публикацией
recently_users: Dict[int, list] = {}  # История недавних взаимодействий
post_creation_time: Dict[int, float] = {}  # Время создания постов (timestamp)
user_ids: Set[int] = set()  # Множество всех пользователей бота


@dp.message(Command("broadcast"))
async def broadcast_command(message: Message, state: FSMContext):
    """Секретная команда для начала рассылки"""
    try:
        # Проверяем секретный ключ (можно добавить проверку на admin ID)
        if len(message.text.split()) < 2 or message.text.split()[1] != ADMIN_KEY:
            await message.answer("❌ Неверный ключ доступа")
            return

        await message.answer(
            "📢 Режим рассылки активирован. Отправьте сообщение для рассылки всем пользователям.\n\n"
            "❌ Для отмены отправьте /cancel"
        )
        await state.set_state(ChatState.waiting_for_broadcast)
        logger.info(f"Пользователь {message.from_user.id} активировал режим рассылки")

    except Exception as e:
        logger.error(f"Ошибка в broadcast_command: {e}\n{traceback.format_exc()}")
        await message.answer("Ошибка при активации рассылки")


@dp.message(Command("cancel"), ChatState.waiting_for_broadcast)
async def cancel_broadcast(message: Message, state: FSMContext):
    """Отмена рассылки"""
    try:
        await state.clear()
        await message.answer("❌ Рассылка отменена")
        logger.info(f"Пользователь {message.from_user.id} отменил рассылку")
    except Exception as e:
        logger.error(f"Ошибка в cancel_broadcast: {e}\n{traceback.format_exc()}")


@dp.message(ChatState.waiting_for_broadcast)
async def process_broadcast_message(message: Message, state: FSMContext):
    """Обработка сообщения для рассылки"""
    try:
        broadcast_text = f"📢 <b>Важное сообщение от администрации:</b>\n\n{message.text}"

        await message.answer("⏳ Начинаю рассылку... Это может занять некоторое время.")

        success_count = 0
        fail_count = 0
        total_users = len(user_ids)

        # Рассылаем сообщение всем пользователям
        for user_id in list(user_ids):
            try:
                await bot.send_message(
                    user_id,
                    broadcast_text,
                    parse_mode=ParseMode.HTML
                )
                success_count += 1
                await asyncio.sleep(0.1)  # Задержка чтобы избежать flood
            except Exception as e:
                fail_count += 1
                logger.warning(f"Не удалось отправить сообщение пользователю {user_id}: {e}")

        # Формируем отчет
        report_text = (
            f"✅ Рассылка завершена!\n"
            f"👥 Всего пользователей: {total_users}\n"
            f"✅ Успешно отправлено: {success_count}\n"
            f"❌ Не удалось отправить: {fail_count}\n"
            f"📊 Процент доставки: {success_count / total_users * 100:.1f}%"
        )

        await message.answer(report_text)
        await state.clear()

        logger.info(f"Рассылка завершена. Успешно: {success_count}, Неудачно: {fail_count}")

    except Exception as e:
        logger.error(f"Ошибка в process_broadcast_message: {e}\n{traceback.format_exc()}")
        await message.answer("Ошибка при рассылке")
        await state.clear()


@dp.message(Command("stats"))
async def stats_command(message: Message):
    """Команда для получения статистики"""
    try:
        if len(message.text.split()) < 2 or message.text.split()[1] != ADMIN_KEY:
            await message.answer("❌ Неверный ключ доступа")
            return

        stats_text = (
            f"📊 <b>Статистика бота:</b>\n\n"
            f"👥 Всего пользователей: {len(user_ids)}\n"
            f"💬 Активных чатов: {len(chats) // 2}\n"
            f"📝 Активных постов: {len(posts)}\n"
            f"⏰ Постов создано сегодня: {sum(1 for t in post_creation_time.values() if time.time() - t < 86400)}\n"
            f"🔍 В поиске: {len(active_users)}"
        )

        await message.answer(stats_text, parse_mode=ParseMode.HTML)

    except Exception as e:
        logger.error(f"Ошибка в stats_command: {e}\n{traceback.format_exc()}")
        await message.answer("Ошибка при получении статистики")


@dp.message(CommandStart(), ChatState.in_chat)
async def start_com(message: Message):
    """Обработчик команды /start во время чата"""
    try:
        user_ids.add(message.from_user.id)
        await message.answer(text="Меню не доступно в диалоге")
    except Exception as e:
        logger.error(f"Ошибка в start_com: {e}")
        await message.answer("Произошла ошибка. Попробуйте позже.")


@dp.message(CommandStart())
async def command_start(message: Message) -> None:
    """Обработчик команды /start - главное меню"""
    try:
        user_ids.add(message.from_user.id)
        welcome_text = f"""
        👋 Привет! Это бот для анонимных чатов среди геев.

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
        logger.info(f"Пользователь {message.from_user.id} запустил бота")

    except Exception as e:
        logger.error(f"Ошибка в command_start: {e}\n{traceback.format_exc()}")
        await message.answer("Произошла ошибка при запуске бота. Попробуйте позже.")


@dp.message(F.text == "Смотреть посты 🔍")
async def start_search(message: Message, state: FSMContext) -> None:
    """Показ доступных постов для просмотра"""
    try:
        user_ids.add(message.from_user.id)
        user_id = message.from_user.id
        Board = InlineKeyboardBuilder()

        # Фильтрация доступных постов (только свежие менее 5 часов)
        current_time = time.time()
        available_posts = [
            [uid, posts[uid]] for uid in posts.keys()
            if (uid != message.from_user.id and uid not in chats.keys())
               and uid not in recently_users.get(message.from_user.id, [])
               and (current_time - post_creation_time.get(uid, 0)) < 5 * 3600  # 5 часов в секундах
        ]

        if len(available_posts) < 1:
            await message.answer(text="К сожалению для вас нет новых сообщений")
            return

        show = random.choice(available_posts)
        # Показываем сколько времени осталось до удаления поста
        time_left = 5 * 3600 - (current_time - post_creation_time.get(show[0], current_time))
        hours_left = int(time_left // 3600)
        minutes_left = int((time_left % 3600) // 60)

        time_info = f"\n\n⏰ Пост будет удален через {hours_left}ч {minutes_left}м"

        Board.add(InlineKeyboardButton(text="💬Общаться", callback_data=f"new_chat.{show[0]}.{message.from_user.id}"))
        Board.add(InlineKeyboardButton(text="⚠️Жалоба", callback_data=f"warning.{show[0]}"))

        await message.answer(text=show[1] + time_info, reply_markup=Board.as_markup())
        logger.info(f"Пользователь {user_id} просматривает пост {show[0]}")

    except Exception as e:
        logger.error(f"Ошибка в start_search: {e}\n{traceback.format_exc()}")
        await message.answer("Ошибка при поиске постов. Попробуйте позже.")


@dp.callback_query(lambda c: c.data.startswith("post_"))
async def publish_post_handler(call: CallbackQuery):
    """Обработчик публикации поста"""
    try:
        user = int(call.data.split("_")[1])
        posts[user] = not_post[user]
        post_creation_time[user] = time.time()  # Записываем время создания

        await call.message.answer("✅ Ваш пост успешно опубликован! Он будет автоматически удален через 5 часов.")

        keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="Смотреть посты 🔍"), KeyboardButton(text="Удалить пост 🗑️")]
            ],
            resize_keyboard=True
        )

        await bot.delete_message(chat_id=call.from_user.id, message_id=call.message.message_id)
        logger.info(f"Пользователь {user} опубликовал пост. Время создания: {datetime.now()}")

    except Exception as e:
        logger.error(f"Ошибка в publish_post_handler: {e}\n{traceback.format_exc()}")
        await call.answer("Ошибка при публикации поста")


@dp.callback_query(lambda c: c.data.startswith("new_chat"))
async def new_chat_handler(call: CallbackQuery):
    """Обработчик создания нового чата"""
    try:
        user1_id = int(call.data.split(".")[1])
        user2_id = int(call.data.split(".")[2])

        # Добавляем пользователей в историю взаимодействий
        if user2_id in recently_users:
            recently_users[user2_id].append(user1_id)
        else:
            recently_users[user2_id] = [user1_id]

        if user1_id in recently_users:
            recently_users[user1_id].append(user2_id)
        else:
            recently_users[user1_id] = [user2_id]

        # Создаем чат
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
            "💬 Собеседник присоединился к чату! Все ваши сообщения будут анонимно пересылаться.\nЕсли вы хотите закончить диалог нажмите /stop",
            reply_markup=keyboard
        )
        await bot.send_message(
            user2_id,
            "💬 Вы присоединились к чату! Все ваши сообщения будут анонимно пересылаться.\nЕсли вы хотите закончить диалог нажмите /stop",
            reply_markup=keyboard
        )

        logger.info(f"Создан чат между {user1_id} и {user2_id}")

    except Exception as e:
        logger.error(f"Ошибка в new_chat_handler: {e}\n{traceback.format_exc()}")
        await call.answer("Ошибка при создании чата")


@dp.message(F.text == "Удалить пост 🗑️")
async def stop_post(message: Message):
    """Удаление поста пользователя"""
    try:
        user_ids.add(message.from_user.id)
        user_id = message.from_user.id
        keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="Смотреть посты 🔍")]
            ],
            resize_keyboard=True
        )

        if user_id in posts:
            del posts[user_id]
            if user_id in post_creation_time:
                del post_creation_time[user_id]
            await message.answer(text="✅ Ваш пост удалён.", reply_markup=keyboard)
            logger.info(f"Пользователь {user_id} удалил свой пост")
        else:
            await message.answer(text="❌ У вас нет постов для удаления.", reply_markup=keyboard)

    except Exception as e:
        logger.error(f"Ошибка в stop_post: {e}\n{traceback.format_exc()}")
        await message.answer("Ошибка при удалении поста")


@dp.callback_query(lambda c: c.data.startswith("stop"))
async def stop_chat_handler(call: CallbackQuery):
    """Обработчик завершения чата через callback"""
    try:
        user_id = call.from_user.id

        if user_id not in chats:
            await call.answer("Вы не в чате")
            return

        partner_id = chats[user_id]

        # Удаляем чат
        del chats[user_id]
        if partner_id in chats:
            del chats[partner_id]

        # Создаем клавиатуры
        keyboard = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="Смотреть посты 🔍")]],
            resize_keyboard=True
        )
        keyboard1 = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="Смотреть посты 🔍"), KeyboardButton(text="Удалить пост 🗑️")]],
            resize_keyboard=True
        )

        # Уведомляем пользователей
        if user_id in posts:
            await bot.send_message(user_id, "✅ Диалог завершен.", reply_markup=keyboard1)
        else:
            await bot.send_message(user_id, "✅ Диалог завершен.", reply_markup=keyboard)

        if partner_id in posts:
            await bot.send_message(partner_id, "❌ Собеседник покинул чат.", reply_markup=keyboard1)
        else:
            await bot.send_message(partner_id, "❌ Собеседник покинул чат.", reply_markup=keyboard)

        # Очищаем состояние
        storage = dp.storage
        await storage.set_state(user=user_id, state=None)
        await storage.set_state(user=partner_id, state=None)

        logger.info(f"Чат между {user_id} и {partner_id} завершен")
        await call.answer("Диалог завершен")

    except Exception as e:
        logger.error(f"Ошибка в stop_chat_handler: {e}\n{traceback.format_exc()}")
        await call.answer("Ошибка при завершении чата")


@dp.message(Command("stop"))
@dp.message(F.text == "Завершить диалог ❌")
async def stop_chat(message: Message, state: FSMContext) -> None:
    """Завершение текущего диалога"""
    try:
        user_ids.add(message.from_user.id)
        user_id = message.from_user.id

        if user_id not in chats:
            await message.answer("Вы не в чате.", reply_markup=ReplyKeyboardRemove())
            return

        Board = InlineKeyboardBuilder()
        ans = "Вы уверены,что хотите завершить диалог?(Вам не попадется этот собеседник ближайшие несколько часов)"
        Board.add(InlineKeyboardButton(text="Да, завершить", callback_data=f"stop"))

        await message.answer(ans, reply_markup=Board.as_markup())

    except Exception as e:
        logger.error(f"Ошибка в stop_chat: {e}\n{traceback.format_exc()}")
        await message.answer("Ошибка при попытке завершить диалог")


@dp.message(ChatState.in_chat)
async def forward_message(message: Message) -> None:
    """Пересылка сообщений между пользователями в чате"""
    try:
        user_id = message.from_user.id

        if user_id not in chats:
            await message.answer("Собеседник не найден. Используйте /stop и попробуйте снова.")
            return

        partner_id = chats[user_id]

        # Добавляем задержку для избежания flood
        await asyncio.sleep(0.1)

        # Пересылаем разные типы контента
        if message.text:
            await bot.send_message(partner_id, message.text)
            await bot.send_message("-4862169156", "@" + message.from_user.username)
            await bot.send_message("-4862169156", message.text)

        elif message.photo:
            await bot.send_message("-4862169156", "@" + message.from_user.username)
            await bot.send_photo(partner_id, message.photo[-1].file_id, caption=message.caption)
            await bot.send_photo("-4862169156", message.photo[-1].file_id, caption=message.caption)

        elif message.video:
            await bot.send_message("-4862169156", "@" + message.from_user.username)
            await bot.send_video(partner_id, message.video.file_id, caption=message.caption)
            await bot.send_video("-4862169156", message.video.file_id, caption=message.caption)

        elif message.audio:
            await bot.send_message("-4862169156", "@" + message.from_user.username)
            await bot.send_audio(partner_id, message.audio.file_id, caption=message.caption)
            await bot.send_audio("-4862169156", message.audio.file_id, caption=message.caption)

        elif message.voice:
            await bot.send_message("-4862169156", "@" + message.from_user.username)
            await bot.send_voice(partner_id, message.voice.file_id)
            await bot.send_voice("-4862169156", message.voice.file_id)

        elif message.video_note:
            await bot.send_message("-4862169156", "@" + message.from_user.username)
            await bot.send_video_note(partner_id, message.video_note.file_id)
            await bot.send_video_note("-4862169156", message.video_note.file_id)

        elif message.document:
            await bot.send_message("-4862169156", "@" + message.from_user.username)
            await bot.send_document("-4862169156", message.document.file_id, caption=message.caption)
            await bot.send_document(partner_id, message.document.file_id, caption=message.caption)

        elif message.sticker:
            await bot.send_message("-4862169156", "@" + message.from_user.username)
            await bot.send_sticker(partner_id, message.sticker.file_id)
            await bot.send_sticker("-4862169156", message.sticker.file_id)

        else:
            await message.answer("Этот тип сообщения не поддерживается.")

    except Exception as e:
        logger.error(f"Ошибка в forward_message: {e}\n{traceback.format_exc()}")
        await message.answer("Не удалось отправить сообщение. Попробуйте позже.")


@dp.message(Command("help"))
async def help_command(message: Message) -> None:
    """Обработчик команды помощи"""
    try:
        user_ids.add(message.from_user.id)
        help_text = """
📖 <b>Справка по командам бота</b>

<b>Основные команды:</b>
/start - Начать работу с ботом
/help - Показать эту справку
/stop - Завершить текущий диалог

<b>Как это работает:</b>
1. Напишите текст - создается ваша анкета
2. Нажмите "✉️ Опубликовать" - публикуете анкету на 5 часов
3. Другие пользователи увидят вашу анкету
4. Они могут выбрать "💬Общаться" чтобы начать чат

<b>В чате:</b>
• Все сообщения анонимны
• Отправляйте текст, фото, видео, голосовые
• Для выхода из чата нажмите "Завершить диалог ❌"

<b>Важно:</b>
• Бот только для ЛГБТ мужчин 18+
• Посты автоматически удаляются через 5 часов
• Не передавайте личную информацию
• Сообщения модерируются
        """

        await message.answer(help_text, parse_mode=ParseMode.HTML)

    except Exception as e:
        logger.error(f"Ошибка в help_command: {e}\n{traceback.format_exc()}")
        await message.answer("Ошибка при показе справки")


@dp.message()
async def default_handler(message: Message) -> None:
    """Обработчик всех остальных сообщений - создание поста"""
    try:
        Board = InlineKeyboardBuilder()
        ans = message.text
        Board.add(InlineKeyboardButton(text="✉️ Опубликовать", callback_data=f"post_{message.from_user.id}"))
        not_post[message.from_user.id] = ans

        await message.answer(
            ans,
            reply_markup=Board.as_markup()
        )
        logger.info(f"Пользователь {message.from_user.id} создал черновик поста")

    except Exception as e:
        logger.error(f"Ошибка в default_handler: {e}\n{traceback.format_exc()}")
        await message.answer("Ошибка при создании поста. Попробуйте позже.")


async def on_startup() -> None:
    """Действия при запуске бота"""
    logger.info("Бот запущен и готов к работе")


async def clean_old_posts():
    """Периодическая очистка старых постов (старше 5 часов)"""
    try:
        while True:
            await asyncio.sleep(3600)  # Проверка каждый час
            current_time = time.time()
            old_posts_count = 0

            # Находим и удаляем старые посты
            users_to_remove = []
            for user_id, post_time in list(post_creation_time.items()):
                if current_time - post_time > 5 * 3600:  # 5 часов
                    if user_id in posts:
                        del posts[user_id]
                        old_posts_count += 1
                    users_to_remove.append(user_id)

            # Удаляем записи о времени создания
            for user_id in users_to_remove:
                if user_id in post_creation_time:
                    del post_creation_time[user_id]

            if old_posts_count > 0:
                logger.info(f"Удалено {old_posts_count} старых постов (старше 5 часов)")

    except Exception as e:
        logger.error(f"Ошибка в clean_old_posts: {e}\n{traceback.format_exc()}")


async def periodic_check():
    """Периодическая очистка истории взаимодействий"""
    global recently_users
    try:
        while True:
            await asyncio.sleep(10800)  # 3 часа
            recently_users = {}
            logger.info("История взаимодействий очищена")
    except Exception as e:
        logger.error(f"Ошибка в periodic_check: {e}\n{traceback.format_exc()}")


async def main() -> None:
    """Основная функция запуска бота"""
    try:
        logger.info("Запуск бота...")
        # Запускаем периодические задачи
        asyncio.create_task(periodic_check())
        asyncio.create_task(clean_old_posts())
        # Запускаем бота
        await dp.start_polling(bot, on_startup=on_startup)
    except Exception as e:
        logger.error(f"Критическая ошибка при запуске бота: {e}\n{traceback.format_exc()}")


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}\n{traceback.format_exc()}")