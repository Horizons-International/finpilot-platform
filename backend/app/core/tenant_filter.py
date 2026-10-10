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

    # Authentication setup and trusted background jobs may not
    # have a tenant context. Such sessions must not be used for
    # ordinary tenant-facing API requests.
    if tenant_id is None:
        return

    statement = state.statement

    for mapper in Base.registry.mappers:
        model = mapper.class_

        # Only models that directly own tenant-scoped records
        # receive this automatic filter.
        if hasattr(model, "tenant_id"):
            statement = statement.options(
                with_loader_criteria(
                    model,
                    lambda entity: entity.tenant_id == tenant_id,
                    include_aliases=True,
                )
            )

    state.statement = statement


def install_tenant_filter() -> None:
    """Install the ORM listener once."""
    if not event.contains(Session, "do_orm_execute", _apply_tenant_filter):
        event.listen(Session, "do_orm_execute", _apply_tenant_filter)
