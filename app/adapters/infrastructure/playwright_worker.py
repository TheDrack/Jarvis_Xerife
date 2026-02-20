
import os
import sys
import time
from playwright.sync_api import sync_playwright
from app.adapters.infrastructure.base_worker import BaseWorker

class PlaywrightWorker(BaseWorker):
    def __init__(self):
        super().__init__()
        self.playwright = None

    def start(self):
        self.playwright = sync_playwright().start()

    def stop(self):
        if self.playwright:
            self.playwright.stop()

    def execute(self, url):
        browser = self.playwright.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        page.goto(url)
        time.sleep(5)  # aguarde 5 segundos
        browser.close()

    def run(self, url):
        try:
            self.start()
            self.execute(url)
            self.stop()
        except Exception as e:
            print(f'Erro: {e}')

if __name__ == '__main__':
    worker = PlaywrightWorker()
    worker.run('https://www.example.com')
