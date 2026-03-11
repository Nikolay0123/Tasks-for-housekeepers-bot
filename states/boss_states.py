"""FSM states for boss workflow."""
from aiogram.fsm.state import State, StatesGroup


class BossStates(StatesGroup):
    main_menu = State()
    choosing_employee = State()
    choosing_rooms = State()
    adding_comment = State()
    room_management = State()
    room_add_name = State()
    room_add_area = State()
    room_edit_select = State()
    room_edit_area = State()
    history_list = State()
    history_detail = State()
    templates_list = State()
