"""Business prompt validation does not reserve or invoke an AI operation."""

from longtian_api.repositories.analysis_settings import AnalysisSettingsRepository
from longtian_api.schemas.analysis_settings import (
    AnalysisSettings,
    AutomationUpdate,
)
from longtian_api.services.ai_settings import AISettingsService


class AnalysisSettingsService:
    def __init__(self, database, ai_settings: AISettingsService, *, available=False):
        self.repository = AnalysisSettingsRepository(database, available=available)
        self._ai = ai_settings

    def read(self) -> AnalysisSettings:
        return self.repository.read()

    def save_automation(self, payload: AutomationUpdate) -> AnalysisSettings:
        if payload.enabled:
            # Verify credentials exist; never expose or reserve them here.
            self._ai.read()
        return self.repository.save_automation(payload)
