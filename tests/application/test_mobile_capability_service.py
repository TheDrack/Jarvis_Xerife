import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from app.application.services.mobile_capability_service import ensure_mobile_capabilities
from app.domain.models.device import Capability, Device


@pytest.fixture()
def session():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine, tables=[Device.__table__, Capability.__table__])
    with Session(engine) as s:
        yield s


def _device(session, kind="mobile"):
    dev = Device(name="Pixel de teste", type=kind)
    session.add(dev)
    session.commit()
    session.refresh(dev)
    return dev


def test_creates_all_mobile_capabilities_once(session):
    dev = _device(session)
    created = ensure_mobile_capabilities(session, dev)
    assert len(created) == 5
    again = ensure_mobile_capabilities(session, dev)
    assert again == []  # idempotente
    names = session.exec(select(Capability.name).where(Capability.device_id == dev.id)).all()
    assert sorted(names) == sorted(created)


def test_rejects_non_mobile_device(session):
    dev = _device(session, kind="desktop")
    with pytest.raises(ValueError):
        ensure_mobile_capabilities(session, dev)


def test_rejects_unpersisted_device(session):
    with pytest.raises(ValueError):
        ensure_mobile_capabilities(session, Device(name="x", type="mobile"))
