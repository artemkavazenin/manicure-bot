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

