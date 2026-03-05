# -*- coding: utf-8 -*-
import requests
import logging
import time

logger = logging.getLogger("HttpClient")

class HttpClient:
    def __init__(self, base_url: str = ""):
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()

    def request(self, method: str, endpoint: str, **kwargs):
        url = f"{self.base_url}{endpoint}" if endpoint.startswith('/') else f"{self.base_url}/{endpoint}"
        
        try:
            response = self.session.request(method, url, **kwargs)
            # Se for 409, não levantamos exceção aqui, deixamos o Adapter tratar
            if response.status_code != 409:
                response.raise_for_status()
            return response
        except requests.exceptions.RequestException as e:
            if not (hasattr(e.response, 'status_code') and e.response.status_code == 409):
                logger.error(f"❌ Erro na requisição {method} {url}: {e}")
            raise e
