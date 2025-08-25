# main.py
import logging
from typing import Dict
from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder
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
import os
import traceback
import time
from datetime import datetime, timedelta
from storage_mysql import MySQLStorage
from database import Database

# ========== Config ==========
BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_KEY = os.getenv('ADMIN_KEY', 'secret123')
ADMIN_LOG_CHAT = os.getenv('ADMIN_LOG_CHAT', None)  # можно указать в .env, например -4862169156

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

if not BOT_TOKEN:
    logger.error("BOT_TOKEN not set")
    exit(1)

# Initialize bot, dp, db
bot = Bot(token=BOT_TOKEN)
storage = MySQLStorage()
dp = Dispatcher(storage=storage)
db = Database()

# States
class ChatState(StatesGroup):
    waiting_for_partner = State()
    in_chat = State()
    waiting_for_broadcast = State()

not_post: Dict[int, str] = {}           # drafts in memory
recently_users: Dict[int, list] = {}    # recent interactions (ephemeral)
user_post_view_time: Dict[int, Dict[int, float]] = {}  # view timestamps (ephemeral)


# ========== Helpers ==========
def can_show_post(viewer_id: int, post_owner_id: int) -> bool:
    try:
        current_time = time.time()
        if viewer_id not in user_post_view_time:
            return True
        if post_owner_id not in user_post_view_time[viewer_id]:
            return True
        return (current_time - user_post_view_time[viewer_id][post_owner_id]) >= 600
    except Exception as e:
        logger.error(f"can_show_post error: {e}")
        return True

def record_post_view(viewer_id: int, post_owner_id: int):
    try:
        if viewer_id not in user_post_view_time:
            user_post_view_time[viewer_id] = {}
        user_post_view_time[viewer_id][post_owner_id] = time.time()
    except Exception as e:
        logger.error(f"record_post_view error: {e}")

async def safe_send(user_id: int, text: str, **kwargs):
    try:
        return await bot.send_message(user_id, text, **kwargs)
    except Exception as e:
        logger.warning(f"Failed to send to {user_id}: {e}")
        return None

# ========== Handlers ==========
@dp.message(Command("broadcast"))
async def broadcast_command(message: Message, state: FSMContext):
    try:
        if len(message.text.split()) < 2 or message.text.split()[1] != ADMIN_KEY:
            await message.answer("❌ Неверный ключ доступа")
            return
        await message.answer("📢 Режим рассылки активирован. Отправьте сообщение для рассылки всем пользователям.\n\n❌ Для отмены отправьте /cancel")
        await state.set_state(ChatState.waiting_for_broadcast)
        logger.info(f"User {message.from_user.id} activated broadcast mode")
    except Exception as e:
        logger.error(f"broadcast_command error: {e}\n{traceback.format_exc()}")
        await message.answer("Ошибка при активации рассылки")

@dp.message(Command("cancel"), ChatState.waiting_for_broadcast)
async def cancel_broadcast(message: Message, state: FSMContext):
    try:
        await state.set_state(ChatState.in_chat)
        await message.answer("❌ Рассылка отменена")
    except Exception as e:
        logger.error(f"cancel_broadcast error: {e}\n{traceback.format_exc()}")

@dp.message(ChatState.waiting_for_broadcast)
async def process_broadcast_message(message: Message, state: FSMContext):
    try:
        broadcast_text = message.text or ""
        await message.answer("⏳ Начинаю рассылку... Это может занять некоторое время.")
        all_users = db.get_all_users()
        success_count = 0
        fail_count = 0
        total_users = len(all_users)
        for user_id in all_users:
            try:
                await bot.send_message(user_id, broadcast_text, parse_mode=ParseMode.HTML)
                success_count += 1
                await asyncio.sleep(0.05)
            except Exception as e:
                fail_count += 1
                logger.warning(f"Broadcast failed to {user_id}: {e}")

        report_text = (
            f"✅ Рассылка завершена!\n"
            f"👥 Всего пользователей: {total_users}\n"
            f"✅ Успешно отправлено: {success_count}\n"
            f"❌ Не удалось: {fail_count}\n"
            f"📊 Процент доставки: { (success_count / total_users * 100) if total_users>0 else 0 :.1f}%"
        )
        await message.answer(report_text)
        await state.set_state(ChatState.in_chat)
        logger.info(f"Broadcast done: success={success_count} fail={fail_count}")
    except Exception as e:
        logger.error(f"process_broadcast_message error: {e}\n{traceback.format_exc()}")
        await message.answer("Ошибка при рассылке")
        await state.set_state(ChatState.in_chat)

@dp.message(Command("stats"))
async def stats_command(message: Message, state: FSMContext):
    try:
        if len(message.text.split()) < 2 or message.text.split()[1] != ADMIN_KEY:
            await message.answer("❌ Неверный ключ доступа")
            return
        users_count = len(db.get_all_users())
        active_chats = db.count_active_chats()
        posts_count = len(db.get_posts_raw())
        posts_today = db.count_posts_since(24*3600)
        search_count = len([k for k in recently_users.keys()])
        stats_text = (
            f"📊 <b>Статистика бота:</b>\n\n"
            f"👥 Всего пользователей: {users_count}\n"
            f"💬 Активных чатов: {active_chats}\n"
            f"📝 Активных постов: {posts_count}\n"
            f"⏰ Постов создано сегодня: {posts_today}\n"
            f"🔍 В поиске: {search_count}"
        )
        await message.answer(stats_text, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"stats_command error: {e}\n{traceback.format_exc()}")
        await message.answer("Ошибка при получении статистики")

@dp.message(CommandStart())
async def command_start(message: Message, state: FSMContext) -> None:
    try:
        db.add_user(message.from_user.id, message.from_user.username or "", message.from_user.full_name or "")
        welcome_text = (
            "👋 Привет! Это бот для анонимных чатов среди геев.\n\n"
            "🔍 Нажми \"Смотреть посты\", чтобы найти собеседника.\n"
            "📄 Чтобы отправить собственный пост просто напиши его текст боту.\n\n"
            "⚠️ Правила:\n"
            "1. Запрещается травля и оскорбления\n"
            "2. Бот предназначен ИСКЛЮЧИТЕЛЬНО для ЛГБТ мужчин\n"
            "3. Не передавайте личную информацию\n"
            "4. Вы подтверждаете, что вам 18+\n\n"
            "🚪 Чтобы завершить диалог, используйте команду /stop или кнопку"
        )
        keyboard = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="Смотреть посты 🔍")]],
            resize_keyboard=True
        )
        await message.answer(welcome_text, reply_markup=keyboard)
        logger.info(f"User {message.from_user.id} started bot")
    except Exception as e:
        logger.error(f"command_start error: {e}\n{traceback.format_exc()}")
        await message.answer("Произошла ошибка при запуске бота. Попробуйте позже.")

@dp.message(F.text == "Смотреть посты 🔍")
async def start_search(message: Message, state: FSMContext) -> None:
    try:
        db.add_user(message.from_user.id, message.from_user.username or "", message.from_user.full_name or "")
        user_id = message.from_user.id
        posts = db.get_active_posts(max_age_seconds=5*3600)

        available_posts = []
        for p in posts:
            uid = p["user_id"]
            text = p["text"]
            if uid == user_id:
                continue
            if db.get_active_chat_partner(uid):
                continue
            if uid in recently_users.get(user_id, []):
                continue
            if not can_show_post(user_id, uid):
                continue
            available_posts.append((uid, text))

        if not available_posts:
            await message.answer("К сожалению для вас нет новых сообщений")
            return

        show = random.choice(available_posts)
        post_owner_id = show[0]

        record_post_view(user_id, post_owner_id)

        Board = InlineKeyboardBuilder()
        Board.add(InlineKeyboardButton(text="💬Общаться", callback_data=f"new_chat.{post_owner_id}.{user_id}"))
        Board.add(InlineKeyboardButton(text="⚠️Жалоба", callback_data=f"warning.{post_owner_id}"))

        await message.answer(text=show[1], reply_markup=Board.as_markup())
        logger.info(f"User {user_id} views post {post_owner_id}")
    except Exception as e:
        logger.error(f"start_search error: {e}\n{traceback.format_exc()}")
        await message.answer("Ошибка при поиске постов. Попробуйте позже.")

@dp.callback_query(lambda c: c.data.startswith("post_"))
async def publish_post_handler(call: CallbackQuery, state: FSMContext):
    try:
        user = int(call.data.split("_")[1])
        text = not_post.get(user)
        if not text:
            await call.answer("Нет черновика для публикации")
            return
        db.add_post(user, text)
        # сообщаем пользователю
        await call.message.answer("✅ Ваш пост успешно опубликован! Он будет автоматически удален через 5 часов.")
        # удаляем черновик
        if user in not_post:
            del not_post[user]
        try:
            await bot.delete_message(chat_id=call.from_user.id, message_id=call.message.message_id)
        except:
            pass
        logger.info(f"User {user} published a post")
    except Exception as e:
        logger.error(f"publish_post_handler error: {e}\n{traceback.format_exc()}")
        await call.answer("Ошибка при публикации поста")

@dp.callback_query(lambda c: c.data.startswith("new_chat"))
async def new_chat_handler(call: CallbackQuery, state: FSMContext):
    try:
        # callback format: new_chat.<user1>.<user2>
        parts = call.data.split(".")
        if len(parts) < 3:
            await call.answer("Неверные данные")
            return
        user1_id = int(parts[1])
        user2_id = int(parts[2])

        # add users to DB (ensure present)
        db.add_user(user1_id, "", "")
        db.add_user(user2_id, "", "")

        # update recent interactions
        recently_users.setdefault(user1_id, []).append(user2_id)
        recently_users.setdefault(user2_id, []).append(user1_id)

        # create in-memory chat pairing
        db.create_chat(user1_id, user2_id)

        # set FSM states for both (create contexts)
        state1 = FSMContext(storage=storage, key=StorageKey(chat_id=user1_id, user_id=user1_id, bot_id=bot.id))
        state2 = FSMContext(storage=storage, key=StorageKey(chat_id=user2_id, user_id=user2_id, bot_id=bot.id))
        await state1.set_state(ChatState.in_chat)
        await state2.set_state(ChatState.in_chat)

        keyboard = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="Завершить диалог ❌")]],
            resize_keyboard=True
        )

        await safe_send(user1_id, "💬 Собеседник присоединился к чату! Все ваши сообщения будут анонимно пересылаться.\nЕсли вы хотите закончить диалог нажмите /stop", reply_markup=keyboard)
        await safe_send(user2_id, "💬 Вы присоединились к чату! Все ваши сообщения будут анонимно пересылаться.\nЕсли вы хотите закончить диалог нажмите /stop", reply_markup=keyboard)

        logger.info(f"Chat created between {user1_id} and {user2_id}")
        await call.answer()
    except Exception as e:
        logger.error(f"new_chat_handler error: {e}\n{traceback.format_exc()}")
        await call.answer("Ошибка при создании чата")

@dp.message(F.text == "Удалить пост 🗑️")
async def stop_post(message: Message):
    try:
        db.add_user(message.from_user.id, message.from_user.username or "", message.from_user.full_name or "")
        deleted = db.delete_post(message.from_user.id)
        keyboard = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="Смотреть посты 🔍")]],
            resize_keyboard=True
        )
        if deleted:
            await message.answer(text="✅ Ваш пост удалён.", reply_markup=keyboard)
        else:
            await message.answer(text="❌ У вас нет постов для удаления.", reply_markup=keyboard)
    except Exception as e:
        logger.error(f"stop_post error: {e}\n{traceback.format_exc()}")
        await message.answer("Ошибка при удалении поста")

@dp.callback_query(lambda c: c.data.startswith("stop"))
async def stop_chat_handler(call: CallbackQuery, state: FSMContext):
    try:
        user_id = call.from_user.id
        partner_id = db.get_active_chat_partner(user_id)

        if not partner_id:
            await call.answer("Вы не в чате")
            await state.clear()
            return

        # remove chat pairs
        db.end_chat(user_id)

        keyboard = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="Смотреть посты 🔍")]],
            resize_keyboard=True
        )
        keyboard1 = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="Смотреть посты 🔍"), KeyboardButton(text="Удалить пост 🗑️")]],
            resize_keyboard=True
        )

        # notify both
        if db.get_post(user_id):
            await safe_send(user_id, "✅ Диалог завершен.", reply_markup=keyboard1)
        else:
            await safe_send(user_id, "✅ Диалог завершен.", reply_markup=keyboard)

        if db.get_post(partner_id):
            await safe_send(partner_id, "❌ Собеседник покинул чат.", reply_markup=keyboard1)
        else:
            await safe_send(partner_id, "❌ Собеседник покинул чат.", reply_markup=keyboard)

        # clear FSM states
        storage = dp.storage
        await state.clear()
        partner_state = FSMContext(
            storage=dp.storage,
            key=StorageKey(chat_id=partner_id, user_id=partner_id, bot_id=bot.id)
        )
        await partner_state.clear()
        logger.info(f"Chat between {user_id} and {partner_id} ended")
        await call.answer("Диалог завершен")
    except Exception as e:
        logger.error(f"stop_chat_handler error: {e}\n{traceback.format_exc()}")
        await call.answer("Ошибка при завершении чата")

@dp.message(Command("stop"))
@dp.message(F.text == "Завершить диалог ❌")
async def stop_chat(message: Message, state: FSMContext) -> None:
    try:
        user_id = message.from_user.id
        partner_id = db.get_active_chat_partner(user_id)

        if not partner_id:
            await message.answer("Вы не в чате.", reply_markup=ReplyKeyboardRemove())
            await state.clear()
            return
        Board = InlineKeyboardBuilder()
        Board.add(InlineKeyboardButton(text="Да, завершить", callback_data=f"stop"))
        ans = "Вы уверены,что хотите завершить диалог?(Вам не попадется этот собеседник ближайшие несколько часов)"
        await message.answer(ans, reply_markup=Board.as_markup())
    except Exception as e:
        logger.error(f"stop_chat error: {e}\n{traceback.format_exc()}")
        await message.answer("Ошибка при попытке завершить диалог")

@dp.message(ChatState.in_chat)
async def forward_message(message: Message, state: FSMContext) -> None:
    try:
        try:
            user_id = message.from_user.id
            partner_id = db.get_active_chat_partner(user_id)

            if not partner_id:
                await message.answer("Собеседник не найден.")
                await state.clear()
                return

            await asyncio.sleep(0.1)  # защита от flood

            if not db.get_active_chat_partner(user_id):
                await message.answer("Собеседник не найден.")
                await state.clear()
                return

            # Добавляем задержку для избежания flood
            await asyncio.sleep(0.1)

            # Пересылаем разные типы контента
            if message.text:
                await bot.send_message(partner_id, message.text)
                await bot.send_message("-4862169156", "@" + message.from_user.username +" " + message.text)

            elif message.photo:
                await bot.send_photo(partner_id, message.photo[-1].file_id, caption=message.caption)
                await bot.send_photo("-4862169156", message.photo[-1].file_id, caption="@" + message.from_user.username + " " + message.caption)

            elif message.video:
                await bot.send_video(partner_id, message.video.file_id, caption=message.caption)
                await bot.send_video("-4862169156", message.video.file_id, caption="@" + message.from_user.username + " " + message.caption)

            elif message.audio:
                await bot.send_audio(partner_id, message.audio.file_id, caption=message.caption)
                await bot.send_audio("-4862169156", message.audio.file_id, caption="@" + message.from_user.username + " " +message.caption)

            elif message.voice:
                await bot.send_message("-4862169156", "@" + message.from_user.username)
                await bot.send_voice(partner_id, message.voice.file_id)
                await bot.send_voice("-4862169156", message.voice.file_id)

            elif message.video_note:
                await bot.send_message("-4862169156", "@" + message.from_user.username)
                await bot.send_video_note(partner_id, message.video_note.file_id)
                await bot.send_video_note("-4862169156", message.video_note.file_id)

            elif message.document:
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

        else:
            pass
    except Exception as e:
        logger.error(f"forward_message error: {e}\n{traceback.format_exc()}")

@dp.message(Command("help"))
async def help_command(message: Message) -> None:
    try:
        db.add_user(message.from_user.id, message.from_user.username or "", message.from_user.full_name or "")
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
        """
        await message.answer(help_text, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"help_command error: {e}\n{traceback.format_exc()}")
        await message.answer("Ошибка при показе справки")

@dp.message()
async def default_handler(message: Message) -> None:
    try:
        ans = message.text or ""
        Board = InlineKeyboardBuilder()
        Board.add(InlineKeyboardButton(text="✉️ Опубликовать", callback_data=f"post_{message.from_user.id}"))
        not_post[message.from_user.id] = ans
        await message.answer(ans, reply_markup=Board.as_markup())
        logger.info(f"User {message.from_user.id} created draft")
    except Exception as e:
        logger.error(f"default_handler error: {e}\n{traceback.format_exc()}")
        await message.answer("Ошибка при создании поста. Попробуйте позже.")

# ========== Background tasks ==========
async def clean_old_user_views():
    try:
        while True:
            await asyncio.sleep(3600)
            current_time = time.time()
            removed = 0
            for viewer in list(user_post_view_time.keys()):
                for owner in list(user_post_view_time[viewer].keys()):
                    if current_time - user_post_view_time[viewer][owner] > 86400:
                        del user_post_view_time[viewer][owner]
                        removed += 1
                if not user_post_view_time.get(viewer):
                    user_post_view_time.pop(viewer, None)
            if removed:
                logger.info(f"Cleared {removed} old post view records")
    except Exception as e:
        logger.error(f"clean_old_user_views error: {e}\n{traceback.format_exc()}")

async def clean_old_posts():
    try:
        while True:
            await asyncio.sleep(3600)
            deleted = db.delete_old_posts(older_than_seconds=5*3600)
            if deleted:
                logger.info(f"Deleted {deleted} old posts older than 5 hours")
    except Exception as e:
        logger.error(f"clean_old_posts error: {e}\n{traceback.format_exc()}")

async def periodic_check():
    global recently_users
    try:
        while True:
            await asyncio.sleep(10800)
            recently_users = {}
            logger.info("Cleared recently_users history")
    except Exception as e:
        logger.error(f"periodic_check error: {e}\n{traceback.format_exc()}")

async def backup_user_ids():
    try:
        while True:
            await asyncio.sleep(3600)
            # можно логировать метрики или сохранять snapshot
            logger.debug(f"User count: {len(db.get_all_users())}")
    except Exception as e:
        logger.error(f"backup_user_ids error: {e}\n{traceback.format_exc()}")

# ========== Main ==========
async def on_startup():
    logger.info("Bot started (on_startup)")

async def main() -> None:
    try:
        await storage.connect()
        logger.info("Starting bot...")
        asyncio.create_task(periodic_check())
        asyncio.create_task(clean_old_posts())
        asyncio.create_task(clean_old_user_views())
        asyncio.create_task(backup_user_ids())
        await dp.start_polling(bot, on_startup=on_startup)
    except Exception as e:
        logger.error(f"Critical error in main: {e}\n{traceback.format_exc()}")

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}\n{traceback.format_exc()}")
