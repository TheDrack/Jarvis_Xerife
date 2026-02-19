
   import { chromium } from 'playwright';
   import { Worker } from 'worker_threads';

   class WorkerPlaywright {
       private browser: any;

       constructor() {
           this.init();
       }

       async init() {
           this.browser = await chromium.launch({
               headless: true,
               args: ['--no-sandbox', '--disable-setuid-sandbox']
           });
       }

       async execute(script: string) {
           const context = await this.browser.newContext();
           const page = await context.newPage();
           try {
               await page.evaluate(script);
           } catch (error) {
               console.error(error);
           } finally {
               await page.close();
               await context.close();
           }
       }

       async close() {
           if (this.browser) {
               await this.browser.close();
           }
       }
   }

   const worker = new Worker(__filename);

   worker.on('message', async (message) => {
       if (message.type === 'execute') {
           const workerPlaywright = new WorkerPlaywright();
           await workerPlaywright.execute(message.script);
           workerPlaywright.close();
       }
   });

   worker.on('error', (error) => {
       console.error(error);
   });

   worker.on('exit', () => {
       console.log('Worker exited');
   });
   