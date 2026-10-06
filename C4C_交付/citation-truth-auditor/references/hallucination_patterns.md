# Hallucination Patterns — AI 编造引用的指纹库

> 供`citation-truth-auditor` 使用，也在需要人工复核 `FABRICATED` 判定时作为依据。
> 严重度：`2` = 几乎确定有问题｜`1` = 可疑，需人工确认｜`0` = 仅信息性

---

## 1. 为什么需要指纹库？

权威数据库检索能回答"这篇论文存不存在"，但检索失败**不等于**论文不存在。
检索失败的原因可能是：网络不通、限流、论文确实没有 DOI、该领域不被收录。

指纹库解决的是相反方向的问题：**在无法联网、或检索结果模棱两可时，
仅凭引用本身的文本特征判断它是否像编造的**。它提供的是**先验概率**，
不是判决——所以指纹只提升可疑度，最终判定仍以检索结果为准。

---

## 2. 指纹目录

| # | 指纹 | 检测方法 | 严重度 | 误报风险 |
|---|---|---|---|---|
| F1 | 标题由高频泛义词堆砌 | 词表命中率 > 50% | 2 | 中（真实综述论文可能触发） |
| F2 | 模板化会议/期刊占位名 | 正则匹配 `In the Proceedings of the International…` | 2 | 低 |
| F3 | 年份不合理（未来 / < 1600） | 范围检查 | 2 | 极低 |
| F4 | DOI 格式损坏 | 不匹配 `10.\d{4,9}/\S+` | 2 | 低（预印本常见无 DOI，但那是缺失不是损坏） |
| F5 | 页码区间倒置 | `134--112` | 2 | 极低 |
| F6 | 缺少作者字段 | 字段为空 | 2 | 低（匿名研讨会论文偶见） |
| F7 | 作者含 `et al.` | 文本匹配 | 1 | **高**（BibTeX 中合法且常见） |

**F7 特别注意**：`author = {Smith, John and others}` 或直接写 `et al.`
在 BibTeX 里是合法写法。脚本只提示、不扣分，**不要**据此判定为编造。

---

## 3. 真实编造样例（取自本技能 demo）

以下是**真实运行** `citation_auditor.py` 检出的两条编造引用，
来自 `demo/sample_refs.bib`。它们是刻意构造的，形态与 LLM 实际产出高度一致。

### 样例 A：泛义词堆砌型

```bibtex
@article{smith2023deep,
  title   = {A Deep Intelligent Neural Network Learning Model Based on Data Driven
             Adaptive Optimization for Advanced Machine Learning Applications},
  author  = {Smith, John A. and Chen, Wei and Kumar, Rajesh and Patel, Suresh},
  journal = {Journal of Advanced Artificial Intelligence Research},
  volume  = {45}, number = {3}, pages = {112--134}, year = {2023},
  doi     = {10.1234/jair.2023.45112}
}
```

审计结论：
```
[FABRICATED] 最佳匹配仅 0.39 < 阈值 0.82
最接近的是《Neural Network-Based Discrete-Time Adaptive ILC》
⚠ 幻觉指纹[2]: 标题由高频泛义词堆砌，疑似占位/编造
```

**为什么是编造**——三个独立信号同时出现：
1. `deep / neural network / learning model / data driven / adaptive /
   optimization / machine learning / applications` —— 八个词全是高频泛义词，
   任何组合都"听起来合理"，但**没有任何一个具体的研究主张**。
2. 期刊名 `Journal of Advanced Artificial Intelligence Research` 过于通用，
   不存在。
3. 前缀 `10.1234` 是测试用保留前缀，Crossref 中真实 DOI 极少以此开头。

真实论文的标题通常包含**具体**的方法名、任务名或数据集名，
例如 `Delving Deep into Rectifiers: Surpassing Human-Level Performance on ImageNet Classification`。

### 样例 B：模板占位型

```bibtex
@inproceedings{doe2021innovative,
  title     = {An Innovative Deep Learning Framework for Scalable Intelligence},
  author    = {Doe, Jane and Roe, Richard},
  booktitle = {In the Proceedings of the International Conference on Advanced
               Computational Methods},
  pages     = {45--52}, year = {2031}
}
```

审计结论：
```
[FABRICATED] 最佳匹配仅 0.52 < 阈值 0.82
最接近的是《IOT-Enabled Deep Learning Framework for Scalable Crop Disease Detection》
⚠ 幻觉指纹[2]: 年份 2031 不合理（未来或过旧）
```

**为什么是编造**：
1. `In the Proceedings of the International Conference on…` 是 LLM 填充
   会议名时的**典型模板句式**，真实会议名几乎不会以 `In the Proceedings of
   the International` 开头（这通常是论文标题里的前缀，而非 booktitle）。
2. `Doe, Jane / Roe, Richard` —— `Doe` 是英语中的"某个无名氏"，
   `Roe` 高度疑似占位。
3. 年份 `2031` 超出当前年份，属未来年份。
4. `Innovative` 是营销词而非学术描述。

### 样例 C：张冠李戴型（最难识别）

```bibtex
@article{misattributed2015,
  title   = {Delving Deep into Rectifiers: Surpassing Human-Level Performance on
             ImageNet Classification},
  author  = {Smith, John A.},          % ← 真实作者应为 He, Kaiming 等
  journal = {ICLR}, year = {2015},
  eprint  = {1502.01852}
}
```

**标题、arXiv ID、年份全部真实**，只有作者是编造的。

这类最危险，因为：
- 它能通过"论文存不存在"的检查；
- 审计器会因作者重合度 < 0.5 标为 `PARTIAL`；
- 如果正文写作时引用它去支撑一个与 ResNet 无关的主张，
  实质上就是**错误归因**。

**处理原则**：作者不匹配时，务必人工确认——要么改正作者，要么确认你引用的是
另一篇真正符合该作者列表的论文。

---

## 4. 真实引用的正例（不应被误报）

```
[VERIFIED] vaswani2017attention   arXiv 命中，标题相似度 1.00，年份/作者一致
[VERIFIED] kingma2014adam         arXiv 命中，标题相似度 1.00，年份/作者一致
[VERIFIED] devlin2019bert         arXiv 命中，标题相似度 1.00，年份/作者一致
[VERIFIED] lecun2015deep          arXiv 命中，标题相似度 1.00，年份/作者一致
```

注意 `goodfellow2014generative` 被判为 `PARTIAL` 而非 `VERIFIED`——
因为 bib 中年份写作 2019，而真实年份是 2014。这是**真实的元数据错误**，
审计器正确地没有放过它。

---

## 5. 人工复核清单（收到 FABRICATED 判定时）

在删除一条引用前，按顺序确认：

1. **换个源再查一次** —— 把标题粘到 Google Scholar 或 Semantic Scholar。
   两个独立源都查不到，才基本确定不存在。
2. **搜索作者 + 关键词** —— 也许论文存在但标题记错了。
   LLM 也常把真实标题记错而非凭空编造。
3. **搜索 arXiv / 会议官网** —— 部分会议论文不进 Crossref。
4. **检查是否只是元数据错误** —— 如果论文真实存在，只是 bib 字段写错，
   应当修正字段而不是删除条目。
5. **确认正文论述是否依赖它** —— 如果依赖且确实找不到真实来源，
   应改写论述（如"该问题尚缺乏充分证据"），而不是保留一条假引用。

**永远不要**为了让报告"变绿"而删除审计结论。`UNCHECKED` 也不等于通过。