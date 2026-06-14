"""FSM-состояния (например, ожидание своего варианта времени)."""
from aiogram.fsm.state import State, StatesGroup


class ReminderFlow(StatesGroup):
    # ждём, пока пользователь введёт своё время текстом
    waiting_custom_time = State()
