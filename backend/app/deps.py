from functools import lru_cache

from app.ai.client import LLM, build_llm
from app.config import get_settings


@lru_cache
def get_llm() -> LLM:
    return build_llm(get_settings())
