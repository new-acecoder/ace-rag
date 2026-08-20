from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.documents import router as documents_router
from app.api.health import router as health_router
from app.core.config import get_settings
from app.core.errors import ApiError, ApiException
from app.db.migrator import run_migrations


def error_response(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=ApiError(code=code, message=message).model_dump(),
    )


def create_app(run_database_migrations: bool = False) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if run_database_migrations:
            await run_migrations(get_settings())
        yield

    app = FastAPI(title="Ace RAG", version="0.1.0", lifespan=lifespan)

    @app.exception_handler(ApiException)
    async def api_exception_handler(_: Request, error: ApiException) -> JSONResponse:
        return error_response(error.status_code, error.code, error.message)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        _: Request, __: RequestValidationError
    ) -> JSONResponse:
        return error_response(422, "INVALID_REQUEST", "请求参数无效")

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        _: Request, error: StarletteHTTPException
    ) -> JSONResponse:
        if error.status_code == 404:
            return error_response(404, "ROUTE_NOT_FOUND", "接口不存在")
        if error.status_code == 405:
            return error_response(405, "METHOD_NOT_ALLOWED", "请求方法不支持")
        return error_response(error.status_code, "INTERNAL_ERROR", "服务内部错误")

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(_: Request, __: Exception) -> JSONResponse:
        return error_response(500, "INTERNAL_ERROR", "服务内部错误")

    app.include_router(health_router)
    app.include_router(documents_router)
    return app


app = create_app(run_database_migrations=True)
