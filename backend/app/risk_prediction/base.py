from typing import Protocol

from app.risk_prediction.feature_schema import RiskPredictionFeatures


class RiskPredictionResult:
    def __init__(
        self,
        *,
        risk_probability: float,
    ) -> None:
        if not 0 <= risk_probability <= 1:
            raise ValueError(
                "risk_probability must be between 0 and 1.",
            )

        self.risk_probability = risk_probability


class RiskPredictionModel(Protocol):
    @property
    def version(self) -> str: ...

    def predict(
        self,
        features: RiskPredictionFeatures,
    ) -> RiskPredictionResult: ...
