export class TranscriptConflictError extends Error {
  constructor() {
    super('This transcript changed in another tab. Save a copy or download your draft to keep your edits.');
    this.name = 'TranscriptConflictError';
  }
}

// Separate from media-cache purges: deleting cached songs must not erase transcripts.
export class TranscriptStore {
  static async db() {
    if (!this.connection) this.connection = new Promise((resolve, reject) => {
      const req = indexedDB.open('NTKTranscriptsDB', 1);
      req.onupgradeneeded = () => req.result.createObjectStore('transcripts', { keyPath: 'id' });
      req.onsuccess = () => {
        req.result.onversionchange = () => { req.result.close(); this.connection = null; };
        resolve(req.result);
      };
      req.onerror = () => { this.connection = null; reject(new Error('Local transcript storage is unavailable. Download a copy before closing.')); };
      req.onblocked = () => { this.connection = null; reject(new Error('Close other studio tabs to open transcript history.')); };
    });
    return this.connection;
  }
  static async action(mode, work) {
    const db = await this.db();
    return new Promise((resolve, reject) => {
      const tx = db.transaction('transcripts', mode);
      const request = work(tx.objectStore('transcripts'));
      tx.oncomplete = () => resolve(request.result);
      tx.onerror = tx.onabort = () => reject(new Error('Could not save locally. Storage may be full. Download your transcript now.'));
    });
  }
  static async change(id, expectedRevision, write) {
    const db = await this.db();
    return new Promise((resolve, reject) => {
      const tx = db.transaction('transcripts', 'readwrite');
      const store = tx.objectStore('transcripts');
      const request = store.get(id);
      let revision;
      let conflict = false;
      request.onsuccess = () => {
        const current = request.result;
        const storedRevision = current ? current.revision ?? 0 : null;
        if (storedRevision !== expectedRevision) {
          conflict = true;
          tx.abort();
          return;
        }
        revision = (storedRevision ?? 0) + 1;
        write(store, revision);
      };
      tx.oncomplete = () => resolve(revision);
      tx.onabort = () => reject(conflict ? new TranscriptConflictError() : new Error('Could not save locally. Download your transcript now.'));
    });
  }
  static save(record, expectedRevision = record.revision ?? null) {
    return this.change(record.id, expectedRevision, (store, revision) => store.put({ ...record, revision }));
  }
  static async get(id) {
    const record = await this.action('readonly', store => store.get(id));
    return record ? { ...record, revision: record.revision ?? 0 } : null;
  }
  static async list() {
    return (await this.action('readonly', store => store.getAll()))
      .map(record => ({ ...record, revision: record.revision ?? 0 }))
      .sort((a, b) => b.updatedAt - a.updatedAt);
  }
  static remove(id, revision) {
    return this.change(id, revision ?? null, store => store.delete(id));
  }
}
