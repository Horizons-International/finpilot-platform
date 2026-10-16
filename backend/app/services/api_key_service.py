import hashlib
import secrets
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.api_key import APIKey, APIKeyUsage
from app.repositories.api_key_repository import APIKeyRepository
from app.schemas.api_key import APIKeyCreate
from app.services.audit_service import AuditService
from app.services.tenant_access_audit import deny_tenant_access
from app.utils.date_time import utc_now
from app.utils.enums import APIKeyStatus, AuditEventType


class APIKeyService:
    """Manage API credentials within one tenant boundary."""

    def __init__(self, db: Session, tenant_id: UUID) -> None:
        current_tenant_id = db.info.get("tenant_id")
        if current_tenant_id is not None and current_tenant_id != tenant_id:
            raise ValueError("The session is already bound to another tenant.")
        db.info["tenant_id"] = tenant_id
        self.db = db
        self.tenant_id = tenant_id
        self.repository = APIKeyRepository(db, tenant_id=tenant_id)
        self.audit_service = AuditService(db)

    @staticmethod
    def hash_key(key: str) -> str:
        return hashlib.sha256(key.encode("utf-8")).hexdigest()

    @staticmethod
    def _generate_secret() -> str:
        # 256 bits of cryptographic randomness; this value is shown only once.
        return f"fp_live_{secrets.token_urlsafe(32)}"

    def create(
        self,
        *,
        data: APIKeyCreate,
        user_id: UUID,
        email: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> tuple[APIKey, str]:
        raw_key = self._generate_secret()
        api_key = APIKey(
            tenant_id=self.tenant_id,
            name=data.name,
            key_hash=self.hash_key(raw_key),
            permissions=list(data.permissions),
            status=APIKeyStatus.ACTIVE,
            created_by=user_id,
            created_at=utc_now(),
        )
        self.repository.create(api_key)
        self.audit_service.log_event(
            event_type=AuditEventType.API_KEY_CREATED,
            user_id=user_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="api_key",
            resource_id=api_key.id,
        )
        self.db.commit()
        self.db.refresh(api_key)
        return api_key, raw_key

    def list_all(self) -> list[APIKey]:
        return self.repository.list_keys()

    def get_by_id(self, api_key_id: UUID, *, for_update: bool = False) -> APIKey:
        api_key = self.repository.get_key(api_key_id, for_update=for_update)
        if api_key is None:
            deny_tenant_access(
                self.db,
                resource_type="api_key",
                resource_id=api_key_id,
                resource_name="API key",
            )
        return api_key

    def revoke(
        self,
        *,
        api_key_id: UUID,
        user_id: UUID,
        email: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> APIKey:
        api_key = self.get_by_id(api_key_id, for_update=True)
        if api_key.status != APIKeyStatus.REVOKED:
            api_key.status = APIKeyStatus.REVOKED
            api_key.revoked_at = utc_now()
            self.audit_service.log_event(
                event_type=AuditEventType.API_KEY_REVOKED,
                user_id=user_id,
                email=email,
                ip_address=ip_address,
                user_agent=user_agent,
                resource_type="api_key",
                resource_id=api_key.id,
            )
            self.db.commit()
            self.db.refresh(api_key)
        return api_key

    def list_usage(self, api_key_id: UUID, *, limit: int = 100) -> list[APIKeyUsage]:
        self.get_by_id(api_key_id)
        return self.repository.list_usage(api_key_id, limit=limit)
