from typing import Optional

from .telemetry.events import EventCategory, record_event
from .telemetry.reward_model import get_persona_prompt_suffix


class QATester:
    """QA Tester persona reading telemetry prompt suffix and recording QA events."""

    def generate_prompt(
        self, base_prompt: str, overrides_path: Optional[str] = None
    ) -> str:
        """Inject drifting prompt suffix from telemetry reward model."""
        suffix = get_persona_prompt_suffix("qa_tester", overrides_path=overrides_path)
        return f"{base_prompt}{suffix}" if suffix else base_prompt

    def run_qa_test(
        self,
        base_prompt: str,
        repo: str = "default",
        db_path: Optional[str] = None,
        overrides_path: Optional[str] = None,
    ) -> str:
        """Run QA test cycle with telemetry prompt tuning and recording."""
        prompt = self.generate_prompt(base_prompt, overrides_path=overrides_path)
        record_event(
            category=EventCategory.QA_FEEDBACK,
            persona="qa_tester",
            repo=repo,
            detail="qa_test_executed",
            state="positive",
            db_path=db_path,
        )
        return prompt
