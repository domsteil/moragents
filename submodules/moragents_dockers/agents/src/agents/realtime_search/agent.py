import logging
import requests

from bs4 import BeautifulSoup
from src.models.messages import ChatRequest

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"


class RealtimeSearchAgent:
    def __init__(self, config, llm, embeddings):
        self.config = config
        self.llm = llm
        self.embeddings = embeddings
        self.last_search_term = None

    def perform_search(self, search_term=None):
        if search_term is not None:
            self.last_search_term = search_term
        elif self.last_search_term is None:
            logger.warning("No search term available for web search")
            return "Web search failed. Please provide a search term."
        else:
            search_term = self.last_search_term

        logger.info(f"Performing web search for: {search_term}")

        try:
            url = f"https://www.google.com/search?q={search_term}"
            headers = {"User-Agent": USER_AGENT}
            response = requests.get(url, headers=headers)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "html.parser")

            search_results = soup.find_all("div", class_="g")

            formatted_results = []
            for result in search_results[:5]:
                result_text = result.get_text(strip=True)
                formatted_results.append(f"Result:\n{result_text}")

            return "\n\n".join(formatted_results)

        except requests.RequestException as e:
            logger.error(f"Error performing web search: {str(e)}")
            return f"Error performing web search: {str(e)}"

    def synthesize_answer(self, search_term, search_results):
        logger.info("Synthesizing answer from search results")
        messages = [
            {
                "role": "system",
                "content": "You are a helpful assistant that synthesizes information from web search results to answer user queries.",
            },
            {
                "role": "user",
                "content": f"Based on the following search results for the query '{search_term}', provide a concise and informative answer:\n\n{search_results}",
            },
        ]

        try:
            result = self.llm.invoke(messages)
            logger.info(f"Received response from LLM: {result}")
            return result.content.strip()
        except Exception as e:
            logger.error(f"Error synthesizing answer: {str(e)}")
            raise

    def chat(self, request: ChatRequest):
        try:
            data = request.dict()
            logger.info(f"Received chat request: {data}")
            if "prompt" in data:
                prompt = data["prompt"]
                search_term = prompt["content"]
                logger.info(f"Performing web search for prompt: {search_term}")

                search_results = self.perform_search(search_term)
                logger.info(f"Search results obtained")

                synthesized_answer = self.synthesize_answer(search_term, search_results)
                logger.info(f"Synthesized answer: {synthesized_answer}")

                return {"role": "assistant", "content": synthesized_answer}
            else:
                logger.error("Missing 'prompt' in chat request data")
                return {"error": "Missing parameters"}, 400
        except Exception as e:
            logger.exception(f"Unexpected error in chat method: {str(e)}")
            return {"Error": str(e)}, 500
