"""Business prompt validation does not reserve or invoke an AI operation."""

from longtian_api.repositories.analysis_settings import AnalysisSettingsRepository
from longtian_api.schemas.analysis_settings import (
    AnalysisSettings,
    AutomationUpdate,
    PromptStage,
    PromptUpdate,
)
from longtian_api.services.ai_settings import AISettingsService
from longtian_api.services.analysis_errors import AnalysisError


class AnalysisSettingsService:
    def __init__(self, database, ai_settings: AISettingsService, *, available=False):
        self.repository = AnalysisSettingsRepository(database, available=available)
        self._ai = ai_settings

    def read(self) -> AnalysisSettings:
        return self.repository.read()

    def save_prompt(
        self, stage: PromptStage, payload: PromptUpdate
    ) -> AnalysisSettings:
        text = payload.instructions
        try:
            if not 1 <= len(text) <= 8000 or not text.strip() or "\x00" in text:
                raise ValueError
            text.encode("utf-8", errors="strict")
        except (ValueError, UnicodeError):
            raise AnalysisError("invalid_analysis_prompt") from None
        return self.repository.save_prompt(stage, payload)

    def save_automation(self, payload: AutomationUpdate) -> AnalysisSettings:
        if payload.enabled:
            # Verify credentials exist; never expose or reserve them here.
            self._ai.read()
        return self.repository.save_automation(payload)
