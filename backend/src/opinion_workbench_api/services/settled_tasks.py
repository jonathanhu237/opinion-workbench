"""Do not abandon SQLite threads or owned operations on coroutine cancellation."""

import asyncio
from collections.abc import Awaitable, Callable
from typing import ParamSpec, TypeVar

P = ParamSpec("P")
T = TypeVar("T")


async def settle(awaitable: Awaitable[T]) -> T:
    task = asyncio.ensure_future(awaitable)
    cancelled = False
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            cancelled = True
    # Retrieve failures even when the caller was cancelled (no unobserved task).
    result = task.result()
    if cancelled:
        raise asyncio.CancelledError
    return result


async def database_call(
    function: Callable[P, T], *args: P.args, **kwargs: P.kwargs
) -> T:
    return await settle(asyncio.to_thread(function, *args, **kwargs))
