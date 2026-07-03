import os
import sys
import asyncio
import json
from dotenv import load_dotenv

# Ensure local package path is correctly configured
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from alloyrag.rag_system import get_rag_instance
from alloyrag.utils import logger

# 1. Mappings of known synonyms (Base list from full_desc.md + domain terms)
SYNONYM_MAP = {
    # electrowinning / electrowinning -> электроэкстракция
    "electrowinning": "электроэкстракция",
    "electrowinning process": "электроэкстракция",
    "electrowinning cell": "ванна электроэкстракции",
    # ПВП / fluidized bed furnace -> печь взвешенной плавки
    "пвп": "печь взвешенной плавки",
    "fluidized bed furnace": "печь взвешенной плавки",
    "печи взвешенной плавки": "печь взвешенной плавки",
    # Other potential synonyms
    "электролиз никеля": "электроэкстракция никеля",
}

def normalize_name(name: str) -> str:
    """Normalize and look up synonym in mapping."""
    cleaned = name.strip()
    # Check lowercase match
    lower_name = cleaned.lower()
    if lower_name in SYNONYM_MAP:
        canonical = SYNONYM_MAP[lower_name]
        logger.info(f"Mapping synonym: '{cleaned}' -> '{canonical}'")
        return canonical
    return cleaned

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
                # In networkx.Graph (undirected), get edge data
                edge_data = nx_graph.get_edge_data(alias_node, neighbor)
                if not nx_graph.has_edge(canonical, neighbor):
                    nx_graph.add_edge(canonical, neighbor, **edge_data)
                
            # Remove the alias node
            nx_graph.remove_node(alias_node)
            modified = True

    if modified:
        logger.info("Saving updated NetworkX graph to disk...")
        # Write back to file
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
    
    # We will use Cypher to redirect relationships and delete duplicate nodes
    # Supports any custom relationship type dynamically
    merge_query = """
    MATCH (alias:Entity {name: $alias, workspace: $workspace})
    MATCH (canonical:Entity {name: $canonical, workspace: $workspace})
    SET canonical.description = 
        CASE 
            WHEN alias.description IS NOT NULL AND NOT canonical.description CONTAINS alias.description
            THEN canonical.description + "\\n[Синоним: " + $alias + "]: " + alias.description
            ELSE canonical.description
        END
    WITH alias, canonical
    // Reconnect outgoing relations
    MATCH (alias)-[r]->(out)
    WHERE out <> canonical
    CALL apoc.merge.relationship(canonical, type(r), properties(r), {}, out, {}) YIELD rel
    DELETE r
    WITH alias, canonical
    // Reconnect incoming relations
    MATCH (in)-[r]->(alias)
    WHERE in <> canonical
    CALL apoc.merge.relationship(in, type(r), properties(r), {}, canonical, {}) YIELD rel
    DELETE r
    WITH alias
    DELETE alias
    """

    # Non-APOC fallback query if APOC is not enabled
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
    // Redirection of a few standard relations
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
            try:
                # Try using APOC-based merge first
                await session.execute_write(run_tx, merge_query, alias, canonical)
                logger.info(f"Neo4j: Merged '{alias}' -> '{canonical}' (APOC)")
            except Exception:
                # Fallback to standard Cypher query
                await session.execute_write(run_tx, fallback_query, alias, canonical)
                logger.info(f"Neo4j: Merged '{alias}' -> '{canonical}' (Fallback Cypher)")

async def llm_resolve_synonyms(rag_instance):
    """Use the LLM to dynamically find and recommend synonym groups in the graph."""
    graph_storage = rag_instance.chunk_entity_relation_graph
    
    # Load all nodes
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
    else:
        # Neo4j or other
        # Return early or mock
        return {}

    if not nodes:
        logger.info("Graph is empty. Skipping LLM resolution.")
        return {}

    logger.info(f"Running LLM synonym resolution over {len(nodes)} entities...")
    
    # Format prompt for the LLM
    entities_list_str = json.dumps(nodes[:100], ensure_ascii=False, indent=2) # Cap at 100 to fit prompt window
    
    prompt = f"""Вы — эксперт-лингвист и специалист по графам знаний. Перед вами список сущностей из базы знаний R&D в области горной металлургии.
Каждая сущность представлена в формате JSON: {{"name": "...", "type": "...", "description": "..."}}.

Ваша задача — найти группы сущностей, которые являются синонимами, аббревиатурами или переводами друг друга (например, "ПВП" и "печь взвешенной плавки", "electrowinning" и "электроэкстракция").

Верните результат строго в формате JSON:
{{
  "synonyms": [
    {{"canonical": "печь взвешенной плавки", "aliases": ["ПВП", "fluidized bed furnace"]}},
    {{"canonical": "электроэкстракция", "aliases": ["electrowinning"]}}
  ]
}}

Список сущностей:
{entities_list_str}
"""

    llm_func = rag_instance.llm_model_func
    llm_name = rag_instance.llm_model_name
    llm_kwargs = rag_instance.llm_model_kwargs
    
    try:
        response_text = await llm_func(
            prompt,
            model=llm_name,
            response_format={"type": "json_object"},
            **llm_kwargs
        )
        
        # Parse the JSON response
        data = json.loads(response_text)
        synonyms = data.get("synonyms", [])
        
        resolved_map = {}
        for item in synonyms:
            canonical = item.get("canonical")
            aliases = item.get("aliases", [])
            for alias in aliases:
                resolved_map[alias] = canonical
                
        logger.info(f"LLM identified synonym mappings: {resolved_map}")
        return resolved_map
    except Exception as e:
        logger.error(f"Failed during LLM synonym resolution: {e}")
        return {}

async def main():
    load_dotenv()
    rag = get_rag_instance()
    await rag.initialize_storages()

    graph_storage = rag.chunk_entity_relation_graph
    
    # 1. Resolve synonyms using static mapping
    resolved_dict = SYNONYM_MAP.copy()
    
    # 2. Optionally resolve synonyms using LLM
    llm_resolved = await llm_resolve_synonyms(rag)
    resolved_dict.update(llm_resolved)

    # 3. Merge nodes in storage
    if hasattr(graph_storage, "_graph"):
        await merge_nodes_networkx(graph_storage, resolved_dict)
    elif hasattr(graph_storage, "client"): # Neo4j client exists
        await merge_nodes_neo4j(graph_storage, resolved_dict)
    else:
        logger.warning(f"Unsupported graph storage class for merging: {type(graph_storage)}")

    await rag.finalize_storages()

if __name__ == "__main__":
    asyncio.run(main())
