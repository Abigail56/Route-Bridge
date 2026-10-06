from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from routebridge.config.settings import get_settings
from routebridge.models import access, catalog, core, events, operations, orders, plans, platform, reliability, webhooks, workflows  # noqa: F401
from sqlmodel import SQLModel

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)
config.set_main_option("sqlalchemy.url", get_settings().database_url)
target_metadata = SQLModel.metadata


def include_object(obj, name, type_, reflected, compare_to):
    """Only compare what the models describe. Ignores PostGIS-managed objects (the generated `geog` columns and
    indexes, spatial_ref_sys, tiger/topology tables) so `alembic check` does not propose dropping them."""
    if type_ == "table":
        return not (reflected and compare_to is None)  # tables that exist in the DB but not in the models
    table = getattr(obj, "table", None)
    if table is not None and table.name not in target_metadata.tables:
        return False
    if type_ == "column" and name == "geog" and reflected:
        return False
    if type_ == "index" and name.endswith("_geog") and reflected:
        return False
    return True


def run_migrations_offline() -> None:
    context.configure(url=get_settings().database_url, target_metadata=target_metadata, literal_binds=True, dialect_opts={"paramstyle": "named"}, include_object=include_object)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(config.get_section(config.config_ini_section, {}), prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, include_object=include_object)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
