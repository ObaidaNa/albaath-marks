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

    __slots__ = ("_events", "_max_updates_per_user")

    def __init__(self, max_concurrent_updates: int, max_updates_per_user: int):
        super().__init__(max_concurrent_updates)
        self._events = defaultdict(lambda: defaultdict(list))
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
        if not update.effective_chat or not update.effective_user:
            return await coroutine
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id
        user_event_list = self._events[chat_id][user_id]
        if len(user_event_list) >= self._max_updates_per_user:
            # drop the update
            del coroutine
            return
        new_event = asyncio.Event()
        try:
            if user_event_list:
                prev_event = user_event_list[-1]
                user_event_list.append(new_event)
                await self.wait_for_event(coroutine, prev_event)
                user_event_list.pop(0)

            else:
                user_event_list.append(new_event)
                await coroutine

            # if there's no one is waiting me
            # then there's no one will delete me, So I delete my self
            if len(user_event_list) == 1:
                user_event_list.pop(0)
        finally:
            new_event.set()

    async def initialize(self) -> None:
        """Does nothing."""

    async def shutdown(self) -> None:
        """Does nothing."""

    @staticmethod
    async def wait_for_event(coroutine: Coroutine, event: asyncio.Event):
        await event.wait()
        return await coroutine
