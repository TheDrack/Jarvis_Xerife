
   const { Worker } = require('worker_threads');
   const playwright = require('playwright');

   class WorkerPlaywright {
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
       return await this.page.evaluate(script);
     }

     async close() {
       if (this.page) await this.page.close();
       if (this.context) await this.context.close();
       if (this.browser) await this.browser.close();
     }
   }

   const worker = new Worker(__filename);

   let workerPlaywright;

   worker.on('message', async (message) => {
     if (message.type === 'init') {
       workerPlaywright = new WorkerPlaywright();
       await workerPlaywright.init();
       worker.postMessage({ type: 'initialized' });
     } else if (message.type === 'execute') {
       if (!workerPlaywright) {
         workerPlaywright = new WorkerPlaywright();
         await workerPlaywright.init();
       }
       const result = await workerPlaywright.execute(message.script);
       worker.postMessage({ type: 'result', result });
     } else if (message.type === 'close') {
       if (workerPlaywright) {
         await workerPlaywright.close();
         workerPlaywright = null;
       }
       worker.postMessage({ type: 'closed' });
     }
   });

   worker.on('error', (error) => {
     console.error(error);
   });

   worker.on('exit', () => {
     console.log('Worker exited');
   });
   