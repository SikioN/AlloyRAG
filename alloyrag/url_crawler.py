import os
import httpx
import base64
from urllib.parse import urljoin
from bs4 import BeautifulSoup

try:
    import trafilatura
except ImportError:
    trafilatura = None
from dotenv import load_dotenv
from alloyrag.rag_system import get_rag_instance
from alloyrag.utils import logger

load_dotenv()


def get_image_base64(image_url: str) -> str | None:
    """Download image and convert to base64."""
    try:
        response = httpx.get(image_url, timeout=10, follow_redirects=True)
        if response.status_code == 200:
            content_type = response.headers.get("content-type", "image/jpeg")
            encoded = base64.b64encode(response.content).decode("utf-8")
            return f"data:{content_type};base64,{encoded}"
    except Exception as e:
        logger.warning(f"Failed to download image {image_url}: {e}")
    return None


def analyze_image_with_vlm(image_base64: str) -> str:
    """Send base64 image to local Ollama VLM (qwen2-vl:7b)."""
    vlm_enable = os.getenv("VLM_PROCESS_ENABLE", "false").lower() == "true"
    if not vlm_enable:
        return ""

    vlm_model = os.getenv("VLM_LLM_MODEL", "qwen2-vl:7b")
    vlm_host = os.getenv("VLM_LLM_BINDING_HOST", "http://localhost:11434")

    try:
        import ollama

        client = ollama.Client(host=vlm_host)

        # Remove data:image/...;base64, prefix if present
        pure_b64 = image_base64
        if "," in image_base64:
            pure_b64 = image_base64.split(",")[1]

        logger.info(f"Analyzing image using local VLM ({vlm_model})...")
        response = client.chat(
            model=vlm_model,
            messages=[
                {
                    "role": "user",
                    "content": "Опиши подробно, что изображено на этом графике/схеме/картинке, перечисли все ключевые данные и подписи:",
                    "images": [pure_b64],
                }
            ],
        )
        description = response["message"]["content"]
        logger.info("VLM successfully generated image description.")
        return description
    except Exception as e:
        logger.warning(f"VLM analysis failed: {e}. Falling back to text extraction.")
        return ""


async def acrawl_and_index_url(url: str):
    """Crawl a webpage, extract text + image descriptions, and insert into AlloyRAG asynchronously."""
    logger.info(f"Starting crawl for URL: {url}")

    # 1. Download webpage content
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        import asyncio

        loop = asyncio.get_running_loop()

        def fetch_html():
            response = httpx.get(
                url, headers=headers, timeout=15, follow_redirects=True
            )
            return response.status_code, response.text

        status_code, html_content = await loop.run_in_executor(None, fetch_html)
        if status_code != 200:
            logger.error(f"Failed to fetch {url}. Status code: {status_code}")
            return False
    except Exception as e:
        logger.error(f"Failed to crawl {url}: {e}")
        return False

    # 2. Extract clean text using trafilatura in executor
    def parse_html():
        main_text = trafilatura.extract(html_content) if trafilatura else None
        if not main_text:
            soup = BeautifulSoup(html_content, "html.parser")
            for script in soup(["script", "style"]):
                script.decompose()
            main_text = soup.get_text(separator="\n")

        lines = (line.strip() for line in main_text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        cleaned_text = "\n".join(chunk for chunk in chunks if chunk)

        soup = BeautifulSoup(html_content, "html.parser")
        images = soup.find_all("img")
        return cleaned_text, images

    cleaned_text, images = await loop.run_in_executor(None, parse_html)

    image_descriptions = []
    logger.info(f"Found {len(images)} images on the page.")

    for idx, img in enumerate(images):
        src = img.get("src")
        alt = img.get("alt", "").strip()
        title = img.get("title", "").strip()

        if not src:
            continue

        absolute_img_url = urljoin(url, src)
        placeholder = f"Изображение {idx + 1}: "
        if alt:
            placeholder += f"Alt: {alt}. "
        if title:
            placeholder += f"Title: {title}."
        if not alt and not title:
            placeholder += f"Source: {src}."

        logger.info(f"Processing image {idx + 1}/{len(images)}: {absolute_img_url}")

        vlm_desc = ""
        vlm_enable = os.getenv("VLM_PROCESS_ENABLE", "false").lower() == "true"
        if vlm_enable:

            def process_image():
                img_b64 = get_image_base64(absolute_img_url)
                if img_b64:
                    return analyze_image_with_vlm(img_b64)
                return ""

            vlm_desc = await loop.run_in_executor(None, process_image)

        if vlm_desc:
            image_descriptions.append(
                f"\n--- [Описание изображения {idx + 1}] ---\n{vlm_desc}\n"
            )
        else:
            image_descriptions.append(
                f"\n--- [Описание изображения {idx + 1}] ---\n{placeholder}\n"
            )

    # 4. Combine text and image descriptions
    full_document_content = f"URL: {url}\n\n=== ТЕКСТ СТРАНИЦЫ ===\n{cleaned_text}\n"
    if image_descriptions:
        full_document_content += (
            "\n=== ОПИСАНИЕ ИЗОБРАЖЕНИЙ НА СТРАНИЦЕ ===\n"
            + "\n".join(image_descriptions)
        )

    # 5. Insert into AlloyRAG asynchronously
    rag = get_rag_instance()
    await rag.initialize_storages()
    logger.info(f"Inserting crawled document from {url} into AlloyRAG database...")
    await rag.ainsert(full_document_content)
    logger.info(f"Successfully indexed URL: {url}")
    return True


def crawl_and_index_url(url: str) -> bool:
    """Crawl a webpage and insert into AlloyRAG (synchronous wrapper)."""
    import asyncio

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(lambda: asyncio.run(acrawl_and_index_url(url))).result()
    else:
        return asyncio.run(acrawl_and_index_url(url))


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        target_url = sys.argv[1]
        crawl_and_index_url(target_url)
    else:
        print("Usage: python url_crawler.py <URL>")
