"""Clear a database down to ONE owner: their account, the workspace(s) they own, and those workspaces' zones.

    python -m routebridge.tools.reset_data --keep-email owner@example.com          # dry run: only counts what would go
    python -m routebridge.tools.reset_data --keep-email owner@example.com --yes    # really delete
    python -m routebridge.tools.reset_data --keep-user user_2abc... --yes          # the owner by Clerk user id (when no email is saved)

Uses ROUTEBRIDGE_DATABASE_URL like the API. Everything happens in one transaction: it either all goes or nothing does.
Deleted: every other person, every other workspace, all shops, Dispatchers, orders, deliveries, payments, claims, rate cards,
notifications, sessions of work. Kept: the owner's `user` row and membership, their workspace(s) and zones, the platform
admin row of the owner, countries and operating areas, and the audit history (append-only by design). A workspace that
still has audit history cannot be removed, so it is emptied and suspended instead.
Back up first (deploy/windows/backup-now.ps1, or pg_dump).
"""
import argparse
import sys

from sqlalchemy import MetaData, and_, create_engine, func, not_, select, true

from routebridge.config.settings import get_settings

# never touched: migration state, PostGIS data, place reference data the zones hang on, and the append-only audit trails
UNTOUCHED = {"alembic_version", "spatial_ref_sys", "country", "operatingarea", "auditevent", "platformauditevent"}


def plan(connection, email: str | None, subject: str | None = None):
    meta = MetaData()
    meta.reflect(bind=connection)
    t = meta.tables
    who = t["user"].c.clerk_user_id == subject if subject else func.lower(t["user"].c.email) == (email or "").lower()
    owners = connection.execute(select(t["user"].c.id, t["user"].c.clerk_user_id).where(who)).all()
    if len(owners) != 1:
        hint = "" if subject else " Sign-in often saves no email: use --keep-user with the Clerk user id instead."
        raise SystemExit(f"Expected exactly one account with that {'user id' if subject else 'email'}, found {len(owners)}. Nothing changed.{hint}")
    owner_id, owner_subject = owners[0]
    m = t["tenantmembership"]
    keep_tenants = [row[0] for row in connection.execute(select(m.c.tenant_id).where(m.c.user_id == owner_id, m.c.role == "tenant_owner", m.c.status == "active")).all()]
    if not keep_tenants:
        raise SystemExit("That account owns no workspace. Nothing changed.")
    audited = {row[0] for row in connection.execute(select(t["auditevent"].c.tenant_id).distinct()).all()}

    conditions = {}
    for name, table in t.items():
        if name in UNTOUCHED:
            continue
        if name == "user":
            conditions[name] = table.c.id != owner_id
        elif name == "platformadmin":
            conditions[name] = table.c.clerk_user_id != owner_subject
        elif name == "tenantmembership":
            conditions[name] = not_(and_(table.c.user_id == owner_id, table.c.tenant_id.in_(keep_tenants)))
        elif name in ("servicezone", "tenantarea"):
            conditions[name] = not_(table.c.tenant_id.in_(keep_tenants))
        elif name == "tenant":
            conditions[name] = and_(not_(table.c.id.in_(keep_tenants)), not_(table.c.id.in_(audited)) if audited else true())
        else:
            conditions[name] = true()
    # children before parents
    order = [table for table in reversed(meta.sorted_tables) if table.name in conditions]
    shells = select(t["tenant"].c.id, t["tenant"].c.name).where(not_(t["tenant"].c.id.in_(keep_tenants)), t["tenant"].c.id.in_(audited)) if audited else None
    kept = connection.execute(select(t["tenant"].c.name).where(t["tenant"].c.id.in_(keep_tenants))).scalars().all()
    return t, order, conditions, shells, kept


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    keep = parser.add_mutually_exclusive_group(required=True)
    keep.add_argument("--keep-email")
    keep.add_argument("--keep-user", help="the owner's Clerk user id (user_...)")
    parser.add_argument("--yes", action="store_true", help="really delete (without it, nothing changes)")
    args = parser.parse_args(argv)
    engine = create_engine(get_settings().database_url)
    with engine.connect() as connection:
        transaction = connection.begin()
        t, order, conditions, shells, kept = plan(connection, args.keep_email, args.keep_user)
        print(f"Keeping: {args.keep_email or args.keep_user} as owner of {', '.join(kept)} (with its zones)")
        total = 0
        for table in order:
            count = connection.execute(select(func.count()).select_from(table).where(conditions[table.name])).scalar_one()
            if count:
                print(f"  {'delete' if args.yes else 'would delete'} {count:>6}  {table.name}")
                total += count
                if args.yes:
                    connection.execute(table.delete().where(conditions[table.name]))
        empty = connection.execute(shells).all() if shells is not None else []
        for _, name in empty:
            print(f"  {'suspend' if args.yes else 'would suspend'} emptied workspace with audit history: {name}")
        if args.yes and empty:
            connection.execute(t["tenant"].update().where(t["tenant"].c.id.in_([row[0] for row in empty])).values(status="suspended"))
        if args.yes:
            transaction.commit()
            print(f"Done: {total} rows deleted.")
        else:
            transaction.rollback()
            print(f"Dry run: {total} rows would be deleted. Nothing changed. Add --yes to do it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
