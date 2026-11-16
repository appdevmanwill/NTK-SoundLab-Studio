/**
 * NTK SoundLab Studio - Universal Media Grabber Bookmarklet & Userscript Generator
 * 2026 Studio Edition - Suno In-Browser Decryption + HTML5/Network Stream Capture HUD
 */

export class BookmarkletEngine {
  /**
   * Builds the self-contained JavaScript bookmarklet URL
   * @returns {string}
   */
  static getBookmarkletUrl() {
    const studioBase =
      typeof window !== 'undefined' &&
      window.location &&
      window.location.href.startsWith('http')
        ? window.location.origin + window.location.pathname
        : 'https://studio-5090403114-fc98b.web.app/';

    const rawCode = `(function(){
      (async function(){
        try {
          var studioUrl = ${JSON.stringify(studioBase)};
          var host = (location.hostname || '').toLowerCase();
          var isSunoHost = host === 'suno.com' || host.endsWith('.suno.com') || host === 'suno.ai' || host.endsWith('.suno.ai');
          var m = isSunoHost ? location.pathname.match(/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/i) : null;
          var u = m ? m[1].toLowerCase() : '';

          var old = document.getElementById('suno-studio-hud');
          if (old) old.remove();

          var h = document.createElement('div');
          h.id = 'suno-studio-hud';
          h.style.cssText = 'position:fixed;bottom:24px;right:24px;z-index:2147483647;background:#0a0e17;color:#f8fafc;border:2px solid #06b6d4;border-radius:20px;padding:18px;width:390px;max-width:92vw;font-family:system-ui,-apple-system,sans-serif;box-shadow:0 24px 60px rgba(0,0,0,0.85);line-height:1.45;';

          if (!u) {
            var metaContent = function(sel){
              var el = document.querySelector(sel);
              return el ? (el.getAttribute('content') || '') : '';
            };
            var rawTitle = metaContent('meta[property="og:title"]') || document.title || 'Captured Media';
            var cleanTitle = rawTitle.replace(/\\s*[|-]\\s*(Audiomack|SoundCloud|Suno|YouTube|Vimeo|ACE Music).*$/i, '').trim() || 'Captured Media';
            var artist = metaContent('meta[name="author"]') || metaContent('meta[property="music:musician"]') || host;
            var cover = metaContent('meta[property="og:image"]') || metaContent('meta[name="twitter:image"]') || '';

            var found = [];
            var seen = {};
            var addUrl = function(url, kind){
              if (!url || !/^https?:\\/\\//i.test(url) || seen[url]) return;
              if (/\\.(js|mjs|css|png|jpe?g|webp|gif|svg|woff2?)(\\?|$)/i.test(url)) return;
              seen[url] = true;
              found.push({ url: url, kind: kind || 'Stream' });
            };

            document.querySelectorAll('audio, video').forEach(function(el){
              addUrl(el.currentSrc || el.src, el.tagName === 'VIDEO' ? 'Video' : 'Audio');
              el.querySelectorAll('source').forEach(function(s){
                addUrl(s.src, el.tagName === 'VIDEO' ? 'Video' : 'Audio');
              });
            });
            addUrl(metaContent('meta[property="og:audio"]'), 'OG Audio');
            addUrl(metaContent('meta[property="og:video"]'), 'OG Video');

            try {
              performance.getEntriesByType('resource').forEach(function(r){
                if (/\\.(mp3|m4a|aac|wav|flac|ogg|opus|webm|mp4|mov|m3u8|mpd)(?:$|[?#])/i.test(r.name)) {
                  addUrl(r.name, /\\.(mp4|webm|mov)/i.test(r.name) ? 'Video Network' : 'Audio Network');
                }
              });
            } catch (ex) {}

            var listHtml = '';
            if (found.length === 0) {
              listHtml = '<div style="font-size:12px;color:#cbd5e1;padding:10px;background:rgba(255,255,255,0.05);border-radius:10px;margin-bottom:10px;">' +
                'No exposed &lt;audio&gt;/&lt;video&gt; URL in the page DOM yet.<br><br>' +
                '1. Make sure you clicked <strong>Play</strong> on the track.<br>' +
                '2. Players like <strong>Audiomack</strong> use detached JS network streams &mdash; use the <strong>NTK SoundLab Browser Grabber Chrome/Edge Extension</strong> to capture them directly from Chrome!' +
                '</div>';
            } else {
              found.slice(0, 5).forEach(function(item, idx){
                listHtml += '<div style="padding:8px 10px;background:rgba(255,255,255,0.06);border-radius:10px;margin-bottom:8px;">' +
                  '<div style="font-size:11px;font-weight:700;color:#67e8f9;margin-bottom:4px;">' + item.kind + '</div>' +
                  '<div style="font-size:10px;color:#94a3b8;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-bottom:6px;">' + item.url + '</div>' +
                  '<div style="display:flex;gap:6px;flex-wrap:wrap;">' +
                  '<button data-ntk-send="' + idx + '" style="padding:6px 10px;border-radius:8px;border:none;background:linear-gradient(90deg,#06b6d4,#8b5cf6);color:#fff;font-weight:700;font-size:11px;cursor:pointer;">⚡ Send to Studio</button>' +
                  '<button data-ntk-copy="' + idx + '" style="padding:6px 10px;border-radius:8px;border:1px solid rgba(255,255,255,0.2);background:rgba(255,255,255,0.08);color:#fff;font-weight:600;font-size:11px;cursor:pointer;">📋 Copy</button>' +
                  '<a href="' + item.url + '" download target="_blank" rel="noopener" style="padding:6px 10px;border-radius:8px;border:1px solid rgba(16,185,129,0.4);background:rgba(16,185,129,0.16);color:#6ee7b7;font-weight:700;font-size:11px;text-decoration:none;">⬇ Save</a>' +
                  '</div></div>';
              });
            }

            h.innerHTML = '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">' +
              '<span style="font-weight:800;font-size:14px;color:#67e8f9;">🧲 NTK SoundLab Stream Grabber</span>' +
              '<button id="sm-close" style="background:none;border:none;color:#94a3b8;font-size:18px;cursor:pointer;">✕</button>' +
              '</div>' +
              '<div style="font-size:12px;font-weight:700;margin-bottom:10px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">' + cleanTitle + '</div>' +
              listHtml +
              '<button id="sm-open-studio" style="width:100%;padding:8px;border-radius:10px;border:1px solid rgba(6,182,212,0.4);background:rgba(6,182,212,0.12);color:#67e8f9;font-weight:700;font-size:11px;cursor:pointer;">Open NTK SoundLab Studio</button>';

            document.body.appendChild(h);
            document.getElementById('sm-close').onclick = function(){ h.remove(); };
            document.getElementById('sm-open-studio').onclick = function(){ window.open(studioUrl, '_blank'); };

            h.querySelectorAll('[data-ntk-copy]').forEach(function(btn){
              btn.onclick = function(){
                var target = found[parseInt(btn.getAttribute('data-ntk-copy'), 10)];
                if (target && navigator.clipboard) {
                  navigator.clipboard.writeText(target.url);
                  btn.innerText = '✅ Copied';
                }
              };
            });
            h.querySelectorAll('[data-ntk-send]').forEach(function(btn){
              btn.onclick = function(){
                var target = found[parseInt(btn.getAttribute('data-ntk-send'), 10)];
                if (!target) return;
                var payload = { url: target.url, title: cleanTitle, artist: artist, cover: cover, pageUrl: location.href };
                var b64 = btoa(unescape(encodeURIComponent(JSON.stringify(payload))));
                window.open(studioUrl + '#grab=' + encodeURIComponent(b64), '_blank');
              };
            });
            return;
          }

          h.style.borderColor = '#f59e0b';
          h.style.background = '#10131d';

          var t = (document.querySelector('h1') && document.querySelector('h1').innerText) || document.title.replace(/\\s*[|-]\\s*Suno.*$/i, '').trim() || 'Suno_Song';
          t = t.replace(/[<>:"/\\\\|?*]/g, '').trim().slice(0, 60) || 'Suno_Song';

          h.innerHTML = '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">' +
            '<span style="font-weight:800;font-size:15px;color:#fbbf24;display:flex;align-items:center;gap:6px;"><span>🪄</span><span>NTK Hub • Suno Studio</span></span>' +
            '<button id="sm-close" style="background:none;border:none;color:#94a3b8;font-size:18px;cursor:pointer;padding:2px 6px;">✕</button>' +
            '</div>' +
            '<div style="font-size:13px;font-weight:700;color:#f8fafc;margin-bottom:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">🎵 ' + t + '</div>' +
            '<div id="sm-status" style="font-size:12px;color:#cbd5e1;margin-bottom:14px;padding:9px 12px;background:rgba(255,255,255,0.06);border-radius:12px;">⏳ Requesting decryption rights...</div>' +
            '<div id="sm-actions" style="display:none;flex-direction:column;gap:8px;"></div>';

          document.body.appendChild(h);
          document.getElementById('sm-close').onclick = function(){ h.remove(); };

          var st = document.getElementById('sm-status');
          var act = document.getElementById('sm-actions');

          var r = await fetch('https://studio-api.prod.suno.com/api/mango/rights', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ content_params: { content_id: u, content_type: 'clip' } })
          });
          if (!r.ok) throw new Error('Rights request failed with status: ' + r.status);
          var data = await r.json();

          st.innerText = '🔓 Deriving cryptographic keys...';
          var gDigest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(data.glt));
          var mKey = await crypto.subtle.importKey('raw', gDigest, { name: 'AES-GCM' }, false, ['decrypt']);

          var unwrap = async function(b64) {
            var raw = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
            return new Uint8Array(await crypto.subtle.decrypt(
              { name: 'AES-GCM', iv: raw.slice(0, 12), additionalData: new TextEncoder().encode(u) },
              mKey,
              raw.slice(12)
            ));
          };

          var cKey = await crypto.subtle.importKey('raw', await unwrap(data.key), { name: 'AES-CTR' }, false, ['decrypt']);
          var iv = await unwrap(data.iv);

          st.innerText = '⚡ Downloading master stream...';
          var encResp = await fetch('https://d2lwuy8qc234o3.cloudfront.net/1/clip/' + u + '.m4a');
          if (!encResp.ok) throw new Error('CloudFront returned HTTP ' + encResp.status);
          var encBuf = await encResp.arrayBuffer();

          st.innerText = '✨ Decrypting audio in browser...';
          var decBuf = await crypto.subtle.decrypt({ name: 'AES-CTR', counter: iv, length: 128 }, cKey, encBuf);

          st.innerHTML = '✅ <strong>Decrypted!</strong> ' + (decBuf.byteLength / 1024 / 1024).toFixed(2) + ' MB ready.';
          act.style.display = 'flex';

          var blobM4a = new Blob([decBuf], { type: 'audio/mp4' });
          var dl = function(b, name) {
            var a = document.createElement('a');
            a.href = URL.createObjectURL(b);
            a.download = name;
            document.body.appendChild(a);
            a.click();
            a.remove();
          };

          act.innerHTML =
            '<button id="sm-dl-m4a" style="padding:10px;border-radius:12px;border:none;background:linear-gradient(90deg,#fbbf24,#f43f5e);color:#0f172a;font-weight:800;font-size:12px;cursor:pointer;">⬇ Download Original Master (.m4a)</button>' +
            '<button id="sm-dl-wav" style="padding:10px;border-radius:12px;border:1px solid rgba(16,185,129,0.5);background:rgba(16,185,129,0.2);color:#6ee7b7;font-weight:800;font-size:12px;cursor:pointer;">⬇ Download Studio WAV (Lossless)</button>' +
            '<button id="sm-dl-stems" style="padding:10px;border-radius:12px;border:1px solid rgba(6,182,212,0.5);background:rgba(6,182,212,0.2);color:#67e8f9;font-weight:800;font-size:12px;cursor:pointer;">🎛️ Open in NTK Hub 4-Stem AI Studio</button>' +
            '<button id="sm-dl-karaoke" style="padding:10px;border-radius:12px;border:1px solid rgba(245,158,11,0.5);background:rgba(245,158,11,0.18);color:#fde68a;font-weight:800;font-size:12px;cursor:pointer;">🎬 Open in 1080p Karaoke Video Studio</button>' +
            '<button id="sm-dl-video" style="padding:8px;border-radius:10px;border:1px solid rgba(139,92,246,0.5);background:rgba(139,92,246,0.2);color:#c4b5fd;font-weight:700;font-size:11px;cursor:pointer;">📹 Download Raw Suno Clip (.mp4)</button>' +
            '<button id="sm-dl-img" style="padding:7px;border-radius:10px;border:1px solid rgba(255,255,255,0.15);background:rgba(255,255,255,0.06);color:#cbd5e1;font-weight:600;font-size:11px;cursor:pointer;">🖼 Download Cover Art (.jpeg)</button>';

          dl(blobM4a, t + '.m4a');

          document.getElementById('sm-dl-m4a').onclick = function(){ dl(blobM4a, t + '.m4a'); };
          document.getElementById('sm-dl-img').onclick = function(){ window.open('https://cdn2.suno.ai/image_large_' + u + '.jpeg', '_blank'); };

          document.getElementById('sm-dl-wav').onclick = async function() {
            this.innerText = '⏳ Encoding Studio WAV...';
            try {
              var ctx = new (window.AudioContext || window.webkitAudioContext)();
              var aBuf = await ctx.decodeAudioData(decBuf.slice(0));
              if (ctx.close) await ctx.close();

              var nCh = aBuf.numberOfChannels, sr = aBuf.sampleRate, len = aBuf.length, ds = len * nCh * 2;
              var b = new ArrayBuffer(44 + ds), v = new DataView(b);
              var w = function(o, s){ for (var i=0; i<s.length; i++) v.setUint8(o+i, s.charCodeAt(i)); };
              w(0, 'RIFF'); v.setUint32(4, 36 + ds, true); w(8, 'WAVE'); w(12, 'fmt ');
              v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, nCh, true);
              v.setUint32(24, sr, true); v.setUint32(28, sr * nCh * 2, true);
              v.setUint16(32, nCh * 2, true); v.setUint16(34, 16, true);
              w(36, 'data'); v.setUint32(40, ds, true);

              var chs = [];
              for (var c=0; c<nCh; c++) chs.push(aBuf.getChannelData(c));
              var off = 44;
              for (var i=0; i<len; i++) {
                for (var c=0; c<nCh; c++) {
                  var smp = Math.max(-1, Math.min(1, chs[c][i]));
                  v.setInt16(off, smp < 0 ? smp * 0x8000 : smp * 0x7FFF, true);
                  off += 2;
                }
              }
              dl(new Blob([b], { type: 'audio/wav' }), t + '.wav');
              this.innerText = '✅ WAV Downloaded!';
            } catch (err) {
              alert('WAV conversion failed: ' + err.message);
              this.innerText = '⬇ Download Studio WAV';
            }
          };

          var launchStudio = function(mode) {
            var p = '';
            try {
              var html = document.documentElement.innerHTML || '';
              var pm = html.match(/"prompt"\\s*:\\s*"\\$([0-9a-fA-F]+)"/);
              if (pm) {
                var idx = html.indexOf(pm[1] + ':T');
                if (idx !== -1) {
                  var sub = html.slice(idx);
                  var cm = sub.match(/^[0-9a-fA-F]+:T([0-9a-fA-F]+),([\\s\\S]*)/);
                  if (cm) {
                    p = cm[2].slice(0, parseInt(cm[1], 16)).replace(/\\\\n/g, '\\n').replace(/\\\\"/g, '"').trim();
                  }
                }
              }
            } catch (ex) {}
            var payload = { title: t, prompt: p, rights: { glt: data.glt, key: data.key, iv: data.iv } };
            var b64 = btoa(unescape(encodeURIComponent(JSON.stringify(payload))));
            var sep = studioUrl.indexOf('?') !== -1 ? '&' : '?';
            window.open(studioUrl + sep + 'song=' + u + '&open=' + mode + '#bridge=' + encodeURIComponent(b64), '_blank');
          };

          document.getElementById('sm-dl-stems').onclick = function() { launchStudio('stems'); };
          document.getElementById('sm-dl-karaoke').onclick = function() { launchStudio('video'); };

          document.getElementById('sm-dl-video').onclick = function() {
            window.open('https://cdn1.suno.ai/' + u + '.mp4', '_blank');
          };

        } catch (e) {
          var st = document.getElementById('sm-status');
          if (st) {
            st.innerHTML = '❌ <strong>Error:</strong> ' + e.message;
          } else {
            alert('NTK SoundLab Grabber: ' + e.message);
          }
        }
      })();
    })();`;

    return 'javascript:' + encodeURIComponent(rawCode.replace(/\s+/g, ' ').trim());
  }

  /**
   * Generates Tampermonkey / Violentmonkey userscript
   * @returns {string}
   */
  static getUserscriptCode() {
    const bookmarkletUrl = BookmarkletEngine.getBookmarkletUrl();
    return `// ==UserScript==
// @name         NTK Hub • Suno Studio Edition
// @namespace    ntk-hub-suno-studio
// @version      4.2.0
// @description  1-Click direct audio & video downloader with Mango DRM decryption and HTDemucs v4 4-Stem AI Studio launcher
// @match        https://suno.com/*
// @grant        none
// @run-at       document-idle
// ==/UserScript==

(function() {
  'use strict';

  const injectDownloadButton = () => {
    if (document.getElementById('suno-pro-hud-trigger')) return;

    const match = location.pathname.match(/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/i);
    if (!match) return;

    const btn = document.createElement('button');
    btn.id = 'suno-pro-hud-trigger';
    btn.innerHTML = '⚡ Download Song & Launch Studio';
    btn.style.cssText = 'position:fixed;top:16px;right:180px;z-index:999999;background:linear-gradient(90deg,#fbbf24,#f43f5e);color:#0f172a;font-weight:800;font-size:12px;padding:8px 16px;border-radius:20px;border:none;box-shadow:0 10px 25px rgba(0,0,0,0.5);cursor:pointer;transition:transform 0.2s;';
    btn.onmouseover = () => { btn.style.transform = 'scale(1.05)'; };
    btn.onmouseout = () => { btn.style.transform = 'scale(1)'; };
    btn.onclick = () => {
      location.href = "${bookmarkletUrl}";
    };
    document.body.appendChild(btn);
  };

  setInterval(injectDownloadButton, 1500);
})();`;
  }
}
