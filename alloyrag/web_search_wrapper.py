"""
Web search fallback for AlloyRAG using the CRAG pattern.
Source: https://arxiv.org/abs/2401.15884

IMPORTANT: This module does NOT import from or modify:
  - alloyrag.operate
  - alloyrag.pipeline  
  - alloyrag.alloyrag (AlloyRAG class)
  - alloyrag.base

It ONLY calls public methods: rag.aquery() and rag.aquery_llm()
"""
from __future__ import annotations
import os
from alloyrag.utils import logger


# ── Поиск ────────────────────────────────────────────────────────────────────

async def search_web(query: str, max_results: int = 5) -> list[dict]:
    """Поиск. Движок выбирается через WEB_SEARCH_ENGINE."""
    engine = os.getenv("WEB_SEARCH_ENGINE", "duckduckgo").lower()
    if engine == "duckduckgo":
        return await _search_duckduckgo(query, max_results)
    # В будущем: brave, tavily, serper
    logger.warning(f"[web_search] Unknown engine '{engine}', falling back to duckduckgo")
    return await _search_duckduckgo(query, max_results)


async def _search_duckduckgo(query: str, max_results: int) -> list[dict]:
    """
    DuckDuckGo search using ddgs package (non-blocking thread pool execution).
    """
    try:
        import asyncio
        from ddgs import DDGS
        
        def sync_search():
            with DDGS() as ddgs:
                return list(ddgs.text(query, max_results=max_results))
                
        results = await asyncio.to_thread(sync_search)
        return results
    except Exception as e:
        logger.error(f"[web_search] DDGS search failed: {e}")
        return []


# ── Оценка контекста (CRAG) ───────────────────────────────────────────────────

def estimate_context_sufficiency(context: str | None, query: str) -> float:
    """
    Оценка достаточности контекста из базы [0.0 – 1.0].
    
    Пороги (CRAG paper, https://arxiv.org/abs/2401.15884):
      >= 0.7  → база достаточна (веб не нужен)
      >= 0.3  → база частичная (смешать с вебом)
      < 0.3   → база пустая/нерелевантна (только веб)
    """
    fail_marker = "[no-context]"  # маркер из PROMPTS["fail_response"]
    if not context or len(context.strip()) < 50 or fail_marker in context:
        return 0.0

    stop_words = {
        "что", "как", "где", "почему", "какой", "который", "это", "при", "и", "в", "на", "с", "по",
        "the", "is", "are", "what", "how", "why", "where", "a", "an", "and", "in", "on", "with", "by",
    }
    query_words = {w.lower() for w in query.split() if w.lower() not in stop_words}
    if not query_words:
        return 0.5

    context_lower = context.lower()
    matched = sum(1 for w in query_words if w in context_lower)
    score = matched / len(query_words)
    logger.debug(f"[web_search] Context score={score:.2f} ({matched}/{len(query_words)} words matched)")
    return score


# ── Форматирование ────────────────────────────────────────────────────────────

def format_web_results(results: list[dict], query: str) -> str:
    """Форматирует результаты поиска в текстовый блок для LLM."""
    if not results:
        return ""
    lines = [f"Результаты веб-поиска по запросу «{query}»:\n"]
    for i, r in enumerate(results, 1):
        title = r.get("title", "—")
        body  = r.get("body", r.get("snippet", ""))
        url   = r.get("href", r.get("url", ""))
        lines.append(f"[{i}] {title}\n{body}\nИсточник: {url}\n")
    return "\n".join(lines)


# ── Главный entry point ───────────────────────────────────────────────────────

async def hybrid_query(rag, query: str, mode: str = "hybrid") -> dict:
    """
    CRAG-style гибридный запрос.
    
    1. Получает контекст из базы через rag.aquery(only_need_context=True)
       → возвращает str (проверено: alloyrag.py L2107-2108)
    2. Оценивает достаточность
    3. При необходимости: веб-поиск + bypass LLM call
       → bypass передаёт system_prompt напрямую в LLM без .format()
         (проверено: alloyrag.py L2400-2402)
    
    Возвращает dict в формате aquery_llm():
      {"llm_response": {"content": str, "is_streaming": bool}, ...}
    """
    from alloyrag.base import QueryParam

    threshold   = float(os.getenv("WEB_SEARCH_CONFIDENCE_THRESHOLD", "0.3"))
    max_results = int(os.getenv("WEB_SEARCH_MAX_RESULTS", "5"))

    # ── Шаг 1: Получаем контекст ─────────────────────────────────────────────
    # aquery() возвращает str (alloyrag.py L2107-2108), НЕ объект с .content
    try:
        context_text: str = await rag.aquery(
            query,
            param=QueryParam(mode=mode, only_need_context=True, enable_rerank=False),
        )
    except Exception as e:
        logger.error(f"[hybrid_query] Context retrieval error: {e}")
        context_text = ""

    # ── Шаг 2: Оцениваем достаточность ───────────────────────────────────────
    score = estimate_context_sufficiency(context_text, query)
    logger.info(f"[hybrid_query] score={score:.2f}, threshold={threshold}")

    # ── Шаг 3a: Если в базе знаний есть хоть какая-то информация (score > 0.0), используем только базу ──
    if score > 0.0:
        logger.info(f"[hybrid_query] Source: knowledge_base (score={score:.2f} > 0.0)")
        return await rag.aquery_llm(
            query,
            param=QueryParam(mode=mode, enable_rerank=False, stream=False),
        )

    # ── Шаг 3b/3c: Веб-поиск ─────────────────────────────────────────────────
    logger.info(f"[hybrid_query] Triggering web search (score={score:.2f})")
    web_results = await search_web(query, max_results)
    web_context = format_web_results(web_results, query)

    if not web_results:
        # Веб ничего не вернул → откатываемся к базе как есть
        logger.warning("[hybrid_query] Web search empty, falling back to KB")
        return await rag.aquery_llm(
            query,
            param=QueryParam(mode=mode, enable_rerank=False, stream=False),
        )

    if score >= threshold and context_text and len(context_text.strip()) > 50:
        # Частичный контекст: база + веб
        logger.info("[hybrid_query] Source: hybrid (KB + web)")
        system_prompt = (
            "Используй следующую информацию для ответа на вопрос пользователя.\n\n"
            f"=== Информация из внутренней базы знаний ===\n{context_text}\n\n"
            f"=== Дополнительная информация из интернета ===\n{web_context}"
        )
        source_tag = "hybrid"
    else:
        # Базы нет — только веб
        logger.info("[hybrid_query] Source: web_search")
        system_prompt = (
            "Ответь на вопрос пользователя, используя следующую информацию из интернета.\n\n"
            f"=== Информация из интернета ===\n{web_context}"
        )
        source_tag = "web_search"

    # bypass: system_prompt передаётся напрямую в LLM (alloyrag.py L2400-2406)
    # stream=False чтобы получить str, а не AsyncIterator
    result = await rag.aquery_llm(
        query,
        param=QueryParam(mode="bypass", stream=False),
        system_prompt=system_prompt,
    )

    # Добавляем метаданные
    result["_web_source"] = source_tag
    result["_web_urls"] = [r.get("href", r.get("url", "")) for r in web_results]
    
    # Автоматически прикрепляем источники к тексту ответа для всех клиентов (включая WebUI)
    # Используем стандартный формат RAG для источников (### References и списки вида - [n] Web: URL)
    if source_tag != "knowledge_base" and web_results:
        content = result.get("llm_response", {}).get("content") or ""
        lines = []
        idx = 1
        for r in web_results:
            url = r.get('href', r.get('url', ''))
            if url:
                lines.append(f"- [{idx}] Web: {url}")
                idx += 1
        if lines:
            sources_block = "\n\n### References\n\n" + "\n".join(lines)
            result["llm_response"]["content"] = content + sources_block
            
    return result
