/*!
 * PromptGate · core/models
 * 模型价格表。价格为「每 100 万 token 的美元标价」，快照日期写在 PRICE_SNAPSHOT。
 * 官方随时调价 —— 因此 UI 允许逐项编辑，报告里也会带上「价格快照日期」。
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else {
    root.PG = root.PG || {};
    root.PG.models = factory();
  }
}(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  var PRICE_SNAPSHOT = '2026-11-01';

  var DEFAULT_MODELS = [
    { id: 'gpt-4o', label: 'GPT-4o', vendor: 'OpenAI', inPrice: 2.5, outPrice: 10, ctx: 128000, note: '通用主力' },
    { id: 'gpt-4o-mini', label: 'GPT-4o mini', vendor: 'OpenAI', inPrice: 0.15, outPrice: 0.6, ctx: 128000, note: '低成本批量' },
    { id: 'gpt-4.1', label: 'GPT-4.1', vendor: 'OpenAI', inPrice: 2.0, outPrice: 8.0, ctx: 1000000, note: '长上下文' },
    { id: 'claude-sonnet-4.5', label: 'Claude Sonnet 4.5', vendor: 'Anthropic', inPrice: 3.0, outPrice: 15.0, ctx: 200000, note: '写作/代码' },
    { id: 'claude-haiku-4.5', label: 'Claude Haiku 4.5', vendor: 'Anthropic', inPrice: 1.0, outPrice: 5.0, ctx: 200000, note: '低延迟' },
    { id: 'deepseek-chat', label: 'DeepSeek V3', vendor: 'DeepSeek', inPrice: 0.27, outPrice: 1.1, ctx: 128000, note: '性价比' },
    { id: 'qwen-plus', label: '通义千问 Plus', vendor: 'Alibaba', inPrice: 0.4, outPrice: 1.2, ctx: 131072, note: '中文场景' },
    { id: 'glm-4-plus', label: 'GLM-4-Plus', vendor: 'Zhipu', inPrice: 0.7, outPrice: 0.7, ctx: 128000, note: '国内可直连' }
  ];

  var ASSUMPTIONS = {
    outputTokens: 800,
    callsPerDay: 200,
    days: 30
  };

  function byId(models, id) {
    for (var i = 0; i < models.length; i++) {
      if (models[i].id === id) return models[i];
    }
    return models[0] || null;
  }

  function clone(list) {
    return (list || []).map(function (m) {
      return {
        id: m.id,
        label: m.label,
        vendor: m.vendor,
        inPrice: Number(m.inPrice) || 0,
        outPrice: Number(m.outPrice) || 0,
        ctx: Number(m.ctx) || 0,
        note: m.note || ''
      };
    });
  }

  /** 校验用户编辑过的价格表，返回 {ok, errors, models} */
  function validate(list) {
    var errors = [];
    if (!Array.isArray(list) || list.length === 0) {
      return { ok: false, errors: ['价格表为空'], models: clone(DEFAULT_MODELS) };
    }
    var seen = Object.create(null);
    var clean = [];
    list.forEach(function (m, i) {
      var label = (m && (m.label || m.id)) || ('第 ' + (i + 1) + ' 项');
      if (!m || !m.id) { errors.push(label + '：缺少 id'); return; }
      if (seen[m.id]) { errors.push(label + '：id 重复（' + m.id + '）'); return; }
      seen[m.id] = true;
      var inp = Number(m.inPrice);
      var outp = Number(m.outPrice);
      if (!isFinite(inp) || inp < 0) errors.push(label + '：输入价必须是非负数字');
      if (!isFinite(outp) || outp < 0) errors.push(label + '：输出价必须是非负数字');
      clean.push({
        id: String(m.id),
        label: String(m.label || m.id),
        vendor: String(m.vendor || ''),
        inPrice: isFinite(inp) ? inp : 0,
        outPrice: isFinite(outp) ? outp : 0,
        ctx: Number(m.ctx) || 0,
        note: String(m.note || '')
      });
    });
    return { ok: errors.length === 0, errors: errors, models: clean.length ? clean : clone(DEFAULT_MODELS) };
  }

  return {
    PRICE_SNAPSHOT: PRICE_SNAPSHOT,
    DEFAULT_MODELS: clone(DEFAULT_MODELS),
    ASSUMPTIONS: ASSUMPTIONS,
    byId: byId,
    clone: clone,
    validate: validate
  };
}));
