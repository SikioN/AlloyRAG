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

async def merge_nodes_networkx(graph_storage, synonym_dict: dict):
    """Merge nodes in NetworkX storage."""
    import networkx as nx
    from alloyrag.kg.networkx_impl import NetworkXStorage

    nx_graph = await graph_storage._get_graph()
    logger.info(f"Current NetworkX graph: {len(nx_graph.nodes)} nodes, {len(nx_graph.edges)} edges")

    modified = False
    for alias, canonical in synonym_dict.items():
        # Find exact or case-insensitive matches for alias in graph nodes
        matching_aliases = [n for n in nx_graph.nodes if n.lower() == alias.lower()]
        if not matching_aliases:
            continue

        for alias_node in matching_aliases:
            if alias_node == canonical:
                continue

            logger.info(f"Merging NetworkX node '{alias_node}' into '{canonical}'...")
            
            # Ensure canonical node exists
            if canonical not in nx_graph:
                # Copy attributes from alias
                attrs = nx_graph.nodes[alias_node].copy()
                nx_graph.add_node(canonical, **attrs)
            else:
                # Merge descriptions
                canonical_desc = nx_graph.nodes[canonical].get("description", "")
                alias_desc = nx_graph.nodes[alias_node].get("description", "")
                if alias_desc and alias_desc not in canonical_desc:
                    nx_graph.nodes[canonical]["description"] = f"{canonical_desc}\n[Синоним: {alias_node}]: {alias_desc}".strip()

            # Redirect edges
            for neighbor in list(nx_graph.neighbors(alias_node)):
                edge_data = nx_graph.get_edge_data(alias_node, neighbor)
                if not nx_graph.has_edge(canonical, neighbor):
                    nx_graph.add_edge(canonical, neighbor, **edge_data)
                
            # Remove the alias node
            nx_graph.remove_node(alias_node)
            modified = True

    if modified:
        logger.info("Saving updated NetworkX graph to disk...")
        NetworkXStorage.write_nx_graph(
            nx_graph, graph_storage._graphml_xml_file, graph_storage.workspace
        )
        logger.info(f"Merged NetworkX graph: {len(nx_graph.nodes)} nodes, {len(nx_graph.edges)} edges")
    else:
        logger.info("No NetworkX nodes needed merging.")

async def merge_nodes_neo4j(graph_storage, synonym_dict: dict):
    """Merge nodes in Neo4j storage using Cypher queries."""
    driver = graph_storage.client
    database = graph_storage.database
    workspace = graph_storage.workspace

    logger.info(f"Running Neo4j synonym merging on database '{database}', workspace '{workspace}'...")
    
    fallback_query = """
    MATCH (alias:Entity {name: $alias, workspace: $workspace})
    MERGE (canonical:Entity {name: $canonical, workspace: $workspace})
    ON CREATE SET canonical.description = alias.description, canonical.entity_type = alias.entity_type
    ON MATCH SET canonical.description = 
        CASE 
            WHEN alias.description IS NOT NULL AND NOT canonical.description CONTAINS alias.description
            THEN canonical.description + "\\n[Синоним: " + $alias + "]: " + alias.description
            ELSE canonical.description
        END
    WITH alias, canonical
    // Redirection of standard relations
    OPTIONAL MATCH (alias)-[r:uses_material]->(out)
    FOREACH (x IN CASE WHEN r IS NOT NULL THEN [1] ELSE [] END |
        MERGE (canonical)-[r2:uses_material]->(out)
        SET r2 = r
        DELETE r
    )
    WITH alias, canonical
    OPTIONAL MATCH (in)-[r:uses_material]->(alias)
    FOREACH (x IN CASE WHEN r IS NOT NULL THEN [1] ELSE [] END |
        MERGE (in)-[r2:uses_material]->(canonical)
        SET r2 = r
        DELETE r
    )
    WITH alias, canonical
    OPTIONAL MATCH (alias)-[r:operates_at_condition]->(out)
    FOREACH (x IN CASE WHEN r IS NOT NULL THEN [1] ELSE [] END |
        MERGE (canonical)-[r2:operates_at_condition]->(out)
        SET r2 = r
        DELETE r
    )
    WITH alias
    DETACH DELETE alias
    """

    async def run_tx(tx, query, alias, canonical):
        await tx.run(query, alias=alias, canonical=canonical, workspace=workspace)

    async with driver.session(database=database) as session:
        for alias, canonical in synonym_dict.items():
            await session.execute_write(run_tx, fallback_query, alias, canonical)
            logger.info(f"Neo4j: Merged '{alias}' -> '{canonical}'")

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

async def main():
    load_dotenv()
    rag = get_rag_instance()
    await rag.initialize_storages()

    graph_storage = rag.chunk_entity_relation_graph
    
    # 1. Load all nodes
    nodes = await extract_all_nodes(graph_storage)
    if not nodes:
        logger.info("Graph is empty. No entities to merge.")
        await rag.finalize_storages()
        return

    # 2. Block/Group similar nodes semantically using embeddings
    candidate_groups = await run_semantic_blocking(rag, nodes)
    
    # 3. Verify each candidate group with the LLM
    synonym_map = {}
    for group in candidate_groups:
        mappings = await verify_synonym_group_via_llm(rag, group)
        synonym_map.update(mappings)

    # 4. Merge nodes in active storage backend
    if synonym_map:
        logger.info(f"Resolved synonym map to merge: {synonym_map}")
        if hasattr(graph_storage, "_graph"):
            await merge_nodes_networkx(graph_storage, synonym_map)
        elif hasattr(graph_storage, "client"):
            await merge_nodes_neo4j(graph_storage, synonym_map)
        else:
            logger.warning(f"Unsupported graph storage class for merging: {type(graph_storage)}")
    else:
        logger.info("No synonyms detected by LLM. Nothing to merge.")

    await rag.finalize_storages()

if __name__ == "__main__":
    asyncio.run(main())
