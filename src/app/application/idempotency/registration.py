from collections.abc import Callable
from datetime import datetime

from app.application.commands.profiles.create_default.command import (
    CreateDefaultProfileCommand,
)
from app.application.commands.profiles.create_default.handler import (
    CreateDefaultProfileHandler,
)
from app.application.ports.deduplication import EventDeduplicationPort


class RegistrationDeduplication:
    """Application boundary wrapper executed inside the command's existing UoW."""

    def __init__(
        self,
        handler: CreateDefaultProfileHandler,
        inbox: EventDeduplicationPort,
        clock: Callable[[], datetime],
    ) -> None:
        self._handler = handler
        self._inbox = inbox
        self._clock = clock

    async def __call__(self, command: CreateDefaultProfileCommand) -> None:
        if command.event_id is not None:
            first = await self._inbox.mark_processed_if_absent(
                command.event_id, self._clock()
            )
            if not first:
                return
        await self._handler(command)
