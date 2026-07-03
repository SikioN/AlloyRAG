import os
import shutil
import asyncio

from fastapi import FastAPI, UploadFile, File, BackgroundTasks, HTTPException, Depends
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from typing import Literal, List

from alloyrag.rag_system import get_rag_instance
from alloyrag.url_crawler import acrawl_and_index_url
from alloyrag.ingest_manager import (
    ascan_and_ingest_inputs,
    get_ingested_states,
)
from alloyrag.utils import logger
from alloyrag.api.routers.document_routes import create_document_routes, DocumentManager
from alloyrag.api.routers.query_routes import create_query_routes
from alloyrag.api.routers.graph_routes import create_graph_routes
from fastapi.security import OAuth2PasswordRequestForm
from alloyrag.api.auth import auth_handler

load_dotenv()

app = FastAPI(
    title="🔬 Научный клубок RAG-система",
    description="Графовая поисково-аналитическая RAG-система по материаловедению",
    version="1.0.0",
)

# Enable CORS for easy local access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mounting templates and static files will be handled after creating them
os.makedirs("templates", exist_ok=True)
os.makedirs("inputs", exist_ok=True)


class QueryRequest(BaseModel):
    query: str
    mode: Literal["local", "global", "hybrid", "mix"] = "hybrid"


class CrawlRequest(BaseModel):
    url: str


# Track background indexing tasks
is_indexing_busy = False


async def run_indexing_pipeline():
    global is_indexing_busy
    if is_indexing_busy:
        logger.info("Indexing pipeline is already running. Skipping trigger.")
        return
    try:
        is_indexing_busy = True
        logger.info("Background indexing pipeline started...")
        # Call the async version directly on the main event loop
        await ascan_and_ingest_inputs()
        logger.info("Background indexing pipeline completed successfully.")
    except Exception as e:
        logger.error(f"Error in background indexing pipeline: {e}")
    finally:
        is_indexing_busy = False


@app.on_event("startup")
async def startup_event():
    # Warm up RAG instance on startup
    logger.info("Initializing RAG system on startup...")
    rag = get_rag_instance()
    await rag.initialize_storages()
    # Trigger initial scan in case files were placed in inputs/ before launch
    asyncio.create_task(run_indexing_pipeline())


@app.post("/api/query")
async def query_rag(request: QueryRequest):
    """Query the RAG system using specified search mode."""
    try:
        rag = get_rag_instance()
        logger.info(f"Querying RAG in '{request.mode}' mode: {request.query}")

        from alloyrag import QueryParam

        answer = await rag.aquery(
            request.query,
            param=QueryParam(
                mode=request.mode,
                enable_rerank=False,  # Disable rerank (no rerank model configured)
            ),
        )

        # Handle case where LLM returns None (e.g. timeout, context overflow)
        if answer is None:
            logger.error(
                "RAG query returned None - possible LLM timeout or context overflow"
            )
            # Retry with simpler naive mode as fallback
            logger.info("Retrying with naive mode as fallback...")
            answer = await rag.aquery(
                request.query, param=QueryParam(mode="naive", enable_rerank=False)
            )
            if answer is None:
                raise HTTPException(
                    status_code=503,
                    detail="LLM did not respond. Possibly overloaded or context too long. Try a simpler query.",
                )

        return {"answer": answer, "mode": request.mode}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error executing query: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/crawl")
async def crawl_url(request: CrawlRequest, background_tasks: BackgroundTasks):
    """Crawl a webpage, extract content + VLM descriptions, and insert into RAG."""
    try:
        # Trigger crawl asynchronously on the main event loop
        success = await acrawl_and_index_url(request.url)

        if success:
            return {
                "status": "success",
                "message": f"URL {request.url} crawled and indexed successfully.",
            }
        else:
            raise HTTPException(
                status_code=400, detail="Failed to crawl URL. Check logs for details."
            )
    except Exception as e:
        logger.error(f"Error crawling URL: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/upload")
async def upload_files(
    background_tasks: BackgroundTasks, files: List[UploadFile] = File(...)
):
    """Upload documents and trigger background ingestion pipeline."""
    saved_files = []
    for file in files:
        if not file.filename:
            continue
        filepath = os.path.join("./inputs", file.filename)
        logger.info(f"Uploading file: {file.filename} -> {filepath}")

        try:
            with open(filepath, "wb") as f:
                shutil.copyfileobj(file.file, f)
            saved_files.append(file.filename)
        except Exception as e:
            logger.error(f"Failed to save uploaded file {file.filename}: {e}")
            raise HTTPException(
                status_code=500, detail=f"Failed to save {file.filename}"
            )

    # Trigger background indexing
    background_tasks.add_task(run_indexing_pipeline)

    return {
        "status": "success",
        "message": f"Successfully uploaded {len(saved_files)} file(s). Ingestion started in background.",
        "files": saved_files,
    }


@app.get("/api/status")
async def get_system_status():
    """Retrieve indexing status of all documents in inputs directory."""
    input_dir = "./inputs"
    files = []

    states = get_ingested_states()

    if os.path.exists(input_dir):
        for name in os.listdir(input_dir):
            if name.startswith("."):
                continue
            path = os.path.join(input_dir, name)
            if os.path.isfile(path):
                state = states.get(path, {})
                files.append(
                    {
                        "name": name,
                        "size": os.path.getsize(path),
                        "status": state.get("status", "pending"),
                        "processed_at": state.get("processed_at", None),
                    }
                )

    return {"is_indexing_busy": is_indexing_busy, "files": files}


@app.get("/api/graph")
async def get_graph():
    """Extract Knowledge Graph structures for vis.js visualization."""
    try:
        rag = get_rag_instance()
        graph_storage = rag.chunk_entity_relation_graph

        # Load the graph
        nx_graph = await graph_storage._get_graph()

        nodes = []
        edges = []

        # Prepare color palettes for UI aesthetics
        type_colors = {
            "Alloy": "#E87A5D",  # Vibrant Coral / Orange
            "Mode": "#4FA3D1",  # Deep Sky Blue
            "Property": "#47C299",  # Emerald Green
            "Equipment": "#DDA0DD",  # Plum / Purple
            "ResearchTeam": "#FFD700",  # Gold
            "Outcome": "#FF69B4",  # Hot Pink
            "Concept": "#9370DB",  # Medium Purple
            "UNKNOWN": "#A9A9A9",  # Grey
            "Other": "#888888",
        }

        for node_id in nx_graph.nodes:
            attrs = nx_graph.nodes[node_id]
            entity_type = attrs.get("entity_type", "UNKNOWN")
            desc = attrs.get("description", "")

            nodes.append(
                {
                    "id": node_id,
                    "label": node_id,
                    "title": f"<b>Type:</b> {entity_type}<br/><b>Description:</b> {desc}",
                    "group": entity_type,
                    "color": type_colors.get(entity_type, "#888888"),
                    "value": nx_graph.degree(
                        node_id
                    ),  # Node size based on degree (importance)
                }
            )

        for u, v in nx_graph.edges:
            attrs = nx_graph.edges[u, v]
            weight = attrs.get("weight", 1.0)
            desc = attrs.get("description", "")
            keywords = attrs.get("keywords", "")

            edges.append(
                {
                    "from": u,
                    "to": v,
                    "title": f"<b>Relation:</b> {keywords}<br/>{desc}",
                    "label": keywords.split(",")[0] if keywords else "",
                    "value": weight,
                }
            )

        return {
            "nodes": nodes,
            "edges": edges,
            "summary": {"node_count": len(nodes), "edge_count": len(edges)},
        }
    except Exception as e:
        logger.error(f"Failed to generate graph structure: {e}")
        return {"nodes": [], "edges": [], "error": str(e)}


# Custom endpoints for WebUI compatibility
@app.post("/documents/upload")
async def upload_document_custom(
    background_tasks: BackgroundTasks, file: UploadFile = File(...)
):
    # Sanitize filename to prevent directory traversal
    safe_filename = os.path.basename(file.filename)
    filepath = os.path.join("./inputs", safe_filename)
    logger.info(f"Custom WebUI upload: {safe_filename} -> {filepath}")

    try:
        with open(filepath, "wb") as f:
            shutil.copyfileobj(file.file, f)
    except Exception as e:
        logger.error(f"Failed to save uploaded file: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to save file: {e}")

    # Trigger background indexing
    background_tasks.add_task(run_indexing_pipeline)

    return {
        "status": "success",
        "message": f"Successfully uploaded {safe_filename}. Ingestion started in background.",
        "track_id": safe_filename,
    }


@app.post("/documents/scan")
async def scan_documents_custom(background_tasks: BackgroundTasks):
    logger.info("Custom WebUI scan triggered.")
    background_tasks.add_task(run_indexing_pipeline)
    return {
        "status": "scanning_started",
        "message": "Scanning process has been initiated in the background",
        "track_id": "scan_trigger",
    }


@app.post("/documents/reprocess_failed")
async def reprocess_failed_documents_custom(background_tasks: BackgroundTasks):
    logger.info("Custom WebUI reprocess failed triggered.")
    states = get_ingested_states()
    changed = False
    for path, state in list(states.items()):
        if state.get("status") == "failed":
            del states[path]
            changed = True
    if changed:
        from ingest_manager import save_ingested_states

        save_ingested_states(states)

    background_tasks.add_task(run_indexing_pipeline)
    return {
        "status": "success",
        "message": "Failed documents queued for reprocessing",
        "track_id": "reprocess_trigger",
    }


@app.get("/documents/scan-progress")
async def get_scan_progress():
    return {
        "scanning": is_indexing_busy,
        "scanning_exclusive": False,
        "total_files": 0,
        "processed_files": 0,
        "failed_files": 0,
    }


@app.get("/documents/pipeline_status")
async def get_pipeline_status_custom():
    return {"busy": is_indexing_busy, "active": is_indexing_busy, "pending_enqueues": 0}


@app.get("/auth-status")
async def get_auth_status():
    if not auth_handler.accounts:
        guest_token = auth_handler.create_token(
            username="guest", role="guest", metadata={"auth_mode": "disabled"}
        )
        return {
            "auth_configured": False,
            "access_token": guest_token,
            "token_type": "bearer",
            "auth_mode": "disabled",
            "message": "Authentication is disabled. Using guest access.",
            "core_version": "1.5.5",
            "api_version": "1.5.5",
            "webui_title": "AlloyRAG",
            "webui_description": "Научный клубок RAG-система",
        }
    return {
        "auth_configured": True,
        "auth_mode": "enabled",
        "core_version": "1.5.5",
        "api_version": "1.5.5",
        "webui_title": "AlloyRAG",
        "webui_description": "Научный клубок RAG-система",
    }


@app.post("/login")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    if not auth_handler.accounts:
        guest_token = auth_handler.create_token(
            username="guest", role="guest", metadata={"auth_mode": "disabled"}
        )
        return {
            "access_token": guest_token,
            "token_type": "bearer",
            "auth_mode": "disabled",
            "message": "Authentication is disabled. Using guest access.",
            "core_version": "1.5.5",
            "api_version": "1.5.5",
            "webui_title": "AlloyRAG",
            "webui_description": "Научный клубок RAG-система",
        }
    username = form_data.username
    if not auth_handler.verify_password(username, form_data.password):
        raise HTTPException(status_code=401, detail="Incorrect credentials")

    user_token = auth_handler.create_token(
        username=username, role="user", metadata={"auth_mode": "enabled"}
    )
    return {
        "access_token": user_token,
        "token_type": "bearer",
        "auth_mode": "enabled",
        "core_version": "1.5.5",
        "api_version": "1.5.5",
        "webui_title": "AlloyRAG",
        "webui_description": "Научный клубок RAG-система",
    }


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "working_directory": os.path.abspath("./rag_storage"),
        "input_directory": os.path.abspath("./inputs"),
        "configuration": {
            "llm_binding": os.getenv("LLM_BINDING", "ollama"),
            "llm_model": os.getenv("LLM_MODEL", "llama3.2:latest"),
            "embedding_binding": os.getenv("EMBEDDING_BINDING", "local_huggingface"),
            "embedding_model": os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2"),
            "kv_storage": "JsonKVStorage",
            "doc_status_storage": "JsonDocStatusStorage",
            "graph_storage": "NetworkXStorage",
            "vector_storage": "NanoVectorDBStorage",
            "summary_language": "Russian",
        },
        "auth_mode": "disabled",
        "pipeline_busy": is_indexing_busy,
        "pipeline_active": is_indexing_busy,
        "webui_available": True,
    }


# Register standard routers from alloyrag
rag_instance = get_rag_instance()
doc_manager_instance = DocumentManager("./inputs")
api_key_val = os.getenv("ALLOYRAG_API_KEY")

logger.info(f"DEBUG: ALLOYRAG_API_KEY value is: {repr(api_key_val)}")

app.include_router(
    create_document_routes(rag_instance, doc_manager_instance, api_key_val)
)
app.include_router(create_query_routes(rag_instance, api_key_val, top_k=60))
app.include_router(create_graph_routes(rag_instance, api_key_val))


# Serve the built React WebUI at root
@app.get("/")
@app.get("/index.html")
async def serve_webui_index():
    index_path = os.path.join(
        os.path.dirname(__file__), "alloyrag", "api", "webui", "index.html"
    )
    if not os.path.exists(index_path):
        return HTMLResponse(
            "<h1>WebUI has not been built yet.</h1>"
            "<p>Please build the React WebUI first by running: <code>cd alloyrag_webui && bun install && bun run build</code></p>"
        )

    with open(index_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Inject runtime config
    import json

    _runtime_config_payload = json.dumps({"apiPrefix": "", "webuiPrefix": "/"}).replace(
        "</", "<\\/"
    )
    runtime_config_script = (
        f"<script>window.__ALLOYRAG_CONFIG__ = {_runtime_config_payload};</script>"
    )

    content = content.replace(
        "<!-- __ALLOYRAG_RUNTIME_CONFIG__ -->", runtime_config_script
    )
    return HTMLResponse(content=content)


# Mount WebUI assets
webui_assets_dir = os.path.join(os.path.dirname(__file__), "alloyrag", "api", "webui")
if os.path.exists(webui_assets_dir):
    app.mount("/", StaticFiles(directory=webui_assets_dir), name="webui")

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
