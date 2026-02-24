"""Costanti centralizzate per i path relativi di prompt e directory di output."""

from pathlib import Path


class PromptFiles:
    """Path relativi dei file prompt (rispetto alla directory prompts/)."""

    STAKEHOLDER = Path("stakeholder.md")
    REQUIREMENTS = Path("requirements.md")
    EVALUATOR = Path("evaluator.md")


class PromptDirs:
    """Directory contenenti prompt versionati."""

    INTERVIEWERS = Path("interviewers")


class OutputDirs:
    """Path relativi delle directory di output (rispetto alla directory run/)."""

    CONVERSATIONS = Path("conversations")
    REQUIREMENTS = Path("requirements")
    EVALUATIONS = Path("evaluations")
    COMPARISONS = Path("comparisons")

    @classmethod
    def all_subdirs(cls) -> list[Path]:
        """Restituisce tutte le sottodirectory di output definite."""
        return [cls.CONVERSATIONS, cls.REQUIREMENTS, cls.EVALUATIONS]
