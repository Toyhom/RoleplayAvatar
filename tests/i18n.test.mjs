import test from 'node:test';
import assert from 'node:assert/strict';
import {catalogs, translate, normalizeLocale} from '../web/i18n.js';

test('every language covers the same messages and positional arguments', () => {
  const keys = Object.keys(catalogs.en).sort();
  for (const [language, catalog] of Object.entries(catalogs)) {
    assert.deepEqual(Object.keys(catalog).sort(), keys, language);
    for (const key of keys) {
      assert.ok(catalog[key].trim(), `${language}: ${key}`);
      assert.deepEqual([...catalog[key].matchAll(/\{\d+\}/g)].map(x=>x[0]).sort(),
        [...key.matchAll(/\{\d+\}/g)].map(x=>x[0]).sort(), `${language}: ${key}`);
    }
  }
});

test('language resolution and interpolation preserve user text', () => {
  assert.equal(normalizeLocale('en-GB'), 'en');
  assert.equal(normalizeLocale('zh-Hans'), 'zh-CN');
  assert.equal(normalizeLocale('ja-JP'), 'ja');
  assert.equal(normalizeLocale('fr'), 'en');
  assert.equal(translate('en','声线 {0}',3),'Voice 3');
  assert.equal(translate('ja','声线 {0}',3),'声 3');
  assert.equal(translate('en','无法启动声音：{0}','<b>user</b>'),'Could not start audio: <b>user</b>');
  assert.equal(translate('ja','Original character dialogue'),'Original character dialogue');
});
