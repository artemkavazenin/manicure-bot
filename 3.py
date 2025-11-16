"""
🎨 Telegram-бот для записи на маникюр
Профессиональный бот с красивым интерфейсом и полным функционалом
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List
import sqlite3

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message, 
    CallbackQuery, 
    InlineKeyboardMarkup, 
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove
)

# ================================
# 🎯 КОНФИГУРАЦИЯ
# ================================

BOT_TOKEN = "8583432941:AAHA0aaAtDwCsj_Agrn6e1jDIsSNzirde6c"  # 👈 Замените на токен вашего бота
ADMIN_IDS = [8485520947]  # 👈 Замените на ваш Telegram ID

# ================================
# 🗄️ БАЗА ДАННЫХ
# ================================

class Database:
    def __init__(self, db_file: str = "manicure.db"):
        self.db_file = db_file
        self.init_db()
    
    def init_db(self):
        """Инициализация базы данных"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        # Таблица клиентов
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS clients (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                phone TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Таблица записей
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS appointments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                service TEXT,
                date TEXT,
                time TEXT,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES clients (user_id)
            )
        """)
        
        conn.commit()
        conn.close()
    
    def add_client(self, user_id: int, username: str, full_name: str, phone: str):
        """Добавление клиента"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO clients (user_id, username, full_name, phone)
            VALUES (?, ?, ?, ?)
        """, (user_id, username, full_name, phone))
        conn.commit()
        conn.close()
    
    def add_appointment(self, user_id: int, service: str, date: str, time: str):
        """Добавление записи"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO appointments (user_id, service, date, time)
            VALUES (?, ?, ?, ?)
        """, (user_id, service, date, time))
        conn.commit()
        conn.close()
    
    def get_appointments_by_date(self, date: str) -> List[str]:
        """Получение занятых времен на дату"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT time FROM appointments 
            WHERE date = ? AND status = 'pending'
        """, (date,))
        times = [row[0] for row in cursor.fetchall()]
        conn.close()
        return times
    
    def get_user_appointments(self, user_id: int) -> List[tuple]:
        """Получение записей пользователя"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, service, date, time, status 
            FROM appointments 
            WHERE user_id = ? 
            ORDER BY date, time
        """, (user_id,))
        appointments = cursor.fetchall()
        conn.close()
        return appointments
    
    def cancel_appointment(self, appointment_id: int):
        """Отмена записи"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE appointments SET status = 'cancelled'
            WHERE id = ?
        """, (appointment_id,))
        conn.commit()
        conn.close()
    
    def get_all_appointments(self) -> List[tuple]:
        """Получение всех записей (для админа)"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT a.id, c.full_name, c.phone, a.service, a.date, a.time, a.status
            FROM appointments a
            JOIN clients c ON a.user_id = c.user_id
            ORDER BY a.date, a.time
        """)
        appointments = cursor.fetchall()
        conn.close()
        return appointments

# ================================
# 📋 СОСТОЯНИЯ FSM
# ================================

class BookingStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_phone = State()
    choosing_service = State()
    choosing_date = State()
    choosing_time = State()

# ================================
# 💅 УСЛУГИ И РАСПИСАНИЕ
# ================================

SERVICES = {
    "classic": {"name": "💅 Классический маникюр", "duration": 60, "price": 1500},
    "hardware": {"name": "✨ Аппаратный маникюр", "duration": 60, "price": 1800},
    "gel": {"name": "💎 Гель-лак", "duration": 90, "price": 2500},
    "design": {"name": "🎨 Дизайн ногтей", "duration": 120, "price": 3000},
    "complex": {"name": "👑 Комплексный уход", "duration": 150, "price": 4000},
}

WORKING_HOURS = ["10:00", "11:30", "13:00", "14:30", "16:00", "17:30", "19:00"]

# ================================
# 🎨 КЛАВИАТУРЫ
# ================================

def get_main_keyboard() -> ReplyKeyboardMarkup:
    """Главное меню"""
    keyboard = [
        [KeyboardButton(text="📅 Записаться")],
        [KeyboardButton(text="📋 Мои записи"), KeyboardButton(text="ℹ️ Информация")],
        [KeyboardButton(text="📞 Контакты")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_admin_keyboard() -> ReplyKeyboardMarkup:
    """Админ-меню"""
    keyboard = [
        [KeyboardButton(text="📅 Записаться")],
        [KeyboardButton(text="📋 Мои записи"), KeyboardButton(text="ℹ️ Информация")],
        [KeyboardButton(text="📞 Контакты")],
        [KeyboardButton(text="👑 АДМИН-ПАНЕЛЬ")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_services_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора услуг"""
    buttons = []
    for key, service in SERVICES.items():
        buttons.append([InlineKeyboardButton(
            text=f"{service['name']} - {service['price']}₽",
            callback_data=f"service_{key}"
        )])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_calendar_keyboard(selected_month: int = None) -> InlineKeyboardMarkup:
    """Календарь для выбора даты"""
    now = datetime.now()
    if selected_month:
        current_date = datetime(now.year, selected_month, 1)
    else:
        current_date = now
    
    buttons = []
    buttons.append([InlineKeyboardButton(
        text=f"📅 {current_date.strftime('%B %Y')}",
        callback_data="ignore"
    )])
    
    # Дни недели
    weekdays = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    buttons.append([InlineKeyboardButton(text=day, callback_data="ignore") for day in weekdays])
    
    # Генерация дней месяца
    month_start = current_date.replace(day=1)
    start_weekday = month_start.weekday()
    days_in_month = (month_start.replace(month=month_start.month % 12 + 1) - timedelta(days=1)).day if month_start.month < 12 else 31
    
    week = [InlineKeyboardButton(text=" ", callback_data="ignore")] * start_weekday
    
    for day in range(1, days_in_month + 1):
        date = current_date.replace(day=day)
        if date >= now.replace(hour=0, minute=0, second=0, microsecond=0):
            week.append(InlineKeyboardButton(
                text=str(day),
                callback_data=f"date_{date.strftime('%Y-%m-%d')}"
            ))
        else:
            week.append(InlineKeyboardButton(text="•", callback_data="ignore"))
        
        if len(week) == 7:
            buttons.append(week)
            week = []
    
    if week:
        while len(week) < 7:
            week.append(InlineKeyboardButton(text=" ", callback_data="ignore"))
        buttons.append(week)
    
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_services")])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_time_keyboard(date: str, booked_times: List[str]) -> InlineKeyboardMarkup:
    """Клавиатура выбора времени"""
    buttons = []
    row = []
    
    for i, time in enumerate(WORKING_HOURS):
        if time in booked_times:
            btn_text = f"❌ {time}"
            callback = "time_unavailable"
        else:
            btn_text = f"✅ {time}"
            callback = f"time_{time}"
        
        row.append(InlineKeyboardButton(text=btn_text, callback_data=callback))
        
        if (i + 1) % 2 == 0:
            buttons.append(row)
            row = []
    
    if row:
        buttons.append(row)
    
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_date")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# ================================
# 🤖 ИНИЦИАЛИЗАЦИЯ БОТА
# ================================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()
db = Database()

# ================================
# 🎯 ОБРАБОТЧИКИ КОМАНД
# ================================

@router.message(Command("start"))
async def cmd_start(message: Message):
    """Команда /start"""
    user_id = message.from_user.id
    is_admin = user_id in ADMIN_IDS
    
    keyboard = get_admin_keyboard() if is_admin else get_main_keyboard()
    
    welcome_text = f"""
✨ <b>Добро пожаловать в наш салон красоты!</b> ✨

Привет, {message.from_user.first_name}! 💅

Я помогу вам записаться на маникюр в удобное время.
У нас работают лучшие мастера, используются качественные материалы.

🎨 <b>Что я умею:</b>
• Записать вас на процедуру
• Показать ваши записи
• Ответить на вопросы
• Предоставить контакты

Выберите действие в меню ⬇️
    """
    
    if is_admin:
        welcome_text += "\n\n👑 <b>Вам доступна админ-панель</b>"
    
    await message.answer(welcome_text, parse_mode="HTML", reply_markup=keyboard)

@router.message(F.text == "📅 Записаться")
async def start_booking(message: Message, state: FSMContext):
    """Начало процесса записи"""
    await state.set_state(BookingStates.waiting_for_name)
    await message.answer(
        "🌸 <b>Отлично! Давайте начнем запись.</b>\n\n"
        "Как я могу к вам обращаться? Напишите ваше имя:",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardRemove()
    )

@router.message(BookingStates.waiting_for_name)
async def process_name(message: Message, state: FSMContext):
    """Обработка имени"""
    await state.update_data(full_name=message.text)
    await state.set_state(BookingStates.waiting_for_phone)
    await message.answer(
        f"Приятно познакомиться, {message.text}! 😊\n\n"
        "Напишите ваш номер телефона в формате:\n"
        "<code>+7 900 123 45 67</code>",
        parse_mode="HTML"
    )

@router.message(BookingStates.waiting_for_phone)
async def process_phone(message: Message, state: FSMContext):
    """Обработка телефона"""
    phone = message.text
    await state.update_data(phone=phone)
    
    # Сохраняем клиента в БД
    data = await state.get_data()
    db.add_client(
        user_id=message.from_user.id,
        username=message.from_user.username or "",
        full_name=data['full_name'],
        phone=phone
    )
    
    await state.set_state(BookingStates.choosing_service)
    await message.answer(
        "✨ <b>Замечательно! Теперь выберите услугу:</b>",
        parse_mode="HTML",
        reply_markup=get_services_keyboard()
    )

@router.callback_query(F.data.startswith("service_"))
async def process_service(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора услуги"""
    service_key = callback.data.split("_")[1]
    service = SERVICES[service_key]
    
    await state.update_data(service=service['name'], service_key=service_key)
    await state.set_state(BookingStates.choosing_date)
    
    await callback.message.edit_text(
        f"💅 <b>Вы выбрали:</b> {service['name']}\n"
        f"💰 <b>Стоимость:</b> {service['price']}₽\n"
        f"⏱ <b>Продолжительность:</b> {service['duration']} мин\n\n"
        f"📅 <b>Выберите удобную дату:</b>",
        parse_mode="HTML",
        reply_markup=get_calendar_keyboard()
    )
    await callback.answer()

@router.callback_query(F.data.startswith("date_"))
async def process_date(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора даты"""
    date = callback.data.split("_")[1]
    await state.update_data(date=date)
    await state.set_state(BookingStates.choosing_time)
    
    # Получаем занятые времена
    booked_times = db.get_appointments_by_date(date)
    
    date_obj = datetime.strptime(date, "%Y-%m-%d")
    formatted_date = date_obj.strftime("%d %B %Y")
    
    await callback.message.edit_text(
        f"📅 <b>Дата:</b> {formatted_date}\n\n"
        f"🕐 <b>Выберите удобное время:</b>\n"
        f"✅ - свободно  ❌ - занято",
        parse_mode="HTML",
        reply_markup=get_time_keyboard(date, booked_times)
    )
    await callback.answer()

@router.callback_query(F.data.startswith("time_"))
async def process_time(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора времени"""
    if callback.data == "time_unavailable":
        await callback.answer("⚠️ Это время уже занято", show_alert=True)
        return
    
    time = callback.data.split("_")[1]
    data = await state.get_data()
    
    # Сохраняем запись
    db.add_appointment(
        user_id=callback.from_user.id,
        service=data['service'],
        date=data['date'],
        time=time
    )
    
    date_obj = datetime.strptime(data['date'], "%Y-%m-%d")
    formatted_date = date_obj.strftime("%d %B %Y")
    
    await callback.message.edit_text(
        f"✅ <b>Отлично! Вы успешно записаны!</b>\n\n"
        f"👤 <b>Имя:</b> {data['full_name']}\n"
        f"📱 <b>Телефон:</b> {data['phone']}\n"
        f"💅 <b>Услуга:</b> {data['service']}\n"
        f"📅 <b>Дата:</b> {formatted_date}\n"
        f"🕐 <b>Время:</b> {time}\n\n"
        f"💌 Мы отправили вам подтверждение.\n"
        f"Ждем вас! До встречи! ✨",
        parse_mode="HTML"
    )
    
    is_admin = callback.from_user.id in ADMIN_IDS
    keyboard = get_admin_keyboard() if is_admin else get_main_keyboard()
    await callback.message.answer("Вернуться в главное меню:", reply_markup=keyboard)
    
    await state.clear()
    await callback.answer("🎉 Запись создана!")

@router.message(F.text == "📋 Мои записи")
async def my_appointments(message: Message):
    """Показать записи пользователя"""
    appointments = db.get_user_appointments(message.from_user.id)
    
    if not appointments:
        await message.answer(
            "📋 <b>У вас пока нет записей</b>\n\n"
            "Нажмите '📅 Записаться', чтобы создать новую запись!",
            parse_mode="HTML"
        )
        return
    
    text = "📋 <b>Ваши записи:</b>\n\n"
    
    for apt in appointments:
        apt_id, service, date, time, status = apt
        date_obj = datetime.strptime(date, "%Y-%m-%d")
        formatted_date = date_obj.strftime("%d %B %Y")
        
        status_emoji = "✅" if status == "pending" else "❌"
        status_text = "Активна" if status == "pending" else "Отменена"
        
        text += (
            f"{status_emoji} <b>Запись #{apt_id}</b>\n"
            f"💅 {service}\n"
            f"📅 {formatted_date} в {time}\n"
            f"📊 Статус: {status_text}\n\n"
        )
    
    await message.answer(text, parse_mode="HTML")

@router.message(F.text == "ℹ️ Информация")
async def info_command(message: Message):
    """Информация о салоне"""
    info_text = """
ℹ️ <b>Информация о нашем салоне</b>

🏢 <b>О нас:</b>
Мы - современный салон красоты с многолетним опытом.
Работаем только с премиальными материалами и проверенными брендами.

💅 <b>Наши услуги:</b>
"""
    for service in SERVICES.values():
        info_text += f"• {service['name']} - {service['price']}₽\n"
    
    info_text += """
⏰ <b>Время работы:</b>
Ежедневно с 10:00 до 20:00

🎁 <b>Акции:</b>
• Скидка 10% на первое посещение
• Накопительная система бонусов
• Специальные предложения по праздникам

✨ Ждем вас в нашем салоне!
    """
    
    await message.answer(info_text, parse_mode="HTML")

@router.message(F.text == "📞 Контакты")
async def contacts_command(message: Message):
    """Контакты салона"""
    contacts_text = """
📞 <b>Наши контакты</b>

📍 <b>Адрес:</b>
г. Москва, ул. Примерная, д. 1

📱 <b>Телефон:</b>
+7 (900) 123-45-67

📧 <b>Email:</b>
info@salon-beauty.ru

🌐 <b>Сайт:</b>
www.salon-beauty.ru

📲 <b>Социальные сети:</b>
• Instagram: @salon_beauty
• VK: vk.com/salon_beauty

🚇 <b>Как добраться:</b>
Метро "Примерная", выход 2
5 минут пешком

🅿️ Бесплатная парковка для клиентов
    """
    
    await message.answer(contacts_text, parse_mode="HTML")

@router.message(F.text == "👑 АДМИН-ПАНЕЛЬ")
async def admin_panel(message: Message):
    """Админ-панель"""
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔️ У вас нет доступа к админ-панели")
        return
    
    appointments = db.get_all_appointments()
    
    if not appointments:
        await message.answer("📋 <b>Записей пока нет</b>", parse_mode="HTML")
        return
    
    text = "👑 <b>АДМИН-ПАНЕЛЬ</b>\n\n📋 <b>Все записи:</b>\n\n"
    
    for apt in appointments:
        apt_id, name, phone, service, date, time, status = apt
        date_obj = datetime.strptime(date, "%Y-%m-%d")
        formatted_date = date_obj.strftime("%d.%m.%Y")
        
        status_emoji = "✅" if status == "pending" else "❌"
        
        text += (
            f"{status_emoji} <b>ID {apt_id}</b>\n"
            f"👤 {name}\n"
            f"📱 {phone}\n"
            f"💅 {service}\n"
            f"📅 {formatted_date} в {time}\n"
            f"{'─' * 30}\n\n"
        )
    
    # Разбиваем на части если слишком длинное
    if len(text) > 4000:
        parts = [text[i:i+4000] for i in range(0, len(text), 4000)]
        for part in parts:
            await message.answer(part, parse_mode="HTML")
    else:
        await message.answer(text, parse_mode="HTML")

# Обработка кнопок "Назад"
@router.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.delete()
    is_admin = callback.from_user.id in ADMIN_IDS
    keyboard = get_admin_keyboard() if is_admin else get_main_keyboard()
    await callback.message.answer("Главное меню:", reply_markup=keyboard)
    await callback.answer()

@router.callback_query(F.data == "back_to_services")
async def back_to_services(callback: CallbackQuery, state: FSMContext):
    await state.set_state(BookingStates.choosing_service)
    await callback.message.edit_text(
        "✨ <b>Выберите услугу:</b>",
        parse_mode="HTML",
        reply_markup=get_services_keyboard()
    )
    await callback.answer()

@router.callback_query(F.data == "back_to_date")
async def back_to_date(callback: CallbackQuery, state: FSMContext):
    await state.set_state(BookingStates.choosing_date)
    data = await state.get_data()
    service = SERVICES[data['service_key']]
    
    await callback.message.edit_text(
        f"💅 <b>Вы выбрали:</b> {service['name']}\n"
        f"💰 <b>Стоимость:</b> {service['price']}₽\n\n"
        f"📅 <b>Выберите удобную дату:</b>",
        parse_mode="HTML",
        reply_markup=get_calendar_keyboard()
    )
    await callback.answer()

@router.callback_query(F.data == "ignore")
async def ignore_callback(callback: CallbackQuery):
    await callback.answer()

# ================================
# 🚀 ЗАПУСК БОТА
# ================================

async def main():
    dp.include_router(router)
    
    logger.info("🚀 Бот запущен!")
    logger.info("💅 Салон красоты готов принимать записи!")
    
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Бот остановлен")