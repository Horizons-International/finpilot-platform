"""Central tenant enforcement for SQLAlchemy ORM and ORM/Core DML operations.

Authenticated API sessions are bound to ``db.info['tenant_id']`` by
``get_current_user``. Queries that omit tenant context in an authenticated
session fail closed. A deliberately unscoped operation must opt in with both
``skip_tenant_filter=True`` and a human-readable ``tenant_scope_reason``.

Raw SQL touching tenant-owned tables is rejected because SQLAlchemy cannot
safely add a tenant predicate to an arbitrary SQL string. Such operations must
be converted to ORM/Core statements or be explicitly reviewed and opted out.
"""

import re
from typing import Any, cast
from uuid import UUID

from sqlalchemy import event, inspect
from sqlalchemy.orm import ORMExecuteState, Session, with_loader_criteria
from sqlalchemy.sql import visitors
from sqlalchemy.sql.dml import Delete, Update
from sqlalchemy.sql.elements import TextClause
from sqlalchemy.sql.visitors import ExternallyTraversible

from app.core.database import Base

_SKIP_REASON_OPTION = "tenant_scope_reason"
_SKIP_FILTER_OPTION = "skip_tenant_filter"


def _tenant_mappers(state: ORMExecuteState) -> tuple[type, ...]:
    """Return mapped classes in this statement that own a tenant_id column."""
    return tuple(
        mapper.class_
        for mapper in state.all_mappers
        if hasattr(mapper.class_, "tenant_id")
    )


def _tenant_table_names() -> tuple[str, ...]:
    """Return database table names whose schema defines tenant ownership."""
    return tuple(
        table.name for table in Base.metadata.tables.values() if "tenant_id" in table.c
    )


def _raw_sql_mentions_tenant_table(statement: TextClause) -> bool:
    sql = str(statement)
    return any(
        re.search(
            rf"(?<![A-Za-z0-9_]){re.escape(name)}(?![A-Za-z0-9_])",
            sql,
            re.I,
        )
        for name in _tenant_table_names()
    )


def _select_element(from_clause: Any) -> Any | None:
    """Unwrap aliases/subqueries until reaching a SELECT or a regular table."""
    element = from_clause
    seen: set[int] = set()
    while id(element) not in seen:
        seen.add(id(element))
        if callable(getattr(element, "get_final_froms", None)):
            return element
        nested = getattr(element, "element", None)
        if nested is None or nested is element:
            return None
        element = nested
    return None


def _tenant_tables_in_from(from_clause: Any) -> tuple[Any, ...]:
    """Find tenant-owned tables in a Core FROM tree, including joins.

    Select-backed aliases are handled by recursively scoping their inner SELECT;
    a wrapper may not project tenant_id (for example Query.count() over only an
    ID column), so filtering the wrapper itself is not always possible.
    """
    left = getattr(from_clause, "left", None)
    right = getattr(from_clause, "right", None)
    if left is not None and right is not None:
        return tuple(
            dict.fromkeys(
                (*_tenant_tables_in_from(left), *_tenant_tables_in_from(right))
            )
        )

    if _select_element(from_clause) is not None:
        return ()

    columns = getattr(from_clause, "c", None)
    if columns is not None and "tenant_id" in columns:
        return (from_clause,)

    original = getattr(from_clause, "original", None)
    original_columns = getattr(original, "c", None)
    if original_columns is not None and "tenant_id" in original_columns:
        return (from_clause,)
    return ()


def _select_contains_tenant_tables(statement: Any) -> bool:
    """Detect tenant-owned tables anywhere in a statement's SELECT tree."""
    for element in visitors.iterate(statement):
        # ``visitors.iterate`` exposes its items as ExternallyTraversible,
        # whose public protocol does not declare ``get_final_froms``. Use a
        # guarded getattr so this remains compatible with SQLAlchemy's types.
        get_final_froms = getattr(element, "get_final_froms", None)
        if not callable(get_final_froms):
            continue
        for from_clause in get_final_froms():
            if _tenant_tables_in_from(from_clause):
                return True
    return False


def _scope_select_tree(statement: Any, tenant_id: UUID) -> Any:
    """Scope a Core/legacy SELECT and its nested SELECT expressions."""
    # First scope child SELECTs (including EXISTS/scalar subqueries and wrapped
    # FROMs). The root is handled separately below to avoid rewriting join
    # semantics for ordinary ORM queries that use with_loader_criteria.
    root = statement

    def scope_child(element: Any, **kw: Any) -> Any | None:
        if element is root or not callable(getattr(element, "get_final_froms", None)):
            return None
        if not _select_contains_tenant_tables(element):
            return None
        return cast(
            ExternallyTraversible,
            _scope_select_tree(element, tenant_id),
        )

    stop_on = tuple(getattr(statement, "_with_options", ()))
    rewritten = visitors.replacement_traverse(
        cast(ExternallyTraversible, statement),
        {"stop_on": stop_on},
        scope_child,
    )
    if rewritten is None:
        raise RuntimeError("Tenant filtering unexpectedly removed a SELECT statement.")
    statement = rewritten
    tenant_tables = tuple(
        table
        for from_clause in statement.get_final_froms()
        for table in _tenant_tables_in_from(from_clause)
    )
    for table in dict.fromkeys(tenant_tables):
        statement = statement.where(table.c.tenant_id == tenant_id)
    return statement


def _scope_nested_selects(statement: Any, tenant_id: UUID) -> Any:
    """Scope nested SELECTs without changing the root ORM query's join logic."""
    root = statement

    def scope_child(element: Any, **kw: Any) -> Any | None:
        if element is root or not callable(getattr(element, "get_final_froms", None)):
            return None
        if not _select_contains_tenant_tables(element):
            return None
        return cast(
            ExternallyTraversible,
            _scope_select_tree(element, tenant_id),
        )

    # ORM loader options are immutable option objects (LoaderCriteriaOption in
    # particular cannot be cloned). They do not contain SQL SELECT statements,
    # so keep them intact while rewriting nested selectable clauses.
    stop_on = tuple(getattr(statement, "_with_options", ()))
    rewritten = visitors.replacement_traverse(
        cast(ExternallyTraversible, statement),
        {"stop_on": stop_on},
        scope_child,
    )
    if rewritten is None:
        raise RuntimeError("Tenant filtering unexpectedly removed a SELECT statement.")
    return rewritten


def _require_tenant_context(state: ORMExecuteState) -> UUID | None:
    """Resolve the active tenant, fail closed for authenticated sessions."""
    tenant_id = state.session.info.get("tenant_id")
    if tenant_id is None:
        # The test suite's dedicated session factory enables a trusted test-only
        # escape hatch for fixture setup and assertions. Production sessions do
        # not have this flag: every tenant-owned query without a context fails.
        if state.session.info.get("tenant_user_id") is not None:
            raise RuntimeError(
                "Authenticated database session has no tenant context; "
                "refusing an unscoped tenant-owned operation."
            )
        if state.session.info.get("allow_unscoped_tenant_operations") is True:
            return None
        raise RuntimeError(
            "Tenant context is required for tenant-owned database operations."
        )

    if not isinstance(tenant_id, UUID):
        raise ValueError("The active session tenant context must be a UUID.")

    return tenant_id


def _apply_tenant_filter(state: ORMExecuteState) -> None:
    """Apply tenant predicates to ORM SELECT/UPDATE/DELETE statements."""
    statement = state.statement

    if state.execution_options.get(_SKIP_FILTER_OPTION, False):
        reason = state.execution_options.get(_SKIP_REASON_OPTION)
        if not isinstance(reason, str) or not reason.strip():
            raise RuntimeError(
                "skip_tenant_filter requires a non-empty tenant_scope_reason."
            )
        return

    # TextClause SQL cannot be safely rewritten to inject a WHERE predicate.
    # Prevent accidental bypasses in authenticated or tenant-bound sessions.
    if isinstance(statement, TextClause):
        if _raw_sql_mentions_tenant_table(statement):
            raise RuntimeError(
                "Raw SQL against tenant-owned tables is not allowed without an "
                "explicitly reviewed skip_tenant_filter operation. Use an ORM "
                "or Core statement so the tenant predicate can be enforced."
            )
        return

    if state.is_select:
        if state.is_column_load:
            # A refresh of an existing ORM instance may not expose the mapper in
            # state.all_mappers. Enforce the context and add a table predicate
            # directly so an instance accidentally loaded via a reviewed bypass
            # cannot refresh another tenant's columns after the session is bound.
            tenant_id = _require_tenant_context(state)
            if tenant_id is not None and _select_contains_tenant_tables(statement):
                state.statement = _scope_select_tree(statement, tenant_id)
            return

        tenant_models = _tenant_mappers(state)
        if not tenant_models:
            # Core and legacy Query.count() statements may not expose an ORM
            # mapper at the outer level. Inspect nested SELECTs too, because a
            # count subquery can project only IDs and omit tenant_id entirely.
            if not _select_contains_tenant_tables(statement):
                return
            tenant_id = _require_tenant_context(state)
            if tenant_id is None:
                return
            state.statement = _scope_select_tree(statement, tenant_id)
            return

        tenant_id = _require_tenant_context(state)
        if tenant_id is None:
            return

        statement = _scope_nested_selects(statement, tenant_id)
        for model in tenant_models:
            statement = statement.options(
                with_loader_criteria(
                    model,
                    lambda entity: entity.tenant_id == tenant_id,
                    include_aliases=True,
                )
            )
        state.statement = statement
        return

    if state.is_insert:
        tenant_models = _tenant_mappers(state)
        target_table = getattr(statement, "table", None)
        target_has_tenant = (
            target_table is not None and "tenant_id" in target_table.c
        ) or bool(tenant_models)
        if not target_has_tenant:
            return
        _require_tenant_context(state)
        raise RuntimeError(
            "Bulk INSERT into tenant-owned tables is disabled. Create ORM model "
            "instances so tenant ownership can be bound and validated in before_flush."
        )

    if not (state.is_update or state.is_delete):
        return

    tenant_models = _tenant_mappers(state)
    target_table = getattr(statement, "table", None)

    # Core UPDATE/DELETE statements can target a Table directly and may not
    # expose an ORM mapper. Add the same tenant predicate at the table level.
    if not tenant_models and target_table is not None and "tenant_id" in target_table.c:
        tenant_id = _require_tenant_context(state)
        if tenant_id is None:
            return
        # ORMExecuteState.statement is typed as Executable, which does not
        # declare ``where``. In this branch we've established a Core/ORM DML
        # statement, so cast to the concrete SQLAlchemy DML types before adding
        # the trusted tenant predicate.
        scoped_statement = cast(Update | Delete, statement).where(
            target_table.c.tenant_id == tenant_id
        )
        state.statement = scoped_statement
        return

    if not tenant_models:
        return

    tenant_id = _require_tenant_context(state)
    if tenant_id is None:
        return

    # with_loader_criteria also participates in ORM-enabled bulk UPDATE/DELETE
    # WHERE clauses. Each mapper is listed explicitly to cover multi-entity
    # statements without depending on the repository implementation.
    for model in tenant_models:
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


def _validate_record_ownership(
    session: Session,
    record: object,
    *,
    operation: str,
) -> None:
    """Reject cross-tenant or contextless mutations in authenticated sessions."""
    if not hasattr(type(record), "tenant_id"):
        return

    active_tenant = session.info.get("tenant_id")
    record_tenant = getattr(record, "tenant_id", None)
    authenticated = session.info.get("tenant_user_id") is not None

    if active_tenant is None:
        if authenticated:
            raise RuntimeError(
                f"Authenticated database session has no tenant context; "
                f"refusing to {operation} {type(record).__name__}."
            )
        if session.info.get("allow_unscoped_tenant_operations") is True:
            return
        raise RuntimeError(
            f"Tenant context is required to {operation} {type(record).__name__}."
        )

    if not isinstance(active_tenant, UUID):
        raise ValueError("The active session tenant context must be a UUID.")

    # Guard against tenant transfer: comparing only the current attribute would
    # let a cross-tenant object be reassigned to the active tenant before flush.
    state = inspect(record)
    if state is None:
        raise TypeError(f"Expected a mapped ORM instance for tenant-owned {operation}.")
    tenant_history = state.attrs.tenant_id.history
    original_tenants = tenant_history.deleted
    if original_tenants and any(value != active_tenant for value in original_tenants):
        raise ValueError(
            f"Cannot {operation} {type(record).__name__} that was previously owned "
            "by another tenant."
        )

    if record_tenant != active_tenant:
        raise ValueError(
            f"Cannot {operation} {type(record).__name__} outside the active tenant."
        )


def _bind_new_records_to_active_tenant(
    session: Session,
    _flush_context: object,
    _instances: object | None,
) -> None:
    """Bind new tenant records and validate existing records before mutation.

    Trusted bootstrap/maintenance sessions without an authenticated user can
    insert records with explicit tenant IDs, or rely on database constraints.
    Authenticated API sessions cannot write after losing their tenant context.
    """
    active_tenant = session.info.get("tenant_id")
    authenticated = session.info.get("tenant_user_id") is not None

    for record in session.new:
        if not hasattr(type(record), "tenant_id"):
            continue

        record_tenant = getattr(record, "tenant_id", None)

        if active_tenant is None:
            if authenticated:
                raise RuntimeError(
                    f"Authenticated database session has no tenant context; "
                    f"refusing to create {type(record).__name__}."
                )
            if session.info.get("allow_unscoped_tenant_operations") is True:
                if record_tenant is None and not _tenant_id_column_is_nullable(record):
                    raise ValueError(
                        f"Tenant context is required to create {type(record).__name__}."
                    )
                continue
            # Nullable global audit rows are the sole insert exception when an
            # unauthenticated operation has no tenant to attribute the event to.
            if (
                record_tenant is None
                and type(record).__name__ == "AuditLog"
                and _tenant_id_column_is_nullable(record)
            ):
                continue
            raise RuntimeError(
                f"Tenant context is required to create {type(record).__name__}."
            )

        if not isinstance(active_tenant, UUID):
            raise ValueError("The active session tenant context must be a UUID.")

        if record_tenant is None:
            setattr(record, "tenant_id", active_tenant)
        elif record_tenant != active_tenant:
            raise ValueError("Cannot create a record for another tenant.")

    for record in session.dirty:
        _validate_record_ownership(session, record, operation="update")

    for record in session.deleted:
        _validate_record_ownership(session, record, operation="delete")


def install_tenant_filter() -> None:
    """Install tenant filtering and mutation ownership validation once."""
    if not event.contains(Session, "do_orm_execute", _apply_tenant_filter):
        event.listen(Session, "do_orm_execute", _apply_tenant_filter)
    if not event.contains(Session, "before_flush", _bind_new_records_to_active_tenant):
        event.listen(Session, "before_flush", _bind_new_records_to_active_tenant)
