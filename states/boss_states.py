"""FSM states for boss workflow."""
from aiogram.fsm.state import State, StatesGroup


class BossStates(StatesGroup):
    main_menu = State()
    choosing_employee = State()
    choosing_rooms = State()
    selecting_cleaning_type = State()  # выбор вида уборки для добавляемого номера
    selecting_linen_variant = State()  # выбор комплекта белья для номеров 101–109
    adding_comment = State()
    room_management = State()
    room_add_name = State()
    room_add_area = State()
    room_edit_select = State()
    room_edit_area = State()
    history_list = State()
    history_detail = State()
    templates_list = State()
