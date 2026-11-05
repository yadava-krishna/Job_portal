// Connection state for the service worker, kept in the extension's own IndexedDB.
//
// Why not chrome.storage.local: content scripts can read chrome.storage, and content scripts run inside employer
// pages' renderer processes. IndexedDB here belongs to the chrome-extension:// origin, which content scripts
// (running with the page's origin) cannot open. Only the service worker uses this module.

const DB = "jobpilot";
const STORE = "vault";

function open() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB, 1);
    req.onupgradeneeded = () => req.result.createObjectStore(STORE);
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function tx(mode, fn) {
  const db = await open();
  try {
    return await new Promise((resolve, reject) => {
      const t = db.transaction(STORE, mode);
      const req = fn(t.objectStore(STORE));
      t.oncomplete = () => resolve(req?.result);
      t.onerror = () => reject(t.error);
      t.onabort = () => reject(t.error);
    });
  } finally {
    db.close();
  }
}

export const vault = {
  get: (key) => tx("readonly", (s) => s.get(key)),
  set: (key, value) => tx("readwrite", (s) => s.put(value, key)),
  remove: (key) => tx("readwrite", (s) => s.delete(key)),
  clear: () => tx("readwrite", (s) => s.clear()),
};
