import requests
from bs4 import BeautifulSoup
from openai import OpenAI
import json

# Configure OpenRouter client
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key="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",  # replace with your key
)

def get_links_from_openrouter(course, difficulty):
    """
    Ask OpenRouter model to return relevant links for the given course and difficulty.
    Returns a Python list of URLs.
    """
    try:
        prompt = f"""
        Provide a JSON list of 3-5 reliable links for learning about the topic:
        Course: {course}
        Difficulty: {difficulty}
        The links should be:
        - Helpful for scraping (easy to extract text content)
        - Covering both easy and hard level concepts
        - Contain good, reliable educational material

        Format ONLY as JSON with this structure:
        {{
            "links": [
                "https://example1.com",
                "https://example2.com"
            ]
        }}
        """

        response = client.chat.completions.create(
            model="openai/gpt-oss-20b:free",  # you can use grok-4-fast:free or another model "openai/gpt-oss-20b:free" or "deepseek/deepseek-chat-v3.1:free"
            messages=[{"role": "user", "content": prompt}],
        )

        raw_text = response.choices[0].message.content.strip()

        # --- CLEAN THE RAW TEXT ---
        if raw_text.startswith("```"):
            raw_text = raw_text.strip("`")
            lines = raw_text.splitlines()
            if lines and lines[0].strip().lower() == "json":
                raw_text = "\n".join(lines[1:])

        print("Cleaned OpenRouter response:", raw_text)

        # --- SAFE JSON PARSE ---
        try:
            data = json.loads(raw_text)
            return data.get("links", [])
        except json.JSONDecodeError as je:
            print("Failed to parse JSON. Raw text:", raw_text)
            print("JSON Error:", je)
            return []

    except Exception as e:
        print("Error fetching links from OpenRouter:", e)
        return []


def scrape_content_from_url(url):
    """Scrape text content from a single URL."""
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/91.0.4472.124 Safari/537.36"
            )
        }
        response = requests.get(url, headers=headers, timeout=10)

        if response.status_code != 200:
            print(f"Failed to fetch {url} (Status code: {response.status_code})")
            return None

        soup = BeautifulSoup(response.text, "html.parser")

        paragraphs = soup.find_all("p")
        text_content = "\n".join(p.get_text().strip() for p in paragraphs if p.get_text().strip())

        return text_content if text_content else None

    except Exception as e:
        print(f"Error scraping {url}: {e}")
        return None


def fetch_online_course_data(course, difficulty):
    """
    1. Fetch relevant links from OpenRouter
    2. Scrape each link
    3. Return combined documents and metadata
    """
    documents = []
    metadatas = []

    # Step 1: Get links
    links = get_links_from_openrouter(course, difficulty)
    print("Links received from OpenRouter:", links)

    if not links:
        print("No links found. Exiting.")
        return documents, metadatas

    # Step 2: Scrape each link
    for url in links:
        print(f"Scraping: {url}")
        content = scrape_content_from_url(url)

        if content:
            documents.append(content)
            metadatas.append({
                "course": course,
                "difficulty": difficulty,
                "source": url
            })
        else:
            print(f"No content scraped from: {url}")

    return documents, metadatas
