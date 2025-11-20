# finder/vibe.py
import json
import logging
import torch
from terminal_logger import TerminalLogger
from .config import VIBE_MAX_LENGTH
from .model_manager import model_manager

logger = TerminalLogger("esl_finder.vibe")


class VibeChecker:
    def _load_model(self):
        return model_manager.get_vibe_model()

    def check(
        self, text_sample: str, profile_summary: str, max_length: int = None
    ) -> float:
        if max_length is None:
            max_length = VIBE_MAX_LENGTH
        if not text_sample or len(text_sample) < 100:
            return 0.5

        try:
            model, tokenizer = self._load_model()
            if not model:
                return 0.5

            messages = [
                {
                    "role": "system",
                    "content": f"You are a helpful ESL content assistant. Student Profile: {profile_summary}",
                },
                {
                    "role": "user",
                    "content": f"""Analyze this transcript for an ESL student.
1. Is the tone calm, structured, and clear?
2. Is the content engaging and specific (not generic)?
3. Is the vocabulary appropriate?

Scoring Guide:
- 90-100: Excellent structure, clear speech, highly relevant, engaging.
- 70-89: Good, but slightly generic or repetitive.
- 50-69: Okay, but unstructured or fast/mumbled.
- <50: Irrelevant, chaotic, or poor quality.

Respond ONLY with JSON: {{"score": <0-100>, "reason": "<concise text>"}}.

Transcript:
{text_sample[:max_length]}...""",
                },
            ]

            input_ids = tokenizer.apply_chat_template(
                messages, return_tensors="pt", add_generation_prompt=True
            ).to(model.device)
            attention_mask = (input_ids != tokenizer.pad_token_id).long()

            outputs = model.generate(
                input_ids,
                attention_mask=attention_mask,
                pad_token_id=tokenizer.pad_token_id,
                max_new_tokens=300,
                do_sample=False,
            )

            response = tokenizer.decode(
                outputs[0][input_ids.shape[1] :], skip_special_tokens=True
            )
            logger.info(f"LLM Output: {response.strip()}")
            return self._parse_json_score(response)

        except Exception as e:
            logger.warn(f"Vibe inference failed: {e}")
            return 0.5

    def _parse_json_score(self, text: str) -> float:
        try:
            # 1. Strip markdown code blocks if present
            clean_text = text.strip()
            if "```" in clean_text:
                import re

                # Extract content inside ```json ... ``` or just ``` ... ```
                match = re.search(r"```(?:json)?(.*?)```", clean_text, re.DOTALL)
                if match:
                    clean_text = match.group(1).strip()

            # 2. Find JSON object boundaries
            start = clean_text.find("{")
            end = clean_text.rfind("}") + 1

            if start != -1 and end != -1:
                json_str = clean_text[start:end]
                data = json.loads(json_str)
                return float(data.get("score", 50)) / 100.0
        except Exception as e:
            logger.debug(f"JSON parse failed: {e} | Text: {text[:100]}...")
            pass
        return 0.5
