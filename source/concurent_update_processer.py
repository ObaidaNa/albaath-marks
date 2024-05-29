import asyncio
from collections import defaultdict
from typing import Any, Awaitable, Coroutine

from telegram import Update
from telegram.ext import BaseUpdateProcessor


class ConcurentUpdateProcessor(BaseUpdateProcessor):
    """Instance of :class:`telegram.ext.BaseUpdateProcessor` that process updates in
    concurrency, but it prevents concurrency per user, so that a user updates
    will be processed sequentially.
    :attr:`telegram.ext.ApplicationBuilder.concurrent_updates` is :obj:`int`.
    """

    __slots__ = ("_user_semaphore", "_max_updates_per_user")

    def __init__(
        self,
        max_concurrent_updates: int,
        max_updates_per_user: int,
        max_concurrent_per_user: int = 2,  # accept an update to cancel the first running task
    ):
        super().__init__(max_concurrent_updates)

        self._user_semaphore = defaultdict(
            lambda: asyncio.BoundedSemaphore(max_concurrent_per_user)
        )
        self._max_updates_per_user = max_updates_per_user

    async def do_process_update(
        self,
        update: Update,
        coroutine: "Awaitable[Any]",
    ) -> None:
        """Immediately awaits the coroutine, i.e. does not apply any additional processing.

        Args:
            update (:obj:`object`): The update to be processed.
            coroutine (:term:`Awaitable`): The coroutine that will be awaited to process the
                update.
        """
        if not update.effective_user:
            return await coroutine
        user_id = update.effective_user.id
        user_semaphore = self._user_semaphore[user_id]
        if (
            user_semaphore._waiters
            and len(user_semaphore._waiters) >= self._max_updates_per_user
        ):
            # drop the update
            return

        async with user_semaphore:
            await coroutine

    async def initialize(self) -> None:
        """Does nothing."""

    async def shutdown(self) -> None:
        """Does nothing."""

    @staticmethod
    async def wait_for_event(coroutine: Coroutine, event: asyncio.Event):
        await event.wait()
        return await coroutine
