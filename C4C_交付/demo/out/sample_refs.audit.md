# 引用真伪审计报告 / Citation Truth Audit Report

- **输入文件**: `demo/sample_refs.bib`
- **审计条数**: 8
- **用时**: 5.3s
- **数据源**: Crossref → arXiv → OpenAlex（含回退）

## 1. 判定汇总

| 判定 | 数量 | 占比 | 含义 |
|---|---|---|---|
| [VERIFIED] | 4 | 50% | 可用 |
| [PARTIAL] | 2 | 25% | 需人工确认字段 |
| [FABRICATED] | 2 | 25% | 疑似编造，必须删/换 |
| [UNCHECKED] | 0 | 0% | 证据不足，需核查 |

## 2. 逐条明细

### [FABRICATED] `doe2021innovative`

- **题名**: An Innovative Deep Learning Framework for Scalable Intelligence
- **作者**: Doe, Jane, Roe, Richard
- **年份**: 2031　**期刊**: In the Proceedings of the International Conference on Advanced Computational Methods
- **DOI**: -　**arXiv**: -
- **结论**: 最佳匹配仅 0.52 < 阈值 0.82（最接近的是《IOT-Enabled Deep Learning Framework for Scalable Crop Diseas》），判定为编造引用
- **幻觉指纹**:
  - [严重度 2] 年份 2031 不合理（未来或过旧）

### [FABRICATED] `smith2023deep`

- **题名**: A Deep Intelligent Neural Network Learning Model Based on Data Driven Adaptive Optimization for Advanced Machine Learning Applications
- **作者**: Smith, John A., Chen, Wei, Kumar, Rajesh, Patel, Suresh
- **年份**: 2023　**期刊**: Journal of Advanced Artificial Intelligence Research
- **DOI**: 10.1234/jair.2023.45112　**arXiv**: -
- **结论**: 最佳匹配仅 0.39 < 阈值 0.82（最接近的是《Neural Network-Based Discrete-Time Adaptive ILC》），判定为编造引用
- **幻觉指纹**:
  - [严重度 2] 标题由高频泛义词堆砌，疑似占位/编造

### [PARTIAL] `vaswani2017`

- **题名**: Attention Is All You Need
- **作者**: Vaswani, Ashish, Shazeer, Noam, Parmar, Niki, Uszkoreit, Jakob, Jones, Llion
- **年份**: 2017　**期刊**: Advances in Neural Information Processing Systems
- **DOI**: 10.5555/3295222.3295349　**arXiv**: -
- **结论**: 检索到同一篇论文（标题与作者均吻合），但数据源年份为 2025；常见于同一论文存在重印/修订版本，建议人工确认后再决定是否改 year 字段。 其余：年份不一致（bib=2017 vs 数据源=2025）
- **建议修正为**:
  - title = {Attention Is All You Need}
  - year = {2025}
  - journal = {}
  - doi = {10.65215/2q58a426}　url = {https://doi.org/10.65215/2q58a426}

### [PARTIAL] `goodfellow2014generative`

- **题名**: Generative Adversarial Nets
- **作者**: Goodfellow, Ian, Pouget-Abadie, Jean, Mirza, Mehdi, Xu, Bing, Warde-Farley, David
- **年份**: 2019　**期刊**: Advances in Neural Information Processing Systems
- **DOI**: -　**arXiv**: 1406.2661
- **结论**: 检索到论文，但年份不一致（bib=2019 vs 数据源=2014）；标题偏差（相似度 0.88）
- **建议修正为**:
  - title = {Generative Adversarial Networks}
  - year = {2014}
  - journal = {arXiv preprint}
  - doi = {-}　url = {https://arxiv.org/abs/1406.2661}

### [VERIFIED] `vaswani2017attention`

- **题名**: Attention Is All You Need
- **作者**: Vaswani, Ashish, Shazeer, Noam, Parmar, Niki, Uszkoreit, Jakob, Jones, Llion
- **年份**: 2017　**期刊**: Advances in Neural Information Processing Systems
- **DOI**: -　**arXiv**: 1706.03762
- **结论**: arXiv 命中，标题相似度 1.00，年份/作者一致

### [VERIFIED] `kingma2014adam`

- **题名**: Adam: A Method for Stochastic Optimization
- **作者**: Kingma, Diederik P., Ba, Jimmy
- **年份**: 2014　**期刊**: International Conference on Learning Representations
- **DOI**: -　**arXiv**: 1412.6980
- **结论**: arXiv 命中，标题相似度 1.00，年份/作者一致

### [VERIFIED] `devlin2019bert`

- **题名**: BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding
- **作者**: Devlin, Jacob, Chang, Ming-Wei, Lee, Kenton, Toutanova, Kristina
- **年份**: 2018　**期刊**: arXiv preprint
- **DOI**: -　**arXiv**: 1810.04805
- **结论**: arXiv 命中，标题相似度 1.00，年份/作者一致

### [VERIFIED] `lecun2015deep`

- **题名**: Delving Deep into Rectifiers: Surpassing Human-Level Performance on ImageNet Classification
- **作者**: He, Kaiming, Zhang, Xiangyu, Ren, Shaoqing, Sun, Jian
- **年份**: 2015　**期刊**: ICLR
- **DOI**: -　**arXiv**: 1502.01852
- **结论**: arXiv 命中，标题相似度 1.00，年份/作者一致

## 3. 修复建议

1. **删除或替换 2 条编造引用**——这些标题在 Crossref / arXiv / OpenAlex 中均不存在。
2. **修正 2 条 PARTIAL 引用**的年份/期刊/DOI 字段（见第 2 节建议值）。
3. 修正后用 `latexmk -pdf` 重新编译，确认无 undefined citation。
4. 若引用确实找不到但正文论述依赖它，改写为"已有工作尚缺证据"的表述，而非虚构引用。
