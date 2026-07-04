import os
import sys
import asyncio
import json
import numpy as np
from dotenv import load_dotenv

# Ensure local package path is correctly configured
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from alloyrag.rag_system import get_rag_instance
from alloyrag.utils import logger
from alloyrag.utils_graph import amerge_entities

async def extract_all_nodes(graph_storage) -> list[dict]:
    """Helper to load all nodes and descriptions from graph storage."""
    nodes = []
    if hasattr(graph_storage, "_graph"):
        # NetworkX
        nx_graph = await graph_storage._get_graph()
        for node_id in nx_graph.nodes:
            attrs = nx_graph.nodes[node_id]
            nodes.append({
                "name": node_id,
                "type": attrs.get("entity_type", "Other"),
                "description": attrs.get("description", "")
            })
    elif hasattr(graph_storage, "client"):
        # Neo4j - fetch all nodes
        driver = graph_storage.client
        database = graph_storage.database
        workspace = graph_storage.workspace
        
        query = "MATCH (n:Entity {workspace: $workspace}) RETURN n.name as name, n.entity_type as type, n.description as description"
        async with driver.session(database=database) as session:
            result = await session.run(query, workspace=workspace)
            async for record in result:
                nodes.append({
                    "name": record["name"],
                    "type": record["type"],
                    "description": record["description"] or ""
                })
    return nodes

async def run_semantic_blocking(rag_instance, nodes: list[dict], threshold: float = 0.72) -> list[list[dict]]:
    """Step 1: Group nodes into candidate synonym blocks using name embeddings similarity."""
    if not nodes:
        return []

    names = [node["name"] for node in nodes]
    logger.info(f"Generating embeddings for {len(names)} entity names for semantic blocking...")
    
    # Generate embeddings via embedding func
    embeddings = await rag_instance.embedding_func(names)
    
    # Calculate cosine similarity matrix using numpy
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    # Handle zero norm safely
    norms[norms == 0] = 1.0
    normalized_embeddings = embeddings / norms
    
    similarity_matrix = np.dot(normalized_embeddings, normalized_embeddings.T)
    
    candidate_groups = []
    visited = set()
    
    for i in range(len(names)):
        if i in visited:
            continue
            
        # Find matches exceeding similarity threshold
        matches = np.where(similarity_matrix[i] > threshold)[0]
        if len(matches) > 1:
            group = [nodes[m] for m in matches]
            candidate_groups.append(group)
            visited.update(matches)
            
    logger.info(f"Semantic blocking identified {len(candidate_groups)} candidate duplicate/synonym groups.")
    return candidate_groups

async def verify_synonym_group_via_llm(rag_instance, group: list[dict]) -> dict:
    """Step 2: Use LLM to verify and select the best canonical representation for a candidate group."""
    llm_func = rag_instance.llm_model_func
    llm_name = rag_instance.llm_model_name
    llm_kwargs = rag_instance.llm_model_kwargs

    candidates_json = json.dumps(group, ensure_ascii=False, indent=2)
    
    prompt = f"""Вы — эксперт-лингвист и специалист по графам знаний. Перед вами группа кандидатов в синонимы из базы знаний R&D в области горной металлургии.
Кандидаты:
{candidates_json}

Определите, являются ли эти сущности синонимами, аббревиатурами или переводами друг друга (обозначают один и тот же реальный объект, процесс, материал, оборудование или понятие).
Если ДА, выберите наилучшее русскоязычное каноническое имя (canonical) для этой сущности, а остальные запишите как алиасы (aliases).
Если НЕТ (они обозначают разные вещи), верните "is_synonym": false.

Верните результат строго в формате JSON:
{{
  "is_synonym": true,
  "canonical": "каноническое_имя",
  "aliases": ["алиас1", "алиас2"]
}}
"""

    try:
        response_text = await llm_func(
            prompt,
            model=llm_name,
            response_format={"type": "json_object"},
            **llm_kwargs
        )
        data = json.loads(response_text)
        if data.get("is_synonym") and data.get("canonical"):
            return {alias: data["canonical"] for alias in data.get("aliases", []) if alias != data["canonical"]}
    except Exception as e:
        logger.error(f"Error verifying group { [n['name'] for n in group] }: {e}")
    return {}

async def run_merging_pipeline():
    """Main entry point to perform semantic blocking, LLM verification, and built-in entity merging."""
    rag = get_rag_instance()
    await rag.initialize_storages()

    graph_storage = rag.chunk_entity_relation_graph
    
    # 1. Load all nodes
    nodes = await extract_all_nodes(graph_storage)
    if not nodes:
        logger.info("Graph is empty. No entities to merge.")
        return

    # 2. Block/Group similar nodes semantically using embeddings
    candidate_groups = await run_semantic_blocking(rag, nodes)
    
    # 3. Verify each candidate group with the LLM
    synonym_map = {}
    for group in candidate_groups:
        mappings = await verify_synonym_group_via_llm(rag, group)
        synonym_map.update(mappings)

    # 4. Merge nodes using the built-in amerge_entities helper (synchronizes Vector, Graph, and KV store)
    if synonym_map:
        logger.info(f"Resolved synonym map to merge: {synonym_map}")
        # Group aliases by canonical target to perform batch merges
        canonical_to_aliases = {}
        for alias, canonical in synonym_map.items():
            canonical_to_aliases.setdefault(canonical, []).append(alias)
            
        for canonical, aliases in canonical_to_aliases.items():
            try:
                logger.info(f"Merging aliases {aliases} into canonical node '{canonical}'...")
                await amerge_entities(
                    chunk_entity_relation_graph=rag.chunk_entity_relation_graph,
                    entities_vdb=rag.entities_vdb,
                    relationships_vdb=rag.relationships_vdb,
                    source_entities=aliases,
                    target_entity=canonical,
                    entity_chunks_storage=rag.entity_chunks,
                    relation_chunks_storage=rag.relation_chunks
                )
            except Exception as e:
                logger.error(f"Failed to merge aliases into '{canonical}': {e}")
    else:
        logger.info("No synonyms detected by LLM. Nothing to merge.")

if __name__ == "__main__":
    load_dotenv()
    asyncio.run(run_merging_pipeline())
