const api = globalThis.browser || globalThis.chrome;

export async function waitForDownload(id) {
  await new Promise((resolve, reject) => {
    const onChange = change => {
      if (change.id !== id || !change.state) return;
      if (change.state.current === 'complete') { api.downloads.onChanged.removeListener(onChange); resolve(); }
      if (change.state.current === 'interrupted') { api.downloads.onChanged.removeListener(onChange); reject(new Error('Download interrupted. You can retry saving.')); }
    };
    api.downloads.onChanged.addListener(onChange);
    api.downloads.search({ id }).then(items => {
      if (items[0]?.state) onChange({ id, state: { current: items[0].state } });
    }).catch(error => { api.downloads.onChanged.removeListener(onChange); reject(error); });
  });
}
