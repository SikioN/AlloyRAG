import os
import sys
import asyncio
from dotenv import load_dotenv

# Ensure local package path is correctly configured
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from alloyrag.rag_system import get_rag_instance
from alloyrag.utils import logger
from alloyrag.ingest_manager import ascan_and_ingest_inputs
from scripts.prepare_inputs import process_directory
from scripts.merge_synonyms import run_merging_pipeline
from pathlib import Path

async def populate_database():
    print("\n" + "="*60)
    print("      ALLOYRAG DATABASE POPULATION PIPELINE STARTED")
    print("="*60 + "\n")

    input_dir = os.getenv("INPUT_DIR", "./inputs")
    
    # Step 1: Prepare and clean inputs (extract ZIPs/RARs, flatten folders)
    logger.info(f"Step 1: Preparing inputs in '{input_dir}'...")
    try:
        process_directory(Path(input_dir))
        logger.info("Input preparation completed successfully.")
    except Exception as e:
        logger.error(f"Error during input preparation: {e}")
        # Continue anyway as we might still have some valid files
        
    # Step 2: Initialize RAG storages
    logger.info("Step 2: Connecting to storage backends (PostgreSQL & Neo4j)...")
    rag = get_rag_instance()
    await rag.initialize_storages()
    
    # Step 3: Scan and Ingest Documents
    logger.info("Step 3: Indexing and extracting entities/relations from documents...")
    try:
        # Calls the core ingestion manager which routes files to parsers and extracts KG
        await ascan_and_ingest_inputs()
        logger.info("Document ingestion and entity extraction completed successfully.")
    except Exception as e:
        logger.error(f"Error during document ingestion: {e}")
        print("\n❌ Ingestion failed. Database is partially populated.")
        await rag.finalize_storages()
        return

    # Step 4: Run automated synonym resolution
    logger.info("Step 4: Running semantic synonym merging and deduplication...")
    try:
        await run_merging_pipeline()
        logger.info("Synonym merging completed successfully.")
    except Exception as e:
        logger.error(f"Error during synonym merging: {e}")
        
    # Finalize connections
    await rag.finalize_storages()
    
    print("\n" + "="*60)
    print("      DATABASE POPULATION COMPLETED SUCCESSFULLY!")
    print("="*60 + "\n")

if __name__ == "__main__":
    load_dotenv()
    asyncio.run(populate_database())
