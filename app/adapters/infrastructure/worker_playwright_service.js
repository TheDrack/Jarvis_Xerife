
   const { Worker } = require('worker_threads');
   const playwright = require('playwright');

   class WorkerPlaywrightService {
     constructor() {
       this.browser = null;
       this.context = null;
       this.page = null;
     }

     async init() {
       this.browser = await playwright.chromium.launch();
       this.context = await this.browser.newContext();
       this.page = await this.context.newPage();
     }

     async execute(script) {
       return new Promise((resolve, reject) => {
         const worker = new Worker(`
           const { parentPort } = require('worker_threads');
           const playwright = require('playwright');

           (async () => {
             const browser = await playwright.chromium.launch();
             const context = await browser.newContext();
             const page = await context.newPage();

             try {
               const result = await eval(`${script}`);
               parentPort.postMessage(result);
             } catch (error) {
               parentPort.postMessage(error);
             } finally {
               await browser.close();
             }
           })();
         `, { eval: true, workerData: script });

         worker.on('message', resolve);
         worker.on('error', reject);
         worker.on('exit', (code) => {
           if (code !== 0) {
             reject(new Error(`Worker stopped with exit code ${code}`));
           }
         });
       });
     }

     async close() {
       if (this.browser) {
         await this.browser.close();
       }
     }
   }

   module.exports = WorkerPlaywrightService;
   