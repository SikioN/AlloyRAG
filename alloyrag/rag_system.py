import os
import functools
import numpy as np
from dotenv import load_dotenv

# Ensure local package path is correctly configured
from alloyrag import AlloyRAG
from alloyrag.llm.ollama import ollama_model_complete
from alloyrag.utils import EmbeddingFunc, logger
from alloyrag.prompt import PROMPTS

# Load environment variables
load_dotenv()

# Override default entity types guidance to focus on Metallurgical R&D Case Study
PROMPTS[
    "default_entity_types_guidance"
] = """Classify each entity using one of the following types. If no type fits, use `Other`.

- Material: Metals, alloys, compositions, solutions, chemical compounds, or residues (e.g., Ni-based superalloy, сульфаты, католит, медный штейн, никелевая руда).
- Process: Technological processes, chemical reactions, experimental modes, or treatments (e.g., кучное выщелачивание, электроэкстракция, пиролиз, обессоливание воды).
- Equipment: Experimental or industrial setups, furnaces, cells, or measurement rigs (e.g., ванны электроэкстракции, печь взвешенной плавки (ПВП), диафрагменные ячейки).
- Property: Physical, mechanical, chemical, or economic properties (e.g., сухой остаток, выход металла, капитальные затраты).
- Experiment: Specific R&D test protocols, parameter sets, or trial runs (e.g., опыт №5, выщелачивание при 90°C).
- Publication: Patents, scientific papers, technical reports, or theses (e.g., Доклад Вострикова, патент РФ №12345).
- Expert: Laboratory teams, scientists, investigators, or competency owners (e.g., Институт Гипроникель, ТренингБутик, Востриков Н.М.).
- Facility: Geographical locations, plants, laboratories, or factories (e.g., Россия, Харьявалта, обогатительная фабрика).
- Condition: Environmental, geographic, or physical conditions (e.g., холодный климат, глубокие горизонты, мировая практика, отечественная практика).
- Parameter: Numeric metrics, ranges, or targets (e.g., сухой остаток <= 1000 мг/дм³, сульфаты 200-300 мг/л).
- Indicator: Technical or economic performance indicators (e.g., производительность: от 100 т/сут, капекс, опекс).

During relationship extraction, always represent relationships using these keywords:
- uses_material: A process/equipment uses a specific material.
- operates_at_condition: A process/experiment runs at specific parameters/conditions (temperature, flow rate, concentrations).
- produces_output: A process/experiment yields a specific product, property, or outcome.
- described_in: A process, material, or experiment is documented in a publication.
- validated_by: A fact or relation is validated by an experiment, expert, or publication.
- contradicts: Highlight conflicting facts or parameters across different sources."""

# Customize RAG response prompts to guide the LLM to highlight metallurgical relations and gaps
PROMPTS["rag_response"] = """---Role---

You are an expert AI assistant specializing in metallurgy, mineral processing, and industrial gas/water treatment. Your primary function is to answer user queries accurately by using the structured Knowledge Graph and the text snippets in the provided Context.

---Goal---

Generate a comprehensive, well-structured, and precise response in Russian to the user query.

Specifically highlight:
1. Relations between Materials, Processes, Equipment, and resulting Properties (using uses_material, operates_at_condition, produces_output relationships).
2. Numeric thresholds, ranges, and target values (e.g. concentrations, flow rates, temperatures, costs).
3. Geographical split: distinguish domestic (отечественная практика) vs. foreign (зарубежная практика) solutions where applicable.
4. "Gaps in data" (пробелы в данных) if the query asks about combinations of materials, modes, or properties that are not present or documented.

---Instructions---

1. Step-by-Step response construction:
   - Analyze the query's intent (e.g., checking for specific concentration limits, circulation rates, or gold/silver distribution).
   - Review both `Knowledge Graph Data` and `Document Chunks`. Match entities and numeric values carefully.
   - Structure the response with clear headings (e.g., Суммарный ответ, Технологические решения, Параметры и показатели, Отечественная vs. Зарубежная практика, Пробелы в данных / Ограничения).
   - Cite source documents with `[n]` referencing the source ID or title.
   - Output a list of sources at the end under `### Источники`.

2. Content & Grounding:
   - Strictly adhere to the provided context; DO NOT invent or assume any facts.
   - If information for a specific constraint (e.g. "≤1000 мг/дм³") is not found, state that explicitly.

{user_prompt}

---Context---

{context_data}
"""

# Dynamic prompt injection for Entity Extraction (adds numerical constraints and geography rules)
extraction_guidance = """
  - **Numeric & Geographic Focus:** Pay close attention to numerical values, ranges, and units (e.g., concentrations like "200–300 мг/л", limits like "≤1000 мг/дм³", flow rates, temperatures). Always include these numeric values and their exact units in the descriptions.
  - **Geographic & Practice Context:** Distinguish between domestic (отечественная практика, РФ) and foreign (зарубежная практика, импортные аналоги, конкретные страны) technologies and record this in the entity description and facility/condition relationships.
"""

if "entity_extraction_json_system_prompt" in PROMPTS:
    PROMPTS["entity_extraction_json_system_prompt"] = PROMPTS[
        "entity_extraction_json_system_prompt"
    ].replace("1. **Entity Extraction:**", "1. **Entity Extraction:**" + extraction_guidance)

if "entity_extraction_system_prompt" in PROMPTS:
    PROMPTS["entity_extraction_system_prompt"] = PROMPTS[
        "entity_extraction_system_prompt"
    ].replace("1. **Entity Extraction:**", "1. **Entity Extraction:**" + extraction_guidance)


class LocalSentenceTransformerEmbedder:
    """Custom embedding wrapper that loads SentenceTransformer locally.
    Bypasses slow Ollama model pull for embeddings.
    """

    def __init__(self, model_name="all-MiniLM-L6-v2"):
        logger.info(f"Initializing local SentenceTransformer model: {model_name}...")
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(model_name)
        self.model_name = model_name
        self.embedding_dim = self.model.get_embedding_dimension()
        logger.info(
            f"SentenceTransformer {model_name} initialized. Dimension: {self.embedding_dim}"
        )

    async def __call__(
        self, texts: list[str], context: str = "document", **kwargs
    ) -> np.ndarray:
        import asyncio

        # sentence-transformers encode is synchronous, run in executor to avoid blocking the event loop
        loop = asyncio.get_event_loop()
        # Add prefixes if model expects them (like e5 models which expect "query: " or "passage: ")
        processed_texts = []
        is_e5 = "e5" in self.model_name.lower()
        for text in texts:
            if is_e5:
                if context == "query":
                    processed_texts.append(f"query: {text}")
                else:
                    processed_texts.append(f"passage: {text}")
            else:
                processed_texts.append(text)

        embeddings = await loop.run_in_executor(
            None, lambda: self.model.encode(processed_texts, show_progress_bar=False)
        )
        return np.array(embeddings)


_rag_instance = None


def get_rag_instance() -> AlloyRAG:
    global _rag_instance
    if _rag_instance is not None:
        return _rag_instance

    working_dir = os.getenv("WORKING_DIR", "./rag_storage")
    input_dir = os.getenv("INPUT_DIR", "./inputs")

    os.makedirs(working_dir, exist_ok=True)
    os.makedirs(input_dir, exist_ok=True)

    llm_binding = os.getenv("LLM_BINDING", "ollama").lower()
    llm_model = os.getenv("LLM_MODEL", "llama3.2:latest")
    llm_host = os.getenv("LLM_BINDING_HOST", "http://localhost:11434")

    # 1. Initialize LLM Complete Function
    if llm_binding == "openai":
        from alloyrag.llm.openai import openai_complete
        llm_model_func = openai_complete
        # Set up kwargs for OpenAI or OpenAI-compatible endpoint
        llm_model_kwargs = {
            "api_key": os.getenv("LLM_BINDING_API_KEY") or os.getenv("OPENAI_API_KEY"),
            "base_url": os.getenv("LLM_BINDING_HOST") or os.getenv("OPENAI_BASE_URL"),
            "timeout": 300,
        }
        # If no specific model is set in env, default to gpt-4o-mini
        if os.getenv("LLM_MODEL") is None:
            llm_model = "gpt-4o-mini"
    else:
        llm_model_func = ollama_model_complete
        # timeout=300: llama3.2 on Mac can be slow generating long responses (17 entities + 25 relations context).
        # num_ctx=8192: Ollama's default context window is only 2048 tokens — not enough for full KG context.
        llm_model_kwargs = {
            "host": llm_host,
            "timeout": 300,
            "options": {
                "num_ctx": 8192,  # Expand context window (default in Ollama = 2048, too small)
                "num_predict": 2048,  # Max tokens in response
                "temperature": 0.1,  # Low temperature for factual/consistent answers
            },
        }

    # 2. Initialize Embedding Function
    embedding_binding = os.getenv("EMBEDDING_BINDING", "local_huggingface")
    embedding_model = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
    embedding_dim = int(os.getenv("EMBEDDING_DIM", "384"))

    if embedding_binding == "local_huggingface":
        embedder = LocalSentenceTransformerEmbedder(model_name=embedding_model)
        # Wrap into AlloyRAG's EmbeddingFunc
        embedding_func = EmbeddingFunc(
            embedding_dim=embedder.embedding_dim,
            func=embedder,
            model_name=embedding_model,
            supports_asymmetric=True,
        )
    elif embedding_binding == "openai":
        from alloyrag.llm.openai import openai_embed
        embedding_func = EmbeddingFunc(
            embedding_dim=embedding_dim,
            func=functools.partial(
                openai_embed.func,
                model=embedding_model,
                base_url=os.getenv("EMBEDDING_BINDING_HOST") or os.getenv("LLM_BINDING_HOST"),
                api_key=os.getenv("EMBEDDING_BINDING_API_KEY") or os.getenv("LLM_BINDING_API_KEY"),
            ),
            model_name=embedding_model,
            supports_asymmetric=True,
        )
    else:
        # Fallback to Ollama embedding
        from alloyrag.llm.ollama import ollama_embed

        embedding_func = EmbeddingFunc(
            embedding_dim=embedding_dim,
            func=functools.partial(
                ollama_embed.func, embed_model=embedding_model, host=llm_host
            ),
            model_name=embedding_model,
            supports_asymmetric=True,
        )

    # 3. Create AlloyRAG Instance
    logger.info(
        f"Constructing AlloyRAG: LLM={llm_model}, Embeddings={embedding_model} ({embedding_dim} dim)..."
    )
    _rag_instance = AlloyRAG(
        working_dir=working_dir,
        llm_model_func=llm_model_func,
        llm_model_name=llm_model,
        llm_model_kwargs=llm_model_kwargs,
        embedding_func=embedding_func,
        kv_storage=os.getenv("ALLOYRAG_KV_STORAGE") or os.getenv("KV_STORAGE") or "JsonKVStorage",
        vector_storage=os.getenv("ALLOYRAG_VECTOR_STORAGE") or os.getenv("VECTOR_STORAGE") or "NanoVectorDBStorage",
        graph_storage=os.getenv("ALLOYRAG_GRAPH_STORAGE") or os.getenv("GRAPH_STORAGE") or "NetworkXStorage",
        doc_status_storage=os.getenv("ALLOYRAG_DOC_STATUS_STORAGE") or os.getenv("DOC_STATUS_STORAGE") or "JsonDocStatusStorage",
        vlm_process_enable=False,
    )

    return _rag_instance


if __name__ == "__main__":
    # Test initialization
    print("Testing AlloyRAG initialization...")
    rag = get_rag_instance()
    print("AlloyRAG instance successfully initialized!")
