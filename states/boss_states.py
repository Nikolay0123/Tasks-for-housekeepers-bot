"""FSM states for boss workflow."""
from aiogram.fsm.state import State, StatesGroup


class BossStates(StatesGroup):
    main_menu = State()
    choosing_employee = State()
    choosing_rooms = State()
    selecting_cleaning_type = State()  # выбор вида уборки для добавляемого номера
    selecting_linen_variant = State()  # вариант комплекта: 101–109 или 4 этаж (401–405)
    selecting_variant2_beds = State()  # вариант 2 (101–109): 1 или 2 кровати
    selecting_linen_color = State()  # цвет белья для номеров 4 этажа (старый сценарий)
    selecting_floor4_bed_layout = State()  # 401.1 / … — разъединены или соединены
    selecting_floor4_beds_count = State()  # 4 этаж: сколько кроватей заправить
    adding_comment = State()
    room_management = State()
    room_add_name = State()
    room_add_area = State()
    room_edit_select = State()
    room_edit_area = State()
    history_list = State()
    history_detail = State()
    templates_list = State()
