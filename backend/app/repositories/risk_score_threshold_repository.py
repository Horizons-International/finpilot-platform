from sqlalchemy.orm import Session

from app.models.risk_score_threshold import RiskScoreThreshold
from app.repositories.base_repository import BaseRepository
from app.utils.enums import CustomerRiskLevel


class RiskScoreThresholdRepository(BaseRepository[RiskScoreThreshold]):
    def __init__(self, db: Session) -> None:
        super().__init__(db, RiskScoreThreshold)

    def get_active_thresholds(self) -> list[RiskScoreThreshold]:
        return (
            self.db.query(RiskScoreThreshold)
            .filter(RiskScoreThreshold.is_active.is_(True))
            .order_by(
                RiskScoreThreshold.min_score.asc(),
            )
            .all()
        )

    def get_by_risk_level(
        self,
        risk_level: CustomerRiskLevel,
    ) -> RiskScoreThreshold | None:
        return (
            self.db.query(RiskScoreThreshold)
            .filter(
                RiskScoreThreshold.risk_level == risk_level,
                RiskScoreThreshold.is_active.is_(True),
            )
            .first()
        )
