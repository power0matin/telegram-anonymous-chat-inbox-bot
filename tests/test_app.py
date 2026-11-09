"""Application composition tests."""

from whisprlink.app import create_dispatcher


def test_dispatcher_registers_start_router() -> None:
    dispatcher = create_dispatcher()

    assert [router.name for router in dispatcher.sub_routers] == ["start"]
