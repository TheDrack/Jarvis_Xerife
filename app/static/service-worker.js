"use strict";

// The Global HUD is online-first. Never persist authenticated API responses.
self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") return;
  event.respondWith(fetch(event.request));
});
