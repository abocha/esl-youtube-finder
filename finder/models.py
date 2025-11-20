# finder/models.py
from pydantic import BaseModel, Field, field_validator, model_validator
from typing import List, Optional, Dict, Union, Any

class TopicPreferences(BaseModel):
    """Structured topic preferences with likes, dislikes, and sensitive topics."""
    strong_likes: List[str] = []
    mild_likes: List[str] = []
    dislikes: List[str] = []
    sensitive_or_avoid: List[str] = []  # CRITICAL: Never show these topics
    
    model_config = {"extra": "ignore"}

class CEFRLevel(BaseModel):
    """Structured CEFR level information."""
    current: str = "B2"
    target: str = "B2"
    confidence: float = 0.9
    evidence: str = ""
    
    model_config = {"extra": "ignore"}
    
    @field_validator('current', 'target', mode='before')
    @classmethod
    def normalize_level(cls, v: Any) -> str:
        """Normalize CEFR level to uppercase."""
        if isinstance(v, str):
            return v.upper()
        return "B2"

class LanguageFeatures(BaseModel):
    """Language learning preferences."""
    preferred_accents: List[str] = []
    speech_speed: str = "normal"  # "slow", "normal", "fast"
    subtitles_preference: str = "optional"  # "required", "preferred", "optional"
    notes: str = ""
    
    model_config = {"extra": "ignore"}

class VideoPreferences(BaseModel):
    min_duration_min: int = 4
    max_duration_min: int = 25
    prefer_playlists: bool = False
    preferred_formats: List[str] = []  # NEW: vlog, day-in-life, etc.
    avoid_formats: List[str] = []      # NEW: shorts, livestream, etc.
    notes: str = ""
    
    model_config = {"extra": "ignore"}

class StudentProfile(BaseModel):
    name: str = "Student"
    student_name: Optional[str] = None  # Alternative name field
    native_language: Optional[str] = None
    learning_language: Optional[str] = None
    
    # Enhanced CEFR structure (backward compatible)
    cefr: Union[CEFRLevel, str, Dict[str, Any]] = Field(default_factory=lambda: CEFRLevel())
    
    # For backward compatibility - derived from cefr
    target_level: str = Field(default="B2")
    
    # Enhanced topic preferences (backward compatible)
    topic_preferences: TopicPreferences = Field(default_factory=TopicPreferences)
    
    # Profile summary for LLM context
    profile_summary: Optional[str] = None
    
    # Legacy interests (kept for backward compatibility)
    interests: List[Union[str, Dict[str, Any]]] = []
    
    # Flattened avoid keywords (populated from topic_preferences + avoid_topics)
    avoid_keywords: List[str] = []
    
    # Language features
    language_features: LanguageFeatures = Field(default_factory=LanguageFeatures)
    
    # Complex structures captured for processing
    youtube_search_profile: Dict[str, Any] = {}
    seed_queries: List[str] = []
    
    video_preferences: VideoPreferences = Field(default_factory=VideoPreferences)

    model_config = {"extra": "ignore"}
    
    @field_validator('student_name', mode='before')
    @classmethod
    def sync_student_name(cls, v: Any, info) -> Optional[str]:
        """Use student_name if provided, otherwise fall back to name."""
        return v

    @field_validator('cefr', mode='before')
    @classmethod
    def handle_cefr_variants(cls, v: Any) -> CEFRLevel:
        """
        Handles multiple CEFR input formats:
        - Simple string: "B2"
        - Dict with current/target: {"current": "B1", "target": "B2"}
        - Full CEFRLevel object
        """
        if isinstance(v, CEFRLevel):
            return v
        elif isinstance(v, str):
            return CEFRLevel(current=v, target=v)
        elif isinstance(v, dict):
            return CEFRLevel(**v)
        else:
            return CEFRLevel()

    @model_validator(mode='after')
    def derive_target_level(self):
        """Ensure target_level is synced with cefr.target."""
        if isinstance(self.cefr, CEFRLevel):
            self.target_level = self.cefr.target
        elif isinstance(self.cefr, str):
            self.target_level = self.cefr
        return self

    @model_validator(mode='before')
    @classmethod
    def extract_topic_preferences(cls, data: Any) -> Any:
        """
        Extracts topic_preferences from the rich profile format.
        Handles backward compatibility with flat avoid_keywords.
        """
        if not isinstance(data, dict):
            return data
        
        # If topic_preferences already provided, use it
        if 'topic_preferences' not in data:
            tp_data = {}
            
            # Extract from root-level topic_preferences dict if present
            if 'topic_preferences' in data and isinstance(data['topic_preferences'], dict):
                raw_tp = data['topic_preferences']
                tp_data['strong_likes'] = raw_tp.get('strong_likes', [])
                tp_data['mild_likes'] = raw_tp.get('mild_likes', [])
                tp_data['dislikes'] = raw_tp.get('dislikes', [])
                tp_data['sensitive_or_avoid'] = raw_tp.get('sensitive_or_avoid', [])
            
            data['topic_preferences'] = TopicPreferences(**tp_data)
        
        return data

    @model_validator(mode='before')
    @classmethod
    def flatten_avoid_lists(cls, data: Any) -> Any:
        """
        Flattens all avoid sources into avoid_keywords for easy filtering.
        Sources:
        1. topic_preferences.dislikes
        2. topic_preferences.sensitive_or_avoid
        3. avoid_topics (legacy)
        4. youtube_search_profile.avoid_keywords
        """
        if not isinstance(data, dict):
            return data
        
        avoids = []
        
        # 1. Extract from topic_preferences if present
        if 'topic_preferences' in data and isinstance(data['topic_preferences'], dict):
            tp = data['topic_preferences']
            avoids.extend(tp.get('dislikes', []))
            avoids.extend(tp.get('sensitive_or_avoid', []))
        
        # 2. Handle 'avoid_topics': [{'keywords': [...]}]
        if 'avoid_topics' in data and isinstance(data['avoid_topics'], list):
            for item in data['avoid_topics']:
                if isinstance(item, dict) and 'keywords' in item:
                    avoids.extend(item['keywords'])
        
        # 3. Handle 'youtube_search_profile.avoid_keywords'
        if 'youtube_search_profile' in data:
            ysp = data['youtube_search_profile']
            if isinstance(ysp, dict):
                avoids.extend(ysp.get('avoid_keywords', []))

        # 4. Handle existing 'avoid_keywords' at root
        if 'avoid_keywords' in data:
             avoids.extend(data['avoid_keywords'])

        # Deduplicate and assign
        data['avoid_keywords'] = list(set(avoids))
        return data
    
    def get_search_queries(self, max_queries: int = 20) -> List[str]:
        """
        Aggregates queries from all possible sources in the profile,
        prioritizing explicit queries over generated ones.
        NOW SUPPORTS WEIGHTED SELECTION.
        """
        # Collect queries with weights
        weighted_queries = []
        
        # 1. High Priority: Explicit Seed Queries (weight=1.0)
        for q in self.seed_queries:
            weighted_queries.append((q, 1.0))
        
        # 2. High Priority: Search Profile Queries with weights
        if self.youtube_search_profile:
            # Root queries (weight=1.0)
            for q in self.youtube_search_profile.get("youtube_queries", []):
                weighted_queries.append((q, 1.0))
            for q in self.youtube_search_profile.get("yt_queries", []):
                weighted_queries.append((q, 1.0))
            
            # Primary topics with their weights
            for topic in self.youtube_search_profile.get("primary_topics", []):
                if isinstance(topic, dict):
                    weight = topic.get("weight", 0.8)
                    for q in topic.get("yt_queries", []):
                        weighted_queries.append((q, weight))
            
            # Secondary topics with their weights
            for topic in self.youtube_search_profile.get("secondary_topics", []):
                if isinstance(topic, dict):
                    weight = topic.get("weight", 0.4)
                    for q in topic.get("yt_queries", []):
                        weighted_queries.append((q, weight))
        
        # 3. Fallback: Generate from Interests if we have very few queries
        if len(weighted_queries) < 5:
            for i in self.interests:
                if isinstance(i, str):
                    weighted_queries.append((i, 0.5))
                elif isinstance(i, dict):
                    weight = i.get("weight", 0.5)
                    if "topic_keywords" in i:
                        keywords = i["topic_keywords"]
                        if keywords:
                            weighted_queries.append((f"{keywords[0]} vlog", weight))
                            if len(keywords) > 1:
                                weighted_queries.append((f"{keywords[1]} explained", weight))

        # 4. Sort by weight descending and deduplicate
        seen = set()
        sorted_queries = []
        for q, w in sorted(weighted_queries, key=lambda x: x[1], reverse=True):
            q_clean = q.strip()
            if q_clean and q_clean not in seen:
                sorted_queries.append(q_clean)
                seen.add(q_clean)
        
        # 5. Limit to max_queries
        final_list = sorted_queries[:max_queries]
        
        # Safety: If empty, add generic
        if not final_list:
            return [f"{self.target_level} English practice"]
            
        return final_list
    
    def get_profile_context(self) -> str:
        """
        Builds rich context string for LLM vibe checker.
        Uses all available profile data.
        """
        if self.profile_summary:
            # Use pre-written summary if available
            return self.profile_summary
        
        # Build from components
        parts = [
            f"Student: {self.student_name or self.name}",
        ]
        
        if isinstance(self.cefr, CEFRLevel):
            parts.append(f"Level: {self.cefr.current} → {self.cefr.target}")
            if self.cefr.evidence:
                parts.append(f"Evidence: {self.cefr.evidence[:200]}")  # Truncate
        else:
            parts.append(f"Level: {self.target_level}")
        
        if self.topic_preferences.strong_likes:
            parts.append(f"Likes: {', '.join(self.topic_preferences.strong_likes[:5])}")
        
        if self.topic_preferences.dislikes:
            parts.append(f"Dislikes: {', '.join(self.topic_preferences.dislikes[:5])}")
        
        if self.topic_preferences.sensitive_or_avoid:
            parts.append(f"AVOID: {', '.join(self.topic_preferences.sensitive_or_avoid)}")
        
        if self.video_preferences.preferred_formats:
            parts.append(f"Prefers: {', '.join(self.video_preferences.preferred_formats[:3])}")
        
        if self.language_features.speech_speed:
            parts.append(f"Speech: {self.language_features.speech_speed}")
        
        return " | ".join(parts)