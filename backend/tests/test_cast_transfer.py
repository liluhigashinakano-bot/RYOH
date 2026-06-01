import os
import sys
from datetime import date, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.database import Base
from app import models
from app.routers.casts import CastTransferRequest, get_cast_stats, get_casts, transfer_cast


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    source_store = models.Store(name="移籍元", code="SRC")
    target_store = models.Store(name="移籍先", code="DST")
    user = models.User(
        username="admin",
        password_hash="dummy",
        name="管理者",
        role=models.UserRole.administrator,
        is_active=True,
    )
    session.add_all([source_store, target_store, user])
    session.flush()

    yield session, source_store, target_store, user
    session.close()


def test_transfer_creates_new_cast_and_keeps_history_visible_from_target(db):
    session, source_store, target_store, user = db
    cast = models.Cast(
        store_id=source_store.id,
        cast_code="SRCF0001",
        stage_name="かな",
        rank="C",
        hourly_rate=1550,
        help_hourly_rate=1650,
        alcohol_tolerance="普通",
        is_active=True,
    )
    session.add(cast)
    session.flush()

    session.add(models.ConfirmedShift(
        cast_id=cast.id,
        store_id=source_store.id,
        date=date(2026, 5, 1),
        actual_start=datetime(2026, 5, 1, 11, 0),
        actual_end=datetime(2026, 5, 1, 15, 0),
        shift_data={"working_hours": 4, "drink_back": 800, "set_l": 1},
    ))
    session.commit()

    response = transfer_cast(
        source_store.id,
        cast.id,
        CastTransferRequest(target_store_id=target_store.id),
        session,
        user,
    )
    new_cast = session.get(models.Cast, response.id)
    old_cast = session.get(models.Cast, cast.id)

    assert new_cast is not None
    assert new_cast.id != old_cast.id
    assert new_cast.store_id == target_store.id
    assert new_cast.cast_code.startswith("DSTF")
    assert new_cast.transferred_from_cast_id == old_cast.id
    assert old_cast.is_active is False
    assert old_cast.is_retired is True
    assert old_cast.transferred_to_cast_id == new_cast.id

    source_list = get_casts(source_store.id, include_retired=True, db=session, current_user=user)
    target_list = get_casts(target_store.id, include_retired=True, db=session, current_user=user)
    assert all(c.id != old_cast.id for c in source_list)
    assert any(c.id == new_cast.id for c in target_list)

    stats = get_cast_stats(target_store.id, new_cast.id, db=session, current_user=user)
    assert stats["total_shifts"] == 1
    assert stats["avg_monthly_hours"] == 4.0
