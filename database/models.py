"""SQLAlchemy models."""
from datetime import datetime
from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Room(Base):
    __tablename__ = "rooms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    area: Mapped[float] = mapped_column(Float, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    def __repr__(self) -> str:
        return f"<Room {self.name} {self.area} m²>"


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    employee_name: Mapped[str] = mapped_column(String(32), nullable=False)  # dina, lena, admin
    rooms_list: Mapped[str] = mapped_column(Text, nullable=False)  # JSON list of room ids/names with order
    total_area: Mapped[float] = mapped_column(Float, nullable=False)
    message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # message id in channel
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<Task {self.id} {self.employee_name} {self.total_area}>"


class Template(Base):
    __tablename__ = "templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    rooms_list: Mapped[str] = mapped_column(Text, nullable=False)  # JSON: list of {"room_id": int, "name": str, "area": float}
    total_area: Mapped[float] = mapped_column(Float, nullable=False)

    def __repr__(self) -> str:
        return f"<Template {self.name} {self.total_area}>"
