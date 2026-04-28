from fastapi import APIRouter
from langchain_core.messages import HumanMessage
from app.ai.llm import get_llm

router = APIRouter(prefix="/debug/ai", tags=["debug"])


@router.get("/ping")
async def ping_llm():
    """
    TEMPORARY — S9 verification only.
    Sends one message to OpenAI, returns the reply.
    Trace should appear in LangSmith under project 'ai-english-coach'.
    DELETE this endpoint after S9 is verified.
    """
    llm = get_llm()
    response = await llm.ainvoke(
        [HumanMessage(content="Say 'LangSmith trace working' in 5 words exactly.")]
    )
    return {"reply": response.content}