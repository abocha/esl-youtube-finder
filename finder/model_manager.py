# finder/model_manager.py
import logging
import torch
from typing import Optional, Any
from terminal_logger import TerminalLogger
from .config import ENABLE_VIBE_CHECK, MODEL_ID

logger = TerminalLogger("esl_finder.models")


class ModelManager:
    """
    Singleton to manage lifecycle of heavy ML models (CEFR, Vibe/LLM).
    Ensures models are loaded only once and provides thread-safe access.
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ModelManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        self._cefr_pipeline = None
        self._vibe_model = None
        self._vibe_tokenizer = None

    def get_cefr_pipeline(self):
        """Lazy load CEFR classification pipeline."""
        if self._cefr_pipeline is None:
            logger.info("Loading CEFR model (AbdulSami/bert-base-cased-cefr)...")
            from transformers import pipeline

            self._cefr_pipeline = pipeline(
                "text-classification", model="AbdulSami/bert-base-cased-cefr"
            )
        return self._cefr_pipeline

    def get_vibe_model(self):
        """Lazy load Vibe (LLM) model and tokenizer."""
        if not ENABLE_VIBE_CHECK:
            return None, None

        if self._vibe_model is None:
            logger.info(f"Mz Downloading/Loading Transformers Model: {MODEL_ID}...")
            try:
                from transformers import (
                    AutoModelForCausalLM,
                    AutoTokenizer,
                    BitsAndBytesConfig,
                )

                quantization_config = BitsAndBytesConfig(
                    load_in_4bit=True,
                    bnb_4bit_compute_dtype=torch.float16,
                    bnb_4bit_use_double_quant=True,
                    bnb_4bit_quant_type="nf4",
                )

                self._vibe_tokenizer = AutoTokenizer.from_pretrained(
                    MODEL_ID, trust_remote_code=True
                )
                if self._vibe_tokenizer.pad_token is None:
                    self._vibe_tokenizer.pad_token = self._vibe_tokenizer.eos_token

                self._vibe_model = AutoModelForCausalLM.from_pretrained(
                    MODEL_ID,
                    device_map="auto",
                    quantization_config=quantization_config,
                    trust_remote_code=True,
                )
                logger.info("✅ Model loaded successfully with 4-bit quantization.")
            except Exception as e:
                logger.error(f"Failed to load Transformers model: {e}")
                raise e

        return self._vibe_model, self._vibe_tokenizer

    def preload_all(self):
        """Force load all enabled models (useful for initialization before threading)."""
        try:
            self.get_cefr_pipeline()
            self.get_vibe_model()
        except Exception as e:
            logger.warning(f"Model pre-loading warning: {e}")


# Global instance
model_manager = ModelManager()
