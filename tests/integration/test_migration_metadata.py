from alembic import command
from tests.integration.test_profile_persistence import migration_config
from tests.integration.test_profile_persistence import (
    profile_sessions as profile_sessions,
)


async def test_migrated_schema_has_no_alembic_metadata_diff(profile_sessions):
    async with profile_sessions() as session:
        connection = await session.connection()
        await connection.run_sync(lambda sync: command.check(migration_config(sync)))
