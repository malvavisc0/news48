"""Alembic environment configuration.

Reads DATABASE_URL from the environment and imports all models
so that Base.metadata contains the full schema for autogenerate.
"""

import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import Base and all models so they are registered on Base.metadata
from news48.core.database.connection import Base  # noqa: E402

target_metadata = Base.metadata

# Import all models so they register themselves on Base.metadata
import news48.core.database.models  # noqa: E402, F401


def get_url() -> str:
    """Read DATABASE_URL from environment, with a sensible default."""
    return os.getenv(
        "DATABASE_URL",
        "mysql+mysqlconnector://news48:news48@localhost:3306/news48",
    )


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL and not an Engine,
    though an Engine is acceptable here as well.  By skipping the Engine
    creation we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.
    """
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine and associate a
    connection with the context.
    """
    configuration = config.get_section(config.config_ini_section)
    configuration["sqlalchemy.url"] = get_url()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


# We only use online migrations
run_migrations_online()
