"""
💅 Профессиональный Telegram-бот для записи на маникюр
Мастер: Юлия | Город Каменка, ул. Суворова

Версия: 2.0 Professional Edition
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List
import sqlite3
import os
import re

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
from aiogram.exceptions import TelegramBadRequest

# ================================
# 🎯 КОНФИГУРАЦИЯ
# ================================

BOT_TOKEN = os.getenv('BOT_TOKEN', "8583432941:AAHA0aaAtDwCsj_Agrn6e1jDIsSNzirde6c")
ADMIN_IDS = [int(id) for id in os.getenv('ADMIN_IDS', '8485520947').split(',')]

# Информация о салоне
MASTER_NAME = "Юлия"
SALON_ADDRESS = "г. Каменка, ул. Суворова"
SALON_PHONE = "+7 (900) 123-45-67"  # 👈 Укажите реальный номер
INSTAGRAM = "@julia_nails_kamenka"  # 👈 Укажите реальный Instagram

# ================================
# 🗄️ УЛУЧШЕННАЯ БАЗА ДАННЫХ
# ================================

class Database:
    def __init__(self, db_file: str = "manicure.db"):
        self.db_file = db_file
        self.init_db()
    
    def init_db(self):
        """Инициализация базы данных"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        # Таблица клиентов с дополнительными полями
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS clients (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                phone TEXT,
                total_visits INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_visit TIMESTAMP
            )
        """)
        
        # Таблица записей с улучшенной структурой
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS appointments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                service TEXT,
                service_key TEXT,
                date TEXT,
                time TEXT,
                price INTEGER,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                cancelled_at TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES clients (user_id)
            )
        """)
        
        # Индексы для быстрого поиска
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_date ON appointments(date, time)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user ON appointments(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_status ON appointments(status)")
        
        conn.commit()
        conn.close()
    
    def add_client(self, user_id: int, username: str, full_name: str, phone: str):
        """Добавление или обновление клиента"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO clients (user_id, username, full_name, phone)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username=excluded.username,
                full_name=excluded.full_name,
                phone=excluded.phone
        """, (user_id, username, full_name, phone))
        conn.commit()
        conn.close()
    
    def add_appointment(self, user_id: int, service: str, service_key: str, date: str, time: str, price: int):
        """Добавление записи"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO appointments (user_id, service, service_key, date, time, price)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user_id, service, service_key, date, time, price))
        appointment_id = cursor.lastrowid
        
        # Обновляем счетчик визитов
        cursor.execute("""
            UPDATE clients SET total_visits = total_visits + 1
            WHERE user_id = ?
        """, (user_id,))
        
        conn.commit()
        conn.close()
        return appointment_id
    
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
        """Получение активных записей пользователя"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, service, date, time, status, price
            FROM appointments 
            WHERE user_id = ? AND status = 'pending'
            AND date >= date('now')
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
            UPDATE appointments 
            SET status = 'cancelled', cancelled_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (appointment_id,))
        conn.commit()
        conn.close()
    
    def get_appointment_details(self, appointment_id: int) -> tuple:
        """Получение деталей записи"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT a.user_id, c.full_name, c.phone, a.service, a.date, a.time, a.price
            FROM appointments a
            JOIN clients c ON a.user_id = c.user_id
            WHERE a.id = ?
        """, (appointment_id,))
        result = cursor.fetchone()
        conn.close()
        return result
    
    def get_all_appointments(self, status: str = 'pending') -> List[tuple]:
        """Получение всех записей для админа"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        query = """
            SELECT a.id, c.full_name, c.phone, c.username, a.service, a.date, a.time, a.price, a.status
            FROM appointments a
            JOIN clients c ON a.user_id = c.user_id
        """
        if status:
            query += " WHERE a.status = ?"
            cursor.execute(query + " ORDER BY a.date, a.time", (status,))
        else:
            cursor.execute(query + " ORDER BY a.date DESC, a.time", ())
        
        appointments = cursor.fetchall()
        conn.close()
        return appointments
    
    def get_client_info(self, user_id: int) -> tuple:
        """Получение информации о клиенте"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT full_name, phone, total_visits, created_at
            FROM clients WHERE user_id = ?
        """, (user_id,))
        result = cursor.fetchone()
        conn.close()
        return result
    
    def get_stats(self) -> dict:
        """Статистика для админа"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        stats = {}
        
        # Всего клиентов
        cursor.execute("SELECT COUNT(*) FROM clients")
        stats['total_clients'] = cursor.fetchone()[0]
        
        # Активные записи
        cursor.execute("SELECT COUNT(*) FROM appointments WHERE status = 'pending' AND date >= date('now')")
        stats['active_appointments'] = cursor.fetchone()[0]
        
        # Записи сегодня
        cursor.execute("SELECT COUNT(*) FROM appointments WHERE date = date('now') AND status = 'pending'")
        stats['today_appointments'] = cursor.fetchone()[0]
        
        # Записи на неделю
        cursor.execute("""
            SELECT COUNT(*) FROM appointments 
            WHERE date BETWEEN date('now') AND date('now', '+7 days')
            AND status = 'pending'
        """)
        stats['week_appointments'] = cursor.fetchone()[0]
        
        # Доход за месяц
        cursor.execute("""
            SELECT COALESCE(SUM(price), 0) FROM appointments 
            WHERE strftime('%Y-%m', date) = strftime('%Y-%m', 'now')
            AND status = 'pending'
        """)
        stats['month_revenue'] = cursor.fetchone()[0]
        
        conn.close()
        return stats

# ================================
# 📋 СОСТОЯНИЯ FSM
# ================================

class BookingStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_phone = State()
    choosing_service = State()
    choosing_date = State()
    choosing_time = State()
    confirming = State()

# ================================
# 💅 УЛУЧШЕННЫЕ УСЛУГИ
# ================================

SERVICES = {
    "classic": {
        "name": "💅 Классический маникюр",
        "description": "Обработка ногтей, кутикулы, форма",
        "duration": 60,
        "price": 1500,
        "emoji": "💅"
    },
    "hardware": {
        "name": "✨ Аппаратный маникюр",
        "description": "Безопасная обработка аппаратом",
        "duration": 60,
        "price": 1800,
        "emoji": "✨"
    },
    "gel": {
        "name": "💎 Гель-лак (маникюр + покрытие)",
        "description": "Маникюр + стойкое покрытие гель-лаком",
        "duration": 90,
        "price": 2500,
        "emoji": "💎"
    },
    "design": {
        "name": "🎨 Дизайн ногтей",
        "description": "Художественный дизайн любой сложности",
        "duration": 120,
        "price": 3000,
        "emoji": "🎨"
    },
    "complex": {
        "name": "👑 Комплексный уход",
        "description": "Маникюр + покрытие + дизайн + уход",
        "duration": 150,
        "price": 4000,
        "emoji": "👑"
    },
}

WORKING_HOURS = ["09:00", "10:30", "12:00", "13:30", "15:00", "16:30", "18:00", "19:30"]

# Месяцы на русском
MONTHS_RU = {
    1: "января", 2: "февраля", 3: "марта", 4: "апреля",
    5: "мая", 6: "июня", 7: "июля", 8: "августа",
    9: "сентября", 10: "октября", 11: "ноября", 12: "декабря"
}

# ================================
# 🎨 УЛУЧШЕННЫЕ КЛАВИАТУРЫ
# ================================

def get_main_keyboard(is_admin: bool = False) -> ReplyKeyboardMarkup:
    """Главное меню с красивыми эмодзи"""
    keyboard = [
        [KeyboardButton(text="📅 Записаться на маникюр")],
        [
            KeyboardButton(text="📋 Мои записи"),
            KeyboardButton(text="💬 Связаться с мастером")
        ],
        [
            KeyboardButton(text="ℹ️ О мастере"),
            KeyboardButton(text="📸 Наши работы")
        ]
    ]
    
    if is_admin:
        keyboard.append([KeyboardButton(text="👑 Панель управления")])
    
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_services_keyboard() -> InlineKeyboardMarkup:
    """Красивая клавиатура выбора услуг"""
    buttons = []
    
    for key, service in SERVICES.items():
        buttons.append([InlineKeyboardButton(
            text=f"{service['emoji']} {service['name'].replace(service['emoji'] + ' ', '')}",
            callback_data=f"service_{key}"
        )])
        buttons.append([InlineKeyboardButton(
            text=f"   ├ {service['duration']} мин • {service['price']}₽",
            callback_data=f"info_{key}"
        )])
    
    buttons.append([InlineKeyboardButton(
        text="« Назад в меню",
        callback_data="back_to_menu"
    )])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_calendar_keyboard(selected_month: int = None, selected_year: int = None) -> InlineKeyboardMarkup:
    """Улучшенный календарь"""
    now = datetime.now()
    
    if selected_month and selected_year:
        current_date = datetime(selected_year, selected_month, 1)
    else:
        current_date = now
    
    buttons = []
    
    # Заголовок с месяцем
    month_name = MONTHS_RU[current_date.month].capitalize()
    buttons.append([InlineKeyboardButton(
        text=f"📅 {month_name} {current_date.year}",
        callback_data="ignore"
    )])
    
    # Дни недели
    weekdays = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    buttons.append([
        InlineKeyboardButton(text=day, callback_data="ignore") 
        for day in weekdays
    ])
    
    # Генерация дней
    month_start = current_date.replace(day=1)
    start_weekday = month_start.weekday()
    
    # Вычисляем последний день месяца
    if month_start.month == 12:
        next_month = month_start.replace(year=month_start.year + 1, month=1)
    else:
        next_month = month_start.replace(month=month_start.month + 1)
    
    last_day = (next_month - timedelta(days=1)).day
    
    week = [InlineKeyboardButton(text=" ", callback_data="ignore")] * start_weekday
    
    for day in range(1, last_day + 1):
        date = current_date.replace(day=day)
        
        # Только будущие даты
        if date.date() >= now.date():
            week.append(InlineKeyboardButton(
                text=f"✓ {day}" if date.date() == now.date() else str(day),
                callback_data=f"date_{date.strftime('%Y-%m-%d')}"
            ))
        else:
            week.append(InlineKeyboardButton(text="·", callback_data="ignore"))
        
        if len(week) == 7:
            buttons.append(week)
            week = []
    
    if week:
        while len(week) < 7:
            week.append(InlineKeyboardButton(text=" ", callback_data="ignore"))
        buttons.append(week)
    
    # Навигация по месяцам
    nav_buttons = []
    if current_date.month > now.month or current_date.year > now.year:
        prev_month = current_date.month - 1 if current_date.month > 1 else 12
        prev_year = current_date.year if current_date.month > 1 else current_date.year - 1
        nav_buttons.append(InlineKeyboardButton(
            text="◀️ Назад",
            callback_data=f"month_{prev_year}_{prev_month}"
        ))
    
    if current_date.month < 12:
        next_month = current_date.month + 1
        next_year = current_date.year
        nav_buttons.append(InlineKeyboardButton(
            text="Вперёд ▶️",
            callback_data=f"month_{next_year}_{next_month}"
        ))
    
    if nav_buttons:
        buttons.append(nav_buttons)
    
    buttons.append([InlineKeyboardButton(
        text="« К выбору услуги",
        callback_data="back_to_services"
    )])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_time_keyboard(date: str, booked_times: List[str]) -> InlineKeyboardMarkup:
    """Улучшенная клавиатура выбора времени"""
    buttons = []
    row = []
    
    for i, time in enumerate(WORKING_HOURS):
        if time in booked_times:
            btn_text = f"🚫 {time}"
            callback = "time_unavailable"
        else:
            btn_text = f"🟢 {time}"
            callback = f"time_{time}"
        
        row.append(InlineKeyboardButton(text=btn_text, callback_data=callback))
        
        if (i + 1) % 2 == 0:
            buttons.append(row)
            row = []
    
    if row:
        buttons.append(row)
    
    buttons.append([InlineKeyboardButton(
        text="« К выбору даты",
        callback_data="back_to_date"
    )])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_confirmation_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура подтверждения"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Подтвердить запись", callback_data="confirm_yes"),
            InlineKeyboardButton(text="❌ Отменить", callback_data="confirm_no")
        ]
    ])

def get_my_appointments_keyboard(appointments: List[tuple]) -> InlineKeyboardMarkup:
    """Клавиатура с кнопками отмены записей"""
    buttons = []
    
    for apt in appointments:
        apt_id, service, date, time, status, price = apt
        date_obj = datetime.strptime(date, "%Y-%m-%d")
        formatted_date = f"{date_obj.day} {MONTHS_RU[date_obj.month]}"
        
        buttons.append([InlineKeyboardButton(
            text=f"🗑 Отменить запись {formatted_date} в {time}",
            callback_data=f"cancel_{apt_id}"
        )])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# ================================
# 🤖 ИНИЦИАЛИЗАЦИЯ
# ================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()
db = Database()

# ================================
# 🔔 УВЕДОМЛЕНИЯ АДМИНУ
# ================================

async def notify_admin_new_booking(appointment_id: int):
    """Отправка уведомления админу о новой записи"""
    details = db.get_appointment_details(appointment_id)
    if not details:
        return
    
    user_id, full_name, phone, service, date, time, price = details
    
    date_obj = datetime.strptime(date, "%Y-%m-%d")
    formatted_date = f"{date_obj.day} {MONTHS_RU[date_obj.month]} {date_obj.year}"
    
    notification = f"""
🔔 <b>НОВАЯ ЗАПИСЬ!</b> 🔔

👤 <b>Клиент:</b> {full_name}
📱 <b>Телефон:</b> {phone}
💅 <b>Услуга:</b> {service}
📅 <b>Дата:</b> {formatted_date}
🕐 <b>Время:</b> {time}
💰 <b>Стоимость:</b> {price}₽

📝 <b>ID записи:</b> #{appointment_id}
    """
    
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, notification, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Не удалось отправить уведомление админу {admin_id}: {e}")

async def notify_admin_cancellation(appointment_id: int, cancelled_by_user: bool = True):
    """Уведомление об отмене записи"""
    details = db.get_appointment_details(appointment_id)
    if not details:
        return
    
    user_id, full_name, phone, service, date, time, price = details
    
    date_obj = datetime.strptime(date, "%Y-%m-%d")
    formatted_date = f"{date_obj.day} {MONTHS_RU[date_obj.month]}"
    
    who_cancelled = "клиентом" if cancelled_by_user else "администратором"
    
    notification = f"""
❌ <b>ОТМЕНА ЗАПИСИ</b> ❌

👤 <b>Клиент:</b> {full_name}
📱 <b>Телефон:</b> {phone}
💅 <b>Услуга:</b> {service}
📅 <b>Дата:</b> {formatted_date} в {time}

⚠️ Отменено {who_cancelled}
📝 ID: #{appointment_id}
    """
    
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, notification, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления: {e}")

# ================================
# 🎯 ОБРАБОТЧИКИ КОМАНД
# ================================

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    """Команда /start"""
    await state.clear()
    
    user_id = message.from_user.id
    is_admin = user_id in ADMIN_IDS
    
    keyboard = get_main_keyboard(is_admin)
    
    welcome_text = f"""
✨ <b>Добро пожаловать в салон красоты!</b> ✨

Здравствуйте, {message.from_user.first_name}! 💅

Я бот для записи к мастеру маникюра <b>{MASTER_NAME}</b>.

🌟 <b>Почему выбирают нас:</b>
• Профессиональный мастер с опытом 5+ лет
• Качественные материалы премиум-класса
• Стерильные инструменты
• Уютная атмосфера
• Индивидуальный подход

📍 <b>Адрес:</b> {SALON_ADDRESS}

Выберите действие в меню ниже 👇
    """
    
    if is_admin:
        welcome_text += "\n\n👑 <b>Режим администратора активирован</b>"
    
    await message.answer(
        welcome_text,
        parse_mode="HTML",
        reply_markup=keyboard
    )

@router.message(F.text == "📅 Записаться на маникюр")
async def start_booking(message: Message, state: FSMContext):
    """Начало записи"""
    # Проверяем, есть ли уже информация о клиенте
    client_info = db.get_client_info(message.from_user.id)
    
    if client_info:
        # Клиент уже есть в базе, сразу к выбору услуги
        full_name, phone, total_visits, created_at = client_info
        await state.update_data(full_name=full_name, phone=phone)
        await state.set_state(BookingStates.choosing_service)
        
        greeting = f"Рады видеть вас снова, {full_name}! 💕" if total_visits > 0 else f"Здравствуйте, {full_name}! 💕"
        
        await message.answer(
            f"{greeting}\n\n"
            f"✨ <b>Выберите услугу:</b>\n\n"
            f"Нажмите на интересующую вас процедуру 👇",
            parse_mode="HTML",
            reply_markup=get_services_keyboard()
        )
    else:
        # Новый клиент
        await state.set_state(BookingStates.waiting_for_name)
        await message.answer(
            "🌸 <b>Приятно познакомиться!</b>\n\n"
            "Для записи мне нужна немного информации.\n\n"
            "Как я могу к вам обращаться?\n"
            "Напишите ваше имя:",
            parse_mode="HTML",
            reply_markup=ReplyKeyboardRemove()
        )

@router.message(BookingStates.waiting_for_name)
async def process_name(message: Message, state: FSMContext):
    """Обработка имени"""
    name = message.text.strip()
    
    if len(name) < 2 or len(name) > 50:
        await message.answer(
            "❌ Пожалуйста, введите корректное имя (от 2 до 50 символов)"
        )
        return
    
    await state.update_data(full_name=name)
    await state.set_state(BookingStates.waiting_for_phone)
    
    await message.answer(
        f"Приятно познакомиться, {name}! 😊\n\n"
        "📱 Теперь напишите ваш номер телефона.\n\n"
        "<i>Формат: +7 900 123 45 67</i>",
        parse_mode="HTML"
    )

@router.message(BookingStates.waiting_for_phone)
async def process_phone(message: Message, state: FSMContext):
    """Обработка телефона"""
    phone = message.text.strip()
    
    # Простая валидация номера
    phone_clean = re.sub(r'[^\d+]', '', phone)
    if len(phone_clean) < 11:
        await message.answer(
            "❌ Пожалуйста, введите корректный номер телефона\n\n"
            "<i>Например: +7 900 123 45 67</i>",
            parse_mode="HTML"
        )
        return
    
    await state.update_data(phone=phone)
    
    # Сохраняем клиента
    data = await state.get_data()
    db.add_client(
        user_id=message.from_user.id,
        username=message.from_user.username or "",
        full_name=data['full_name'],
        phone=phone
    )
    
    await state.set_state(BookingStates.choosing_service)
    
    await message.answer(
        "✅ Отлично! Информация сохранена.\n\n"
        "✨ <b>Теперь выберите услугу:</b>",
        parse_mode="HTML",
        reply_markup=get_services_keyboard()
    )

@router.callback_query(F.data.startswith("service_"))
async def process_service(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора услуги"""
    service_key = callback.data.split("_")[1]
    service = SERVICES[service_key]
    
    await state.update_data(
        service=service['name'],
        service_key=service_key,
        price=service['price'],
        duration=service['duration']
    )
    await state.set_state(BookingStates.choosing_date)
    
    await callback.message.edit_text(
        f"{service['emoji']} <b>Вы выбрали:</b>\n"
        f"<b>{service['name'].replace(service['emoji'] + ' ', '')}</b>\n\n"
        f"📝 {service['description']}\n"
        f"⏱ Продолжительность: {service['duration']} минут\n"
        f"💰 Стоимость: <b>{service['price']}₽</b>\n\n"
        f"📅 <b>Выберите удобную дату:</b>",
        parse_mode="HTML",
        reply_markup=get_calendar_keyboard()
    )
    await callback.answer()

@router.callback_query(F.data.startswith("info_"))
async def show_service_info(callback: CallbackQuery):
    """Показ информации об услуге"""
    service_key = callback.data.split("_")[1]
    service = SERVICES[service_key]
    
    await callback.answer(
        f"{service['description']}\n"
        f"⏱ {service['duration']} мин • {service['price']}₽",
        show_alert=True
    )

@router.callback_query(F.data.startswith("month_"))
async def change_month(callback: CallbackQuery, state: FSMContext):
    """Навигация по месяцам"""
    _, year, month = callback.data.split("_")
    
    try:
        await callback.message.edit_reply_markup(
            reply_markup=get_calendar_keyboard(int(month), int(year))
        )
    except TelegramBadRequest:
        pass
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
    formatted_date = f"{date_obj.day} {MONTHS_RU[date_obj.month]} {date_obj.year}"
    weekday = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"][date_obj.weekday()]
    
    await callback.message.edit_text(
        f"📅 <b>Дата:</b> {formatted_date} ({weekday})\n\n"
        f"🕐 <b>Выберите удобное время:</b>\n\n"
        f"🟢 - свободно\n"
        f"🚫 - занято",
        parse_mode="HTML",
        reply_markup=get_time_keyboard(date, booked_times)
    )
    await callback.answer()

@router.callback_query(F.data.startswith("time_"))
async def process_time(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора времени"""
    if callback.data == "time_unavailable":
        await callback.answer("⚠️ Это время уже занято. Выберите другое.", show_alert=True)
        return
    
    time = callback.data.split("_")[1]
    await state.update_data(time=time)
    await state.set_state(BookingStates.confirming)
    
    data = await state.get_data()
    
    date_obj = datetime.strptime(data['date'], "%Y-%m-%d")
    formatted_date = f"{date_obj.day} {MONTHS_RU[date_obj.month]} {date_obj.year}"
    weekday = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"][date_obj.weekday()]
    
    service = SERVICES[data['service_key']]
    
    confirmation_text = f"""
✨ <b>ПОДТВЕРЖДЕНИЕ ЗАПИСИ</b> ✨

👤 <b>Имя:</b> {data['full_name']}
📱 <b>Телефон:</b> {data['phone']}

💅 <b>Услуга:</b>
{service['emoji']} {service['name'].replace(service['emoji'] + ' ', '')}

📅 <b>Дата:</b> {formatted_date} ({weekday})
🕐 <b>Время:</b> {time}
⏱ <b>Длительность:</b> {data['duration']} минут
💰 <b>Стоимость:</b> <b>{data['price']}₽</b>

📍 <b>Адрес:</b> {SALON_ADDRESS}

─────────────────────

⚠️ <b>Важно:</b>
• Пожалуйста, приходите за 5 минут до начала
• При опоздании более 15 минут запись может быть отменена
• Для отмены записи используйте меню "📋 Мои записи"

Всё верно? Подтверждаете запись?
    """
    
    await callback.message.edit_text(
        confirmation_text,
        parse_mode="HTML",
        reply_markup=get_confirmation_keyboard()
    )
    await callback.answer()

@router.callback_query(F.data == "confirm_yes")
async def confirm_booking(callback: CallbackQuery, state: FSMContext):
    """Подтверждение записи"""
    data = await state.get_data()
    
    # Проверяем, не занято ли время (двойная проверка)
    booked_times = db.get_appointments_by_date(data['date'])
    if data['time'] in booked_times:
        await callback.message.edit_text(
            "❌ <b>К сожалению, это время только что заняли.</b>\n\n"
            "Пожалуйста, выберите другое время.",
            parse_mode="HTML"
        )
        await callback.answer("Время занято", show_alert=True)
        await state.set_state(BookingStates.choosing_time)
        return
    
    # Сохраняем запись
    appointment_id = db.add_appointment(
        user_id=callback.from_user.id,
        service=data['service'],
        service_key=data['service_key'],
        date=data['date'],
        time=data['time'],
        price=data['price']
    )
    
    date_obj = datetime.strptime(data['date'], "%Y-%m-%d")
    formatted_date = f"{date_obj.day} {MONTHS_RU[date_obj.month]} {date_obj.year}"
    
    service = SERVICES[data['service_key']]
    
    success_text = f"""
🎉 <b>ЗАПИСЬ УСПЕШНО СОЗДАНА!</b> 🎉

✅ Вы записаны на:

{service['emoji']} <b>{service['name'].replace(service['emoji'] + ' ', '')}</b>
📅 {formatted_date}
🕐 {data['time']}
💰 {data['price']}₽

📍 <b>Адрес:</b>
{SALON_ADDRESS}

📱 <b>Телефон мастера:</b>
{SALON_PHONE}

💌 <b>Важная информация:</b>
• ID вашей записи: #{appointment_id}
• Мастер {MASTER_NAME} ждёт вас!
• Напоминание придёт за день до визита
• Для отмены используйте "📋 Мои записи"

✨ <b>Будем рады видеть вас!</b> ✨

До встречи! 💅💕
    """
    
    await callback.message.edit_text(
        success_text,
        parse_mode="HTML"
    )
    
    is_admin = callback.from_user.id in ADMIN_IDS
    await callback.message.answer(
        "Вернуться в главное меню:",
        reply_markup=get_main_keyboard(is_admin)
    )
    
    # Отправляем уведомление админу
    await notify_admin_new_booking(appointment_id)
    
    await state.clear()
    await callback.answer("✅ Запись создана!", show_alert=True)

@router.callback_query(F.data == "confirm_no")
async def cancel_booking_process(callback: CallbackQuery, state: FSMContext):
    """Отмена процесса записи"""
    await state.clear()
    
    await callback.message.edit_text(
        "❌ Запись отменена.\n\n"
        "Вы можете начать заново, нажав кнопку\n"
        "📅 <b>Записаться на маникюр</b>",
        parse_mode="HTML"
    )
    
    is_admin = callback.from_user.id in ADMIN_IDS
    await callback.message.answer(
        "Главное меню:",
        reply_markup=get_main_keyboard(is_admin)
    )
    await callback.answer()

@router.message(F.text == "📋 Мои записи")
async def my_appointments(message: Message):
    """Показать записи пользователя"""
    appointments = db.get_user_appointments(message.from_user.id)
    
    if not appointments:
        await message.answer(
            "📋 <b>У вас пока нет активных записей</b>\n\n"
            "Нажмите <b>📅 Записаться на маникюр</b>, чтобы создать новую запись! 💅",
            parse_mode="HTML"
        )
        return
    
    text = "📋 <b>ВАШИ ЗАПИСИ:</b>\n\n"
    
    for apt in appointments:
        apt_id, service, date, time, status, price = apt
        date_obj = datetime.strptime(date, "%Y-%m-%d")
        formatted_date = f"{date_obj.day} {MONTHS_RU[date_obj.month]} {date_obj.year}"
        weekday = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"][date_obj.weekday()]
        
        # Находим эмодзи услуги
        service_emoji = "💅"
        for key, serv in SERVICES.items():
            if serv['name'] == service:
                service_emoji = serv['emoji']
                break
        
        text += (
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"{service_emoji} <b>{service.split(' ', 1)[1] if ' ' in service else service}</b>\n"
            f"📅 {formatted_date} ({weekday})\n"
            f"🕐 {time}\n"
            f"💰 {price}₽\n"
            f"📝 ID: #{apt_id}\n\n"
        )
    
    text += "━━━━━━━━━━━━━━━━━━━━\n\n"
    text += "💡 <i>Для отмены записи нажмите кнопку ниже</i>"
    
    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=get_my_appointments_keyboard(appointments)
    )

@router.callback_query(F.data.startswith("cancel_"))
async def cancel_appointment(callback: CallbackQuery):
    """Отмена записи клиентом"""
    appointment_id = int(callback.data.split("_")[1])
    
    # Получаем детали записи перед отменой
    details = db.get_appointment_details(appointment_id)
    if not details:
        await callback.answer("❌ Запись не найдена", show_alert=True)
        return
    
    user_id, full_name, phone, service, date, time, price = details
    
    # Проверяем, что это запись пользователя
    if user_id != callback.from_user.id:
        await callback.answer("❌ Это не ваша запись", show_alert=True)
        return
    
    # Отменяем запись
    db.cancel_appointment(appointment_id)
    
    date_obj = datetime.strptime(date, "%Y-%m-%d")
    formatted_date = f"{date_obj.day} {MONTHS_RU[date_obj.month]}"
    
    await callback.message.edit_text(
        f"✅ <b>Запись отменена</b>\n\n"
        f"💅 {service}\n"
        f"📅 {formatted_date} в {time}\n\n"
        f"💔 Жаль, что не сможете прийти.\n"
        f"Будем рады видеть вас в другой раз! 💕",
        parse_mode="HTML"
    )
    
    # Уведомляем админа
    await notify_admin_cancellation(appointment_id, cancelled_by_user=True)
    
    await callback.answer("Запись отменена", show_alert=True)

@router.message(F.text == "ℹ️ О мастере")
async def about_master(message: Message):
    """Информация о мастере"""
    about_text = f"""
✨ <b>МАСТЕР МАНИКЮРА</b> ✨

👩‍🎨 <b>{MASTER_NAME}</b>

🌟 <b>О мастере:</b>
• Опыт работы: 5+ лет
• Профессиональное образование
• Регулярное повышение квалификации
• Работа с премиум-материалами
• Индивидуальный подход к каждому клиенту

💅 <b>Специализация:</b>
• Классический и аппаратный маникюр
• Покрытие гель-лаком
• Художественный дизайн ногтей
• Укрепление и восстановление ногтей
• Nail-арт любой сложности

📍 <b>Где мы находимся:</b>
{SALON_ADDRESS}

📱 <b>Контакты:</b>
Телефон: {SALON_PHONE}
Instagram: {INSTAGRAM}

⏰ <b>Режим работы:</b>
Ежедневно с 09:00 до 21:00

💎 <b>Почему выбирают нас:</b>
• Стерильные инструменты
• Качественные материалы (CND, OPI, Kodi)
• Уютная атмосфера
• Приятные цены
• Удобное расположение

✨ Записывайтесь и убедитесь сами! ✨
    """
    
    await message.answer(about_text, parse_mode="HTML")

@router.message(F.text == "📸 Наши работы")
async def show_portfolio(message: Message):
    """Показать портфолио"""
    portfolio_text = f"""
📸 <b>НАШИ РАБОТЫ</b>

✨ Посмотрите примеры работ мастера {MASTER_NAME} в Instagram:

👉 {INSTAGRAM}

💅 Там вы найдете:
• Фото наших работ
• Актуальные цены
• Акции и специальные предложения
• Отзывы довольных клиентов
• Новинки дизайна

🎨 Мы постоянно обновляем портфолио и показываем новые идеи дизайна!

💕 Подписывайтесь, чтобы не пропустить акции!
    """
    
    await message.answer(portfolio_text, parse_mode="HTML")

@router.message(F.text == "💬 Связаться с мастером")
async def contact_master(message: Message):
    """Контакты для связи"""
    contact_text = f"""
💬 <b>СВЯЗАТЬСЯ С МАСТЕРОМ</b>

👩‍🎨 <b>Мастер:</b> {MASTER_NAME}

📱 <b>Телефон:</b>
{SALON_PHONE}

📍 <b>Адрес:</b>
{SALON_ADDRESS}

📲 <b>Социальные сети:</b>
Instagram: {INSTAGRAM}

💬 <b>Вы можете:</b>
• Позвонить по телефону
• Написать в Instagram Direct
• Задать вопрос прямо здесь в боте

⏰ <b>Время для звонков:</b>
Ежедневно с 09:00 до 21:00

✨ Всегда рады ответить на ваши вопросы!
    """
    
    await message.answer(contact_text, parse_mode="HTML")

# ================================
# 👑 АДМИН-ПАНЕЛЬ
# ================================

@router.message(F.text == "👑 Панель управления")
async def admin_panel(message: Message):
    """Админ-панель"""
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔️ У вас нет доступа")
        return
    
    stats = db.get_stats()
    
    admin_text = f"""
👑 <b>ПАНЕЛЬ УПРАВЛЕНИЯ</b> 👑

📊 <b>СТАТИСТИКА:</b>

👥 Всего клиентов: <b>{stats['total_clients']}</b>
📅 Активных записей: <b>{stats['active_appointments']}</b>
📆 Записей сегодня: <b>{stats['today_appointments']}</b>
📈 Записей на неделю: <b>{stats['week_appointments']}</b>
💰 Доход за месяц: <b>{stats['month_revenue']}₽</b>

━━━━━━━━━━━━━━━━━━━━

<b>ДОСТУПНЫЕ КОМАНДЫ:</b>

/today - Записи на сегодня
/week - Записи на неделю
/all - Все активные записи
/history - История записей
/stats - Подробная статистика
    """
    
    await message.answer(admin_text, parse_mode="HTML")

@router.message(Command("today"))
async def show_today_appointments(message: Message):
    """Записи на сегодня (только для админа)"""
    if message.from_user.id not in ADMIN_IDS:
        return
    
    today = datetime.now().strftime("%Y-%m-%d")
    
    conn = sqlite3.connect(db.db_file)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT a.id, c.full_name, c.phone, a.service, a.time, a.price
        FROM appointments a
        JOIN clients c ON a.user_id = c.user_id
        WHERE a.date = ? AND a.status = 'pending'
        ORDER BY a.time
    """, (today,))
    appointments = cursor.fetchall()
    conn.close()
    
    if not appointments:
        await message.answer("📅 На сегодня записей нет")
        return
    
    text = f"📅 <b>ЗАПИСИ НА СЕГОДНЯ</b>\n"
    text += f"{datetime.now().strftime('%d.%m.%Y')}\n\n"
    
    total = 0
    for apt in appointments:
        apt_id, name, phone, service, time, price = apt
        text += (
            f"🕐 <b>{time}</b>\n"
            f"👤 {name}\n"
            f"📱 {phone}\n"
            f"💅 {service}\n"
            f"💰 {price}₽\n"
            f"━━━━━━━━━━━━━━━━\n\n"
        )
        total += price
    
    text += f"💵 <b>Итого:</b> {total}₽"
    
    await message.answer(text, parse_mode="HTML")

@router.message(Command("week"))
async def show_week_appointments(message: Message):
    """Записи на неделю (только для админа)"""
    if message.from_user.id not in ADMIN_IDS:
        return
    
    today = datetime.now()
    week_end = (today + timedelta(days=7)).strftime("%Y-%m-%d")
    today_str = today.strftime("%Y-%m-%d")
    
    conn = sqlite3.connect(db.db_file)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT a.date, a.time, c.full_name, c.phone, a.service, a.price
        FROM appointments a
        JOIN clients c ON a.user_id = c.user_id
        WHERE a.date BETWEEN ? AND ? AND a.status = 'pending'
        ORDER BY a.date, a.time
    """, (today_str, week_end))
    appointments = cursor.fetchall()
    conn.close()
    
    if not appointments:
        await message.answer("📅 На ближайшую неделю записей нет")
        return
    
    text = "📅 <b>ЗАПИСИ НА НЕДЕЛЮ</b>\n\n"
    
    current_date = None
    total = 0
    
    for apt in appointments:
        date, time, name, phone, service, price = apt
        
        if date != current_date:
            if current_date:
                text += "\n"
            date_obj = datetime.strptime(date, "%Y-%m-%d")
            formatted_date = f"{date_obj.day} {MONTHS_RU[date_obj.month]}"
            weekday = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"][date_obj.weekday()]
            text += f"<b>{formatted_date} ({weekday})</b>\n"
            current_date = date
        
        text += (
            f"  🕐 {time} | {name} | {service}\n"
        )
        total += price
    
    text += f"\n💵 <b>Итого:</b> {total}₽"
    
    await message.answer(text, parse_mode="HTML")

@router.message(Command("all"))
async def show_all_appointments(message: Message):
    """Все активные записи (только для админа)"""
    if message.from_user.id not in ADMIN_IDS:
        return
    
    appointments = db.get_all_appointments(status='pending')
    
    if not appointments:
        await message.answer("📋 Активных записей нет")
        return
    
    text = "📋 <b>ВСЕ АКТИВНЫЕ ЗАПИСИ:</b>\n\n"
    
    total = 0
    for apt in appointments:
        apt_id, name, phone, username, service, date, time, price, status = apt
        
        date_obj = datetime.strptime(date, "%Y-%m-%d")
        formatted_date = f"{date_obj.day}.{date_obj.month}.{date_obj.year}"
        
        text += (
            f"<b>#{apt_id}</b> | {formatted_date} {time}\n"
            f"👤 {name} | 📱 {phone}\n"
            f"💅 {service} | 💰 {price}₽\n"
            f"━━━━━━━━━━━━━━━━\n\n"
        )
        total += price
        
        # Разбиваем на части если слишком длинное
        if len(text) > 3500:
            await message.answer(text, parse_mode="HTML")
            text = ""
    
    if text:
        text += f"💵 <b>Общая сумма:</b> {total}₽"
        await message.answer(text, parse_mode="HTML")

@router.message(Command("stats"))
async def detailed_stats(message: Message):
    """Подробная статистика (только для админа)"""
    if message.from_user.id not in ADMIN_IDS:
        return
    
    conn = sqlite3.connect(db.db_file)
    cursor = conn.cursor()
    
    # Статистика по услугам
    cursor.execute("""
        SELECT service_key, COUNT(*), SUM(price)
        FROM appointments
        WHERE status = 'pending' AND date >= date('now')
        GROUP BY service_key
    """)
    services_stats = cursor.fetchall()
    
    # Популярные дни недели
    cursor.execute("""
        SELECT 
            CASE CAST(strftime('%w', date) AS INTEGER)
                WHEN 0 THEN 'Воскресенье'
                WHEN 1 THEN 'Понедельник'
                WHEN 2 THEN 'Вторник'
                WHEN 3 THEN 'Среда'
                WHEN 4 THEN 'Четверг'
                WHEN 5 THEN 'Пятница'
                WHEN 6 THEN 'Суббота'
            END as day,
            COUNT(*)
        FROM appointments
        WHERE status = 'pending'
        GROUP BY strftime('%w', date)
        ORDER BY COUNT(*) DESC
        LIMIT 3
    """)
    popular_days = cursor.fetchall()
    
    conn.close()
    
    stats = db.get_stats()
    
    text = f"""
📊 <b>ПОДРОБНАЯ СТАТИСТИКА</b>

━━━━━━━━━━━━━━━━━━━━

👥 <b>КЛИЕНТЫ:</b>
Всего зарегистрировано: {stats['total_clients']}

📅 <b>ЗАПИСИ:</b>
Активных: {stats['active_appointments']}
Сегодня: {stats['today_appointments']}
На неделю: {stats['week_appointments']}

💰 <b>ФИНАНСЫ:</b>
Доход за месяц: {stats['month_revenue']}₽

━━━━━━━━━━━━━━━━━━━━

💅 <b>ПОПУЛЯРНЫЕ УСЛУГИ:</b>
"""
    
    for service_key, count, revenue in services_stats:
        service_name = SERVICES.get(service_key, {}).get('name', 'Неизвестно')
        text += f"• {service_name}: {count} шт. ({revenue}₽)\n"
    
    text += "\n📆 <b>ПОПУЛЯРНЫЕ ДНИ:</b>\n"
    for day, count in popular_days:
        text += f"• {day}: {count} записей\n"
    
    await message.answer(text, parse_mode="HTML")

# Обработка кнопок "Назад"
@router.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.delete()
    is_admin = callback.from_user.id in ADMIN_IDS
    await callback.message.answer(
        "Главное меню:",
        reply_markup=get_main_keyboard(is_admin)
    )
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
        f"{service['emoji']} <b>Вы выбрали:</b> {service['name'].replace(service['emoji'] + ' ', '')}\n\n"
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

async def run_bot():
    """Запуск бота"""
    dp.include_router(router)
    
    logger.info("=" * 50)
    logger.info("🚀 БОТ ЗАПУЩЕН!")
    logger.info(f"💅 Мастер: {MASTER_NAME}")
    logger.info(f"📍 Адрес: {SALON_ADDRESS}")
    logger.info(f"👑 Админов: {len(ADMIN_IDS)}")
    logger.info("=" * 50)
    
    try:
        await dp.start_polling(bot, skip_updates=True)
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

# Простой веб-сервер для Render (чтобы не было timeout)
async def run_web_server():
    """Запуск фейкового веб-сервера для Render"""
    from aiohttp import web
    
    async def health(request):
        return web.Response(text="Bot is running! 🤖")
    
    app = web.Application()
    app.router.add_get('/', health)
    app.router.add_get('/health', health)
    
    port = int(os.getenv('PORT', 10000))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    
    logger.info(f"🌐 Веб-сервер запущен на порту {port}")
    await site.start()

async def main():
    """Главная функция - запускает бота и веб-сервер"""
    await asyncio.gather(
        run_bot(),
        run_web_server()
    )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Бот остановлен пользователем")