import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.config import get_settings
from app.database.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata
settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

_is_sqlite = settings.DATABASE_URL.startswith("sqlite")


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    # Pin the session to the ``public`` schema explicitly. Migrations use
    # unqualified table names and some CI/docker Postgres roles resolve an
    # empty search_path (e.g. when the ``public`` schema is absent from the
    # role's default "$user", public search_path), which fails the alembic
    # version table with "no schema has been selected to create in".
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args={"server_settings": {"search_path": "public"}},
    )

    # Ensure the schema exists in its own committed transaction. If this ran
    # on the same connection/transaction the migrations execute in, its
    # autobegin would make alembic treat ``context.begin_transaction()`` as a
    # nested savepoint; committing that leaves the outer auto-begun transaction
    # open and SQLAlchemy rolls the whole migration back on close (the alembic
    # step would report success while leaving a schema with zero tables).
    async with connectable.begin() as conn:
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS public"))

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
