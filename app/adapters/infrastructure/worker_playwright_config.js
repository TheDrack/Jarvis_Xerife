
   // app/adapters/infrastructure/worker_playwright_config.js
   const { Worker } = require('worker_threads');
   const playwright = require('playwright');

   class WorkerPlaywrightConfig {
     constructor() {
       this.browser = null;
       this.context = null;
       this.page = null;
     }

     async init() {
       this.browser = await playwright.chromium.launch({
         headless: true,
         args: ['--no-sandbox', '--disable-setuid-sandbox']
       });
       this.context = await this.browser.newContext();
       this.page = await this.context.newPage();
     }

     async close() {
       if (this.page) {
         await this.page.close();
       }
       if (this.context) {
         await this.context.close();
       }
       if (this.browser) {
         await this.browser.close();
       }
     }
   }

   module.exports = WorkerPlaywrightConfig;
   