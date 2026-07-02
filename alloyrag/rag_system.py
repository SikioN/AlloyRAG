import os
import sys
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

# Override default entity types guidance to focus on Material Science
PROMPTS["default_entity_types_guidance"] = """Classify each entity using one of the following types. If no type fits, use `Other`.

- Alloy: Alloy names, chemical systems, compositions, materials (e.g., Ni-based superalloy, Ti-6Al-4V, steel).
- Mode: Process modes, parameters, temperatures, heat treatments, conditions (e.g., hot rolling, annealing at 1000°C, aging for 4h, casting, cooling rate).
- Property: Material properties, characteristics, measurements, mechanical/physical/chemical tests (e.g., tensile strength, hardness, microhardness, elongation, yield strength, yield stress).
- Equipment: Experimental equipment, installations, machines, microscopes, furnaces, testing rigs.
- ResearchTeam: Research groups, laboratories, scientists, investigators, authors, institutes.
- Outcome: Experimental results, conclusions, effect descriptions, microstructural features (e.g., grain growth, phase transformation, recrystallization, dislocation, crack formation).
- Concept: Abstract ideas, theories, principles, beliefs (e.g., thermodynamic equilibrium, recrystallization kinetics, grain boundaries)."""

# Customize RAG response prompts to guide the LLM to highlight alloy-property relations and gaps
PROMPTS["rag_response"] = """---Role---

You are an expert AI assistant specializing in materials science and metallurgy. Your primary function is to answer user queries accurately by using both the structured Knowledge Graph and the text snippets in the provided Context.

---Goal---

Generate a comprehensive, well-structured answer to the user query.
Specifically highlight relations between:
1. Alloys (сплавы)
2. Modes of processing (режимы обработки)
3. Resulting Properties (свойства)
Also, identify and highlight any "gaps in data" (пробелы в данных) if the query asks about combinations of alloys, modes, or properties that are not present in the context.

---Instructions---

1. Step-by-Step Instruction:
  - Carefully determine the user's query intent to fully understand the user's information need.
  - Scrutinize both `Knowledge Graph Data` and `Document Chunks` in the Context. Identify and extract all pieces of information that are directly relevant.
  - Structure the response with clear headings (e.g., Summary, Alloys and Processing Modes, Resulting Properties, Gaps/Missing Data if applicable).
  - Track the reference_id of the document chunks that support your facts and cite them.
  - Generate a references section at the end.

2. Content & Grounding:
  - Strictly adhere to the provided context; DO NOT invent, assume, or infer any information not explicitly stated.
  - If the answer cannot be found in the Context, state clearly that you do not have enough information to answer. Do not guess.

3. Formatting & Language:
  - The response MUST be in the same language as the user query (typically Russian).
  - Use Markdown (headings, bold text, lists).

4. References Section Format:
  - Under heading: `### References` or `### Источники` (match query language).
  - Format: `* [n] Document Title`

{user_prompt}

---Context---

{context_data}
"""

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
        logger.info(f"SentenceTransformer {model_name} initialized. Dimension: {self.embedding_dim}")
        
    async def __call__(self, texts: list[str], context: str = "document", **kwargs) -> np.ndarray:
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
            None, 
            lambda: self.model.encode(processed_texts, show_progress_bar=False)
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

    llm_binding = os.getenv("LLM_BINDING", "ollama")
    llm_model = os.getenv("LLM_MODEL", "llama3.2:latest")
    llm_host = os.getenv("LLM_BINDING_HOST", "http://localhost:11434")

    # 1. Initialize LLM Complete Function
    llm_model_func = ollama_model_complete
    # timeout=300: llama3.2 on Mac can be slow generating long responses (17 entities + 25 relations context).
    # num_ctx=8192: Ollama's default context window is only 2048 tokens — not enough for full KG context.
    llm_model_kwargs = {
        "host": llm_host,
        "timeout": 300,
        "options": {
            "num_ctx": 8192,         # Expand context window (default in Ollama = 2048, too small)
            "num_predict": 2048,     # Max tokens in response
            "temperature": 0.1,      # Low temperature for factual/consistent answers
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
            supports_asymmetric=True
        )
    else:
        # Fallback to Ollama embedding
        from alloyrag.llm.ollama import ollama_embed
        embedding_func = EmbeddingFunc(
            embedding_dim=embedding_dim,
            func=functools.partial(
                ollama_embed.func,
                embed_model=embedding_model,
                host=llm_host
            ),
            model_name=embedding_model,
            supports_asymmetric=True
        )

    # 3. Create AlloyRAG Instance
    logger.info(f"Constructing AlloyRAG: LLM={llm_model}, Embeddings={embedding_model} ({embedding_dim} dim)...")
    _rag_instance = AlloyRAG(
        working_dir=working_dir,
        llm_model_func=llm_model_func,
        llm_model_name=llm_model,
        llm_model_kwargs=llm_model_kwargs,
        embedding_func=embedding_func,
        kv_storage="JsonKVStorage",
        vector_storage="NanoVectorDBStorage",
        graph_storage="NetworkXStorage",
        doc_status_storage="JsonDocStatusStorage",
        vlm_process_enable=False,
    )
    
    return _rag_instance

if __name__ == "__main__":
    # Test initialization
    print("Testing AlloyRAG initialization...")
    rag = get_rag_instance()
    print("AlloyRAG instance successfully initialized!")
