# 引用真伪审计报告 / Citation Truth Audit Report

- **输入文件**: `demo/c2_validation/C2_references.bib`
- **审计条数**: 17
- **用时**: 7.4s
- **数据源**: Crossref → arXiv → OpenAlex（含回退）

## 1. 判定汇总

| 判定 | 数量 | 占比 | 含义 |
|---|---|---|---|
| [VERIFIED] | 16 | 94% | 可用 |
| [PARTIAL] | 0 | 0% | 需人工确认字段 |
| [FABRICATED] | 0 | 0% | 疑似编造，必须删/换 |
| [UNCHECKED] | 1 | 5% | 证据不足，需核查 |

## 2. 逐条明细

### [UNCHECKED] `coqmanual`

- **题名**: The Coq Proof Assistant Reference Manual
- **作者**: {The Coq Development Team}
- **年份**: 2021　**期刊**: Coq documentation
- **DOI**: -　**arXiv**: -
- **结论**: 疑似软件手册/技术文档类条目——Crossref、arXiv、OpenAlex 均不收录此类文献，查不到属预期。请人工确认其存在性

### [VERIFIED] `alphageometry2024`

- **题名**: Solving olympiad geometry without human demonstrations
- **作者**: Trieu H. Trinh, Yuhuai Wu, Quoc Viet Le, He He, Thang Luong
- **年份**: 2024　**期刊**: Nature
- **DOI**: 10.1038/s41586-023-06747-5　**arXiv**: -
- **结论**: Crossref 命中，标题相似度 1.00，年份/作者一致

### [VERIFIED] `dsp2022`

- **题名**: Draft, Sketch, and Prove: Guiding Formal Theorem Provers with Informal Proofs
- **作者**: Albert Qiaochu Jiang, Sean Welleck, Jin Zhou, Wenda Li, Jiacheng Liu
- **年份**: 2022　**期刊**: arXiv (Cornell University)
- **DOI**: 10.48550/arxiv.2210.12283　**arXiv**: -
- **结论**: arXiv 命中，标题相似度 1.00，年份/作者一致

### [VERIFIED] `minif2f2021`

- **题名**: MiniF2F: a cross-system benchmark for formal Olympiad-level mathematics
- **作者**: Kunhao Zheng, Jesse Michael Han, Stanislas Polu
- **年份**: 2021　**期刊**: arXiv (Cornell University)
- **DOI**: 10.48550/arxiv.2109.00110　**arXiv**: -
- **结论**: arXiv 命中，标题相似度 1.00，年份/作者一致

### [VERIFIED] `leanworkbook2024`

- **题名**: Lean Workbook: A large-scale Lean problem set formalized from natural language math problems
- **作者**: Huaiyuan Ying, Zijian Wu, Yihan Geng, Zheng Yuan, Dahua Lin
- **年份**: 2024　**期刊**: arXiv (Cornell University)
- **DOI**: 10.48550/arxiv.2406.03847　**arXiv**: -
- **结论**: arXiv 命中，标题相似度 1.00，年份/作者一致

### [VERIFIED] `lean4tool`

- **题名**: The Lean 4 Theorem Prover and Programming Language
- **作者**: Leonardo de Moura, Sebastian Ullrich
- **年份**: 2021　**期刊**: Lecture notes in computer science
- **DOI**: 10.1007/978-3-030-79876-5_37　**arXiv**: -
- **结论**: Crossref 命中，标题相似度 1.00，年份/作者一致

### [VERIFIED] `isabelle2002`

- **题名**: Isabelle/HOL: A Proof Assistant for Higher-Order Logic
- **作者**: Tobias Nipkow, Markus Wenzel, Lawrence Charles Paulson
- **年份**: 2002　**期刊**: Digital Access to Libraries (Université catholique de Louvain (UCL), l'Université de Namur (UNamur) and the Université Saint-Louis (USL-B))
- **DOI**: 10.1007/3-540-45949-9　**arXiv**: -
- **结论**: OpenAlex 命中，标题相似度 1.00，年份/作者一致

### [VERIFIED] `wei2022cot`

- **题名**: Chain-Of-Thought Prompting Elicits Reasoning in Large Language Models
- **作者**: Jason Wei, Xuezhi Wang, Dale Schuurmans, Maarten Bosma, Brian Ichter
- **年份**: 2022　**期刊**: Advances in Neural Information Processing Systems
- **DOI**: 10.52202/068431-1800　**arXiv**: -
- **结论**: Crossref 命中，标题相似度 1.00，年份/作者一致

### [VERIFIED] `chen2022pot`

- **题名**: Program of Thoughts Prompting: Disentangling Computation from Reasoning for Numerical Reasoning Tasks
- **作者**: Wenhu Chen, Xueguang Ma, Xinyi Wang, William W. Cohen
- **年份**: 2022　**期刊**: arXiv (Cornell University)
- **DOI**: 10.48550/arxiv.2211.12588　**arXiv**: -
- **结论**: arXiv 命中，标题相似度 1.00，年份/作者一致

### [VERIFIED] `schick2023toolformer`

- **题名**: Toolformer: Language Models Can Teach Themselves to Use Tools
- **作者**: Timo Schick, Jane Dwivedi-Yu, Roberto Dessì, Roberta Răileanu, María Lomelí
- **年份**: 2023　**期刊**: arXiv (Cornell University)
- **DOI**: 10.48550/arxiv.2302.04761　**arXiv**: -
- **结论**: arXiv 命中，标题相似度 1.00，年份/作者一致

### [VERIFIED] `hendrycks2021math`

- **题名**: Measuring Mathematical Problem Solving With the MATH Dataset
- **作者**: Dan Hendrycks, Collin Burns, Saurav Kadavath, Akul Arora, Steven Basart
- **年份**: 2021　**期刊**: arXiv (Cornell University)
- **DOI**: 10.48550/arxiv.2103.03874　**arXiv**: -
- **结论**: arXiv 命中，标题相似度 1.00，年份/作者一致

### [VERIFIED] `cobbe2021verifiers`

- **题名**: Training Verifiers to Solve Math Word Problems
- **作者**: Karl Cobbe, Vineet Kosaraju, Mohammad Bavarian, Mark Chen, Heewoo Jun
- **年份**: 2021　**期刊**: arXiv (Cornell University)
- **DOI**: 10.48550/arxiv.2110.14168　**arXiv**: -
- **结论**: arXiv 命中，标题相似度 1.00，年份/作者一致

### [VERIFIED] `huh2024platonic`

- **题名**: The Platonic Representation Hypothesis
- **作者**: Minyoung Huh, Brian Cheung, Tongzhou Wang, Phillip Isola
- **年份**: 2024　**期刊**: arXiv (Cornell University)
- **DOI**: 10.48550/arxiv.2405.07987　**arXiv**: -
- **结论**: arXiv 命中，标题相似度 1.00，年份/作者一致

### [VERIFIED] `kaprison2025physics`

- **题名**: Physics of Language Models: Part 2.1, Grade-School Math and the Hidden Reasoning Process
- **作者**: Ye Tian, Zicheng Xu, Yuanzhi Li, Zeyuan Allen-Zhu
- **年份**: 2025　**期刊**: SSRN Electronic Journal
- **DOI**: 10.2139/ssrn.5250629　**arXiv**: -
- **结论**: Crossref 命中，标题相似度 1.00，年份/作者一致

### [VERIFIED] `bender2021parrots`

- **题名**: On the Dangers of Stochastic Parrots
- **作者**: Emily M. Bender, Timnit Gebru, Angelina McMillan-Major, Shmargaret Shmitchell
- **年份**: 2021　**期刊**: Proceedings of the 2021 ACM Conference on Fairness, Accountability, and Transparency
- **DOI**: 10.1145/3442188.3445922　**arXiv**: -
- **结论**: Crossref 命中，标题相似度 1.00，年份/作者一致

### [VERIFIED] `brown2020`

- **题名**: Language Models are Few-Shot Learners
- **作者**: Tom B. Brown, Benjamin Mann, Nick Ryder, Melanie Subbiah, Jared Kaplan
- **年份**: 2020　**期刊**: arXiv (Cornell University)
- **DOI**: 10.48550/arxiv.2005.14165　**arXiv**: -
- **结论**: arXiv 命中，标题相似度 1.00，年份/作者一致

### [VERIFIED] `alphaproof2025`

- **题名**: Olympiad-level formal mathematical reasoning with reinforcement learning
- **作者**: Thomas Hubert, Rishi Mehta, Laurent Sartran, Miklós Z. Horváth, Goran Žužić
- **年份**: 2025　**期刊**: Nature
- **DOI**: 10.1038/s41586-025-09833-y　**arXiv**: -
- **结论**: Crossref 命中，标题相似度 1.00，年份/作者一致

## 3. 修复建议

1. 未发现编造引用。
3. 修正后用 `latexmk -pdf` 重新编译，确认无 undefined citation。
4. 若引用确实找不到但正文论述依赖它，改写为"已有工作尚缺证据"的表述，而非虚构引用。
