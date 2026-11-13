/*!
 * PromptGate · core/storage
 * localStorage 的安全封装：隐私模式 / file:// / 配额满 都不能让应用崩。
 * 存储不可用时退化为内存 Map，功能仍可用（只是关掉页面就没了），并在 UI 里提示。
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else {
    root.PG = root.PG || {};
    root.PG.storage = factory();
  }
}(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  var PREFIX = 'promptgate.v1.';

  function createStorage(backend, opts) {
    var memory = Object.create(null);
    var backup = backend || null;
    var usable = false;

    if (backup) {
      try {
        var probe = PREFIX + '__probe__';
        backup.setItem(probe, '1');
        backup.removeItem(probe);
        usable = true;
      } catch (e) {
        usable = false;
      }
    }

    function readRaw(key) {
      if (usable) {
        try {
          var stored = backup.getItem(PREFIX + key);
          if (stored != null) return stored;
        } catch (e) { /* 退回内存 */ }
      }
      // 后端没有（或写入时配额已满只落在内存），用内存副本兜底
      return key in memory ? memory[key] : null;
    }

    function writeRaw(key, value) {
      memory[key] = value;
      if (usable) {
        try {
          backup.setItem(PREFIX + key, value);
          return true;
        } catch (e) {
          // 配额满：保留内存副本，返回 false 让调用方提示
          return false;
        }
      }
      return false;
    }

    return {
      isPersistent: function () { return usable; },
      get: function (key, fallback) {
        var raw = readRaw(key);
        if (raw == null) return fallback;
        try { return JSON.parse(raw); } catch (e) { return fallback; }
      },
      set: function (key, value) {
        var ok;
        try {
          ok = writeRaw(key, JSON.stringify(value));
        } catch (e) {
          return false;
        }
        return ok;
      },
      remove: function (key) {
        delete memory[key];
        if (usable) {
          try { backup.removeItem(PREFIX + key); } catch (e) { /* ignore */ }
        }
      },
      /** 列出本命名空间下的 key，用于调试与「清空数据」 */
      keys: function () {
        if (!usable) return Object.keys(memory);
        var out = [];
        try {
          for (var i = 0; i < backup.length; i++) {
            var k = backup.key(i);
            if (k && k.indexOf(PREFIX) === 0) out.push(k.slice(PREFIX.length));
          }
        } catch (e) { /* ignore */ }
        return out;
      },
      clearAll: function () {
        var self = this;
        self.keys().forEach(function (k) { self.remove(k); });
      },
      backendKind: usable ? ((opts && opts.kind) || 'localStorage') : 'memory'
    };
  }

  function getDefaultBackend() {
    try {
      if (typeof localStorage !== 'undefined' && localStorage) return localStorage;
    } catch (e) { /* 隐私模式下访问即抛 */ }
    return null;
  }

  var defaultStore = createStorage(getDefaultBackend(), { kind: 'localStorage' });

  return {
    createStorage: createStorage,
    store: defaultStore,
    PREFIX: PREFIX
  };
}));
