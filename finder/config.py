# finder/config.py
import os
from pathlib import Path
from dotenv import load_dotenv
from dataclasses import dataclass, field
from typing import List, Dict

# Paths
ROOT_DIR = Path(__file__).parent.parent
load_dotenv(ROOT_DIR / ".env")


@dataclass
class Settings:
    # Paths
    root_dir: Path = ROOT_DIR
    cache_dir: Path = ROOT_DIR / "cache"
    transcript_cache_dir: Path = field(init=False)
    metadata_cache_dir: Path = field(init=False)

    # API Keys
    youtube_api_key: str = field(
        default_factory=lambda: os.getenv("YOUTUBE_API_KEY", "")
    )
    supadata_api_key: str = field(
        default_factory=lambda: os.getenv("SUPADATA_API_KEY", "")
    )

    # Constraints
    max_transcripts_per_run: int = 30
    transcript_max_chars: int = 4000
    supadata_request_delay: float = 1.0

    # Vibe Check
    enable_vibe_check: bool = field(
        default_factory=lambda: os.getenv("ENABLE_VIBE_CHECK", "true").lower() == "true"
    )
    model_id: str = field(
        default_factory=lambda: os.getenv("MODEL_ID", "microsoft/Phi-4-mini-instruct")
    )
    vibe_max_length: int = field(
        default_factory=lambda: int(os.getenv("VIBE_MAX_LENGTH", "10000"))
    )

    # CEFR
    cefr_levels: List[str] = field(
        default_factory=lambda: ["A1", "A2", "B1", "B2", "C1", "C2"]
    )
    cefr_to_int: Dict[str, int] = field(init=False)

    def __post_init__(self):
        self.transcript_cache_dir = self.cache_dir / "transcripts"
        self.metadata_cache_dir = self.cache_dir / "metadata"

        # Ensure dirs exist
        for d in [self.cache_dir, self.transcript_cache_dir, self.metadata_cache_dir]:
            d.mkdir(parents=True, exist_ok=True)

        self.cefr_to_int = {l: i for i, l in enumerate(self.cefr_levels)}


# Global instance
settings = Settings()

# Backward compatibility exports (to avoid breaking imports immediately)
# These can be deprecated later
YOUTUBE_API_KEY = settings.youtube_api_key
SUPADATA_API_KEY = settings.supadata_api_key
MAX_TRANSCRIPTS_PER_RUN = settings.max_transcripts_per_run
ENABLE_VIBE_CHECK = settings.enable_vibe_check
MODEL_ID = settings.model_id
VIBE_MAX_LENGTH = settings.vibe_max_length
TRANSCRIPT_MAX_CHARS = settings.transcript_max_chars
CEFR_TO_INT = settings.cefr_to_int
TRANSCRIPT_CACHE_DIR = settings.transcript_cache_dir
