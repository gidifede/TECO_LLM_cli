"""Costanti centralizzate per i path relativi di prompt e directory di output."""

from dataclasses import dataclass
from pathlib import Path


class PromptFiles:
    """Path relativi dei file prompt (rispetto alla directory prompts/)."""

    US_AC = Path("user_stories/ac_based.md")
    US_PERSONA = Path("user_stories/persona_based.md")
    TC_FROM_US = Path("test_cases/from_user_stories.md")
    TC_FROM_REQ = Path("test_cases/from_requirements.md")
    EVAL_COHERENCE = Path("evaluation/coherence.md")


class OutputDirs:
    """Path relativi delle directory di output (rispetto alla directory output/)."""

    US_AC = Path("percorso_indiretto/ac_based/user_stories")
    US_PERSONA = Path("percorso_indiretto/persona_based/user_stories")
    TC_FROM_US_AC = Path("percorso_indiretto/ac_based/test_cases")
    TC_FROM_US_PERSONA = Path("percorso_indiretto/persona_based/test_cases")
    TC_FROM_REQ = Path("percorso_diretto/test_cases")
    EVALUATIONS = Path("valutazioni")

    @classmethod
    def all_subdirs(cls) -> list[Path]:
        """Restituisce tutte le sottodirectory di output definite."""
        return [
            cls.US_AC,
            cls.US_PERSONA,
            cls.TC_FROM_US_AC,
            cls.TC_FROM_US_PERSONA,
            cls.TC_FROM_REQ,
            cls.EVALUATIONS,
        ]


@dataclass(frozen=True)
class TCChain:
    """Definizione di una catena di produzione test cases."""

    key: str        # "direct", "indirect_ac", "indirect_persona"
    label: str      # Etichetta display
    tc_dir: Path    # Directory relativa dei TC (da OutputDirs)
    naming: str     # Descrizione naming convention


TC_CHAINS: dict[str, TCChain] = {
    "direct": TCChain(
        "direct",
        "Diretti (da Requisito)",
        OutputDirs.TC_FROM_REQ,
        "{REQ}.TC{NN}",
    ),
    "indirect_ac": TCChain(
        "indirect_ac",
        "Indiretti AC-based (da User Stories AC)",
        OutputDirs.TC_FROM_US_AC,
        "{REQ}.US{NN}.TC{NN}",
    ),
    "indirect_persona": TCChain(
        "indirect_persona",
        "Indiretti Persona-based (da User Stories Persona)",
        OutputDirs.TC_FROM_US_PERSONA,
        "{REQ}.US{NN}.TC{NN}",
    ),
}
