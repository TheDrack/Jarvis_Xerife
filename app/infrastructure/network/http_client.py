import requests
import logging

class HttpClient:
    """Motor central de requisições do JARVIS."""
    def __init__(self, base_url: str = "", default_headers: dict = None):
        self.base_url = base_url
        self.headers = default_headers or {}
        self.logger = logging.getLogger("HttpClient")

    def request(self, method: str, endpoint: str, **kwargs):
        url = f"{self.base_url}{endpoint}" if not endpoint.startswith("http") else endpoint
        try:
            response = requests.request(method, url, headers=self.headers, timeout=30, **kwargs)
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as e:
            self.logger.error(f"❌ Erro na requisição {method} {url}: {e}")
            if hasattr(e, 'response') and e.response is not None:
                return e.response
            raise e
