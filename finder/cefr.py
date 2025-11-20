# finder/cefr.py
from terminal_logger import TerminalLogger
from .config import TRANSCRIPT_MAX_CHARS
from .model_manager import model_manager

logger = TerminalLogger("esl_finder.cefr")


def get_pipeline():
    return model_manager.get_cefr_pipeline()


def estimate_cefr(text: str) -> dict:
    """Returns {label: str, numeric: int, score: float}"""
    if not text:
        return {"label": "N/A", "numeric": 0, "score": 0.0}

    # Smart sampling: Take middle chunk to avoid intros/outros
    if len(text) > TRANSCRIPT_MAX_CHARS:
        start = int(len(text) * 0.2)
        end = start + TRANSCRIPT_MAX_CHARS
        sample = text[start:end]
    else:
        sample = text

    try:
        clf = get_pipeline()
        # Truncation=True handles tokens > 512
        result = clf(sample, truncation=True, max_length=512)[0]

        label = result["label"]  # e.g., "B2"
        score = result["score"]

        # Map label to numeric for distance calc
        from .config import CEFR_TO_INT

        numeric = CEFR_TO_INT.get(label, 3)  # Default to B2 (3) if unknown

        return {"label": label, "numeric": numeric, "score": score}
    except Exception as e:
        logger.error(f"CEFR inference failed: {e}")
        return {"label": "Error", "numeric": 3, "score": 0.0}
