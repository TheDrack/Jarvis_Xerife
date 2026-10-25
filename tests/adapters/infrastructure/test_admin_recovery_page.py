from fastapi.responses import HTMLResponse

from app.adapters.infrastructure.routers.admin_recovery import create_admin_recovery_router


def test_recovery_page_is_served_without_authentication():
    router = create_admin_recovery_router()
    route = next(route for route in router.routes if route.path == "/recover")
    response = __import__("asyncio").run(route.endpoint())

    assert isinstance(response, HTMLResponse)
    assert response.status_code == 200
    assert "Recuperar acesso" in response.body.decode("utf-8")
    assert "X-Jarvis-Reset-Token" in response.body.decode("utf-8")
