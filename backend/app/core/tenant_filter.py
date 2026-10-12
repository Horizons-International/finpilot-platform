from uuid import UUID

from sqlalchemy import event
from sqlalchemy.orm import ORMExecuteState, Session, with_loader_criteria

from app.core.database import Base


def _apply_tenant_filter(state: ORMExecuteState) -> None:
    """Apply the authenticated tenant to ORM SELECT queries."""
    if not state.is_select or state.is_column_load or state.is_relationship_load:
        return
    if state.execution_options.get("skip_tenant_filter", False):
        return

    tenant_id = state.session.info.get("tenant_id")
    # Authentication and trusted jobs may have no tenant context. Such sessions
    # must not be used for ordinary tenant-facing API requests.
    if tenant_id is None:
        return
    if not isinstance(tenant_id, UUID):
        raise ValueError("The active session tenant context must be a UUID.")

    statement = state.statement
    for mapper in Base.registry.mappers:
        model = mapper.class_
        if hasattr(model, "tenant_id"):
            statement = statement.options(
                with_loader_criteria(
                    model,
                    lambda entity: entity.tenant_id == tenant_id,
                    include_aliases=True,
                )
            )
    state.statement = statement


def _tenant_id_column_is_nullable(record: object) -> bool:
    """Return whether this mapped record's tenant_id column allows NULL."""
    table = getattr(type(record), "__table__", None)
    if table is None:
        return False

    column = table.columns.get("tenant_id")
    return bool(column is not None and column.nullable)


def _bind_new_records_to_active_tenant(
    session: Session,
    _flush_context: object,
    _instances: object | None,
) -> None:
    """Bind new tenant-owned records to trusted session context.

    A missing tenant is still an error for models whose tenant_id column is
    non-nullable. Models that explicitly permit a NULL tenant_id (such as audit
    events emitted before login establishes a tenant context) may keep it NULL.
    When a tenant context exists, missing IDs are filled from that context and
    conflicting IDs are rejected.
    """
    active_tenant = session.info.get("tenant_id")

    for record in session.new:
        if not hasattr(type(record), "tenant_id"):
            continue

        record_tenant = getattr(record, "tenant_id", None)

        if active_tenant is None:
            if record_tenant is None and not _tenant_id_column_is_nullable(record):
                raise ValueError(
                    f"Tenant context is required to create {type(record).__name__}."
                )
            # No trusted tenant context is available. Do not invent one for a
            # nullable/global row, and do not change an explicitly assigned ID.
            continue

        if not isinstance(active_tenant, UUID):
            raise ValueError("The active session tenant context must be a UUID.")

        if record_tenant is None:
            setattr(record, "tenant_id", active_tenant)
        elif record_tenant != active_tenant:
            raise ValueError("Cannot create a record for another tenant.")


def install_tenant_filter() -> None:
    """Install tenant query filtering and insert-time tenant binding once."""
    if not event.contains(Session, "do_orm_execute", _apply_tenant_filter):
        event.listen(Session, "do_orm_execute", _apply_tenant_filter)
    if not event.contains(Session, "before_flush", _bind_new_records_to_active_tenant):
        event.listen(Session, "before_flush", _bind_new_records_to_active_tenant)
