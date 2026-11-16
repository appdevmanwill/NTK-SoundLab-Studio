(() => {
  document.documentElement.dataset.ntkGrabberExt = '1.0.0';

  let appReady = Boolean(window.__ntkSoundLabBridgeReady);
  const queuedMessages = [];

  function base64ToUint8Array(b64) {
    const bin = atob(b64);
    const arr = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) {
      arr[i] = bin.charCodeAt(i);
    }
    return arr;
  }

  function deliverToApp(payload) {
    if (!appReady) {
      queuedMessages.push(payload);
      window.postMessage({ source: 'ntk-soundlab-grabber-ext', type: 'NTK_SOUNDLAB_BRIDGE_PING' }, window.location.origin);
      return;
    }
    const buf = payload.bytes instanceof Uint8Array ? payload.bytes : new Uint8Array(payload.bytes);
    window.postMessage(
      {
        source: 'ntk-soundlab-grabber-ext',
        type: 'NTK_SOUNDLAB_EXT_IMPORT',
        payload: {
          ...payload.meta,
          bytes: buf.buffer
        }
      },
      window.location.origin,
      [buf.buffer]
    );
  }

  window.addEventListener('message', (event) => {
    if (event.source !== window || event.origin !== window.location.origin) return;
    if (event.data?.source === 'ntk-soundlab-app' && (event.data?.type === 'NTK_SOUNDLAB_BRIDGE_PONG' || event.data?.type === 'NTK_SOUNDLAB_APP_READY')) {
      appReady = true;
      while (queuedMessages.length > 0) {
        deliverToApp(queuedMessages.shift());
      }
    }
  });

  function startTransfer(transferId) {
    if (!transferId) return;
    const port = chrome.runtime.connect({ name: 'ntk-soundlab-bridge' });
    let chunks = [];
    let meta = null;

    port.onMessage.addListener((msg) => {
      if (msg.type === 'TRANSFER_START') {
        meta = msg.meta;
        chunks = new Array(msg.totalChunks);
      } else if (msg.type === 'TRANSFER_CHUNK') {
        chunks[msg.index] = base64ToUint8Array(msg.dataB64);
      } else if (msg.type === 'TRANSFER_DONE') {
        const total = chunks.reduce((sum, c) => sum + (c ? c.length : 0), 0);
        const merged = new Uint8Array(total);
        let offset = 0;
        for (const c of chunks) {
          if (c) {
            merged.set(c, offset);
            offset += c.length;
          }
        }
        deliverToApp({ meta, bytes: merged });
        port.disconnect();
      } else if (msg.type === 'TRANSFER_ERROR') {
        port.disconnect();
      }
    });

    port.postMessage({ type: 'REQUEST_TRANSFER', transferId });
  }

  chrome.runtime.onMessage.addListener((msg) => {
    if (msg?.type === 'TRANSFER_AVAILABLE' && msg.transferId) {
      startTransfer(msg.transferId);
    }
  });

  if (window.location.hash && window.location.hash.includes('ext-transfer=')) {
    const params = new URLSearchParams(window.location.hash.replace(/^#/, ''));
    const tid = params.get('ext-transfer');
    if (tid) {
      try {
        history.replaceState(null, document.title, window.location.pathname + window.location.search);
      } catch {}
      startTransfer(tid);
    }
  }

  window.postMessage({ source: 'ntk-soundlab-grabber-ext', type: 'NTK_SOUNDLAB_BRIDGE_PING' }, window.location.origin);
})();
