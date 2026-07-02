import os
import asyncio
from dotenv import load_dotenv
from alloyrag.rag_system import get_rag_instance
from alloyrag.ingest_excel import aingest_excel_file
from alloyrag.utils import logger

load_dotenv()


async def run_verification():
    logger.info("==============================================")
    logger.info("Starting Scientific Knot verification test...")
    logger.info("==============================================")

    # Target Excel path
    excel_path = "./inputs/experiments_template.xlsx"

    # 1. Run Excel Ingestion
    logger.info("Step 1: Running Excel ingestion...")
    rag = get_rag_instance()
    await rag.initialize_storages()
    success = await aingest_excel_file(excel_path)
    if not success:
        logger.error("Excel ingestion failed!")
        return

    logger.info("Excel ingestion completed successfully!")

    # 2. Verify graph database files
    logger.info("Step 2: Checking RAG storage status...")
    working_dir = os.getenv("WORKING_DIR", "./rag_storage")
    if os.path.exists(working_dir):
        files = os.listdir(working_dir)
        logger.info(f"Files created in storage: {files}")
    else:
        logger.error("RAG storage directory was not created!")
        return

    # 3. Query the RAG system to test retrieval
    logger.info("Step 3: Querying RAG system to verify retrieval...")
    rag = get_rag_instance()
    query = "Какие свойства имеет сплав Ni-Superalloy-718 и кто проводил эксперименты?"

    from alloyrag import QueryParam

    logger.info(f"Query: '{query}'")
    answer = await rag.aquery(query, param=QueryParam(mode="hybrid"))

    logger.info("==============================================")
    logger.info("RAG Response:")
    logger.info(answer)
    logger.info("==============================================")
    logger.info("Verification test successfully completed!")


if __name__ == "__main__":
    asyncio.run(run_verification())
