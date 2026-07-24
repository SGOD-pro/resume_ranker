import logging
from typing import Any
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

logger = logging.getLogger(__name__)

class NotFoundError(Exception):
    def __init__(self, message: str):
        self.message = message

def rfc7807_response(
    error_type: str,
    title: str,
    status_code: int,
    detail: str,
    instance: str | None = None,
    invalid_params: list[dict[str, Any]] | None = None
) -> JSONResponse:
    content = {
        "type": f"https://resume-ranker.com/errors/{error_type}",
        "title": title,
        "status": status_code,
        "detail": detail,
    }
    if instance:
        content["instance"] = instance
    if invalid_params:
        content["invalid_params"] = invalid_params

    return JSONResponse(
        status_code=status_code,
        content=content,
        headers={"Content-Type": "application/problem+json"}
    )

def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(NotFoundError)
    async def not_found_handler(request: Request, exc: NotFoundError):
        return rfc7807_response(
            error_type="not-found",
            title="Resource Not Found",
            status_code=status.HTTP_404_NOT_FOUND,
            detail=exc.message,
            instance=request.url.path
        )

    @app.exception_handler(KeyError)
    async def key_error_handler(request: Request, exc: KeyError):
        msg = str(exc).strip("'\"")
        return rfc7807_response(
            error_type="not-found",
            title="Resource Not Found",
            status_code=status.HTTP_404_NOT_FOUND,
            detail=msg if "does not exist" in msg else f"Key error: {msg}",
            instance=request.url.path
        )

    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError):
        return rfc7807_response(
            error_type="bad-request",
            title="Bad Request",
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
            instance=request.url.path
        )

    @app.exception_handler(PermissionError)
    async def permission_error_handler(request: Request, exc: PermissionError):
        return rfc7807_response(
            error_type="forbidden",
            title="Forbidden",
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
            instance=request.url.path
        )

    @app.exception_handler(ValidationError)
    async def validation_error_handler(request: Request, exc: ValidationError):
        return rfc7807_response(
            error_type="validation-error",
            title="Validation Error",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
            instance=request.url.path,
            invalid_params=[{"name": str(e.get("loc")), "reason": e.get("msg")} for e in exc.errors()]
        )

    @app.exception_handler(RequestValidationError)
    async def request_validation_error_handler(request: Request, exc: RequestValidationError):
        return rfc7807_response(
            error_type="validation-error",
            title="Invalid Request Parameters",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Request validation failed.",
            instance=request.url.path,
            invalid_params=[{"name": "->".join(map(str, e.get("loc", []))), "reason": e.get("msg")} for e in exc.errors()]
        )
