import test from 'node:test';
import assert from 'node:assert/strict';
import { safeFilename, mediaUrl, streamKey, sourceSize } from '../media-utils.mjs';

test('different qualities on the same endpoint remain selectable', () => {
  assert.notEqual(streamKey('https://media.example/play?id=1&quality=1080'), streamKey('https://media.example/play?id=1&quality=360'));
});

test('export filenames use the requested format even when titles contain dots', () => {
  assert.equal(safeFilename('Artist feat. Singer.mp4', 'wav'), 'Artist feat. Singer.wav');
  assert.equal(safeFilename('CON', 'mp3'), '_CON.mp3');
  assert.equal(safeFilename('../track?', 'mp4'), '.. track.mp4');
});

test('partial responses report the complete media size', () => {
  assert.equal(sourceSize(new Headers({'content-length':'1024','content-range':'bytes 0-1023/9000000'})), 9000000);
});

test('captured downloads reject active content and embedded credentials', () => {
  for (const url of ['javascript:alert(1)', 'file:///test', 'https://user:secret@example.com/audio']) {
    assert.throws(() => mediaUrl(url));
  }
});
