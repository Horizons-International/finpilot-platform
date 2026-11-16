"""Tenant-scoped async queries for AI usage history and summaries."""

from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.models.ai_usage_log import AIUsageLog
from app.schemas.ai_usage import (
    AIUsageListResponse,
    AIUsageLogResponse,
    AIUsageSummaryResponse,
)


class AsyncAIUsageQueryService:
    """Read AI usage records without blocking the request event loop."""

    def __init__(self, db: AsyncSession, tenant_id: UUID) -> None:
        active_tenant_id = db.info.get("tenant_id")
        if active_tenant_id is not None and active_tenant_id != tenant_id:
            raise ValueError(
                "AI usage tenant does not match the active session tenant."
            )
        db.info["tenant_id"] = tenant_id
        self.db = db
        self.tenant_id = tenant_id

    def _filters(
        self, *, user_id: UUID | None = None, feature: str | None = None
    ) -> list[ColumnElement[bool]]:
        filters: list[ColumnElement[bool]] = [AIUsageLog.tenant_id == self.tenant_id]
        if user_id is not None:
            filters.append(AIUsageLog.user_id == user_id)
        if feature is not None:
            filters.append(AIUsageLog.feature == feature)
        return filters

    async def get_usage(
        self,
        *,
        limit: int = 100,
        user_id: UUID | None = None,
        feature: str | None = None,
    ) -> AIUsageListResponse:
        if not 1 <= limit <= 500:
            raise ValueError("AI usage limit must be between 1 and 500.")
        filters = self._filters(user_id=user_id, feature=feature)
        rows = await self.db.scalars(
            select(AIUsageLog)
            .where(*filters)
            .order_by(AIUsageLog.created_at.desc())
            .limit(limit)
        )
        total = int(
            await self.db.scalar(select(func.count(AIUsageLog.id)).where(*filters)) or 0
        )
        return AIUsageListResponse(
            items=[AIUsageLogResponse.model_validate(item) for item in rows.all()],
            total=total,
        )

    async def get_summary(
        self,
        *,
        user_id: UUID | None = None,
        feature: str | None = None,
    ) -> AIUsageSummaryResponse:
        row = (
            await self.db.execute(
                select(
                    func.count(AIUsageLog.id),
                    func.coalesce(
                        func.sum(
                            case((AIUsageLog.error_message.is_not(None), 1), else_=0)
                        ),
                        0,
                    ),
                    func.coalesce(func.sum(AIUsageLog.input_tokens), 0),
                    func.coalesce(func.sum(AIUsageLog.output_tokens), 0),
                    func.coalesce(func.avg(AIUsageLog.response_time), 0),
                ).where(*self._filters(user_id=user_id, feature=feature))
            )
        ).one()
        total_requests, total_errors, input_tokens, output_tokens, avg_response = row
        requests = int(total_requests or 0)
        errors = int(total_errors or 0)
        return AIUsageSummaryResponse(
            total_requests=requests,
            total_errors=errors,
            successful_requests=requests - errors,
            total_input_tokens=int(input_tokens or 0),
            total_output_tokens=int(output_tokens or 0),
            average_response_time=float(avg_response or 0),
        )
