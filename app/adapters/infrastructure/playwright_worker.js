
   const { Worker } = require('worker_threads');
   const playwright = require('playwright');

   class PlaywrightWorker {
       constructor(browserType) {
           this.browserType = browserType;
           this.worker = new Worker(__filename, { workerData: { browserType } });
           this.browser = null;
       }

       async launchBrowser() {
           return new Promise((resolve, reject) => {
               this.worker.on('message', (message) => {
                   if (message.type === 'browserLaunched') {
                       this.browser = message.browser;
                       resolve(message.browser);
                   }
               });
               this.worker.on('error', (error) => {
                   reject(error);
               });
               this.worker.postMessage({ type: 'launchBrowser' });
           });
       }

       async closeBrowser() {
           return new Promise((resolve, reject) => {
               this.worker.on('message', (message) => {
                   if (message.type === 'browserClosed') {
                       resolve();
                   }
               });
               this.worker.on('error', (error) => {
                   reject(error);
               });
               this.worker.postMessage({ type: 'closeBrowser' });
           });
       }
   }

   if (require.main === module) {
       const browserType = process.argv[2];
       const worker = new PlaywrightWorker(browserType);

       worker.worker.on('message', (message) => {
           if (message.type === 'launchBrowser') {
               (async () => {
                   const browser = await playwright[browserType].launch();
                   worker.worker.postMessage({ type: 'browserLaunched', browser });
               })();
           } else if (message.type === 'closeBrowser') {
               (async () => {
                   const browser = worker.browser;
                   if (browser) {
                       await browser.close();
                       worker.worker.postMessage({ type: 'browserClosed' });
                   }
               })();
           }
       });
   }

   module.exports = PlaywrightWorker;
   