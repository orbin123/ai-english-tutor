from functools import lru_cache
from langchain_openai import ChatOpenAI
from app.core.config import settings  

@lru_cache(maxsize=1)
def get_llm() -> ChatOpenAI:
    """
    Returns a configured ChatOpenAI client.
    Cached so we don't build a new client on every request.
    """
    return ChatOpenAI(
        model="gpt-4o-mini",   # cheap + fast for MVP
        temperature=0.7,
        api_key=settings.OPENAI_API_KEY,
    )