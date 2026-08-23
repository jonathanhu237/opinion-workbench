from fastapi import FastAPI

from longtian_api.api.router import api_router


def create_app() -> FastAPI:
    """Create the product API without starting external collection services."""
    application = FastAPI(
        title="Longtian Public Opinion API",
        version="0.1.0",
    )
    application.include_router(api_router)
    return application


app = create_app()
