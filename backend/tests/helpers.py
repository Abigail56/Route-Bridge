from sqlalchemy import delete, text
from sqlmodel import Session


def reset_data(session: Session, models: tuple) -> None:
    """Clear tenant data between tests.

    On PostgreSQL the audit table is append-only (row trigger), so row-level DELETEs are rejected by design;
    TRUNCATE ... CASCADE is not a row operation and clears tenants plus everything that references them.
    Reference data (countries, operating areas) is kept.
    """
    if session.bind.dialect.name == "postgresql":
        session.exec(text("TRUNCATE tenant CASCADE"))
    else:
        for model in models:
            session.exec(delete(model))
    session.commit()
