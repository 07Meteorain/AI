---
title: 上下文腐化（Context Rot）
doc_id: context-rot
category: Week 1 · 上下文工程
source: CS146S_offline/pages/context-rot.html
origin: https://research.trychroma.com/context-rot
translator: AI 机器翻译 + 人工校对（术语表 v1.0）
coverage: 100%
---

# 上下文腐化（Context Rot）

> 原文：[https://research.trychroma.com/context-rot](https://research.trychroma.com/context-rot)

Chroma 技术报告

2025 年 7 月 14 日

# 上下文腐化：输入 token 增加如何影响大语言模型的表现

Kelly Hong

Anton Troynikov

Jeff Huber

人们通常假定大语言模型（LLM）会均匀地处理上下文——也就是说，模型处理第 10,000 个 token 应当和处理第 100 个 token 一样可靠。但实际上，这个假定并不成立。我们观察到，即使在简单任务上，模型表现也会随输入长度变化而显著波动。

在这份报告里，我们评测了 18 个大语言模型，其中包括最先进的 GPT-4.1、Claude 4、Gemini 2.5 和 Qwen3 系列模型。结果显示，模型并非均匀地使用它们的上下文；相反，输入越长，表现就越不可靠。

重复词任务上的 Claude Sonnet 4、GPT-4.1、Qwen3-32B 和 Gemini 2.5 Flash大语言模型近年的发展呈现出上下文窗口越来越长的趋势，最新一代模型的输入 token 数已达数百万。由于这些模型在大海捞针（Needle in a Haystack, NIAH）[1] 这类被广泛采用的基准测试上得分接近满分，人们往往想当然地认为它们在各类长上下文任务上表现稳定。

然而，NIAH 本质上是一个简单的检索任务：把一句已知的话（「针」）放进一篇由无关文本组成的长文档（「草堆」）里，再让模型把这句话找出来。这个基准虽然易于扩展，但通常考察的是直接的字面匹配，而这一点未必能代表那些灵活的、面向语义的任务。

大海捞针（NIAH）设置示例我们扩展了标准的 NIAH 任务，以便研究模型在此前很少被探索的设定下的行为。我们考察了两方面的影响：一是与问题之间存在语义关联（而非直接字面匹配）的针，二是对草堆内容做各种改动带来的影响。

此外，我们还加入了两项评测：一项是基于 LongMemEval [2] 的对话式问答评测，一项是让模型复述一串重复词的合成任务。每个任务都刻意保持简单，并被严格控制，以便单独隔离上下文长度的影响。

我们证明：即使在这些最简化的条件下，模型表现也会随输入变长而衰减，而且衰减方式常常出人意料、并不均匀。真实应用中的复杂度要高得多，这意味着输入长度的影响在实践中可能更加明显。

下面是我们完整的技术报告。如果觉得我们的工作有用，欢迎引用：

plaintext

```
```
@techreport{hong2025context,
  title = {Context Rot: How Increasing Input Tokens Impacts LLM Performance},
  author = {Hong, Kelly and Troynikov, Anton and Huber, Jeff},
  year = {2025},
  month = {July},
  institution = {Chroma},
  url = {https://trychroma.com/research/context-rot},
}
```
```
有兴趣一起改进 AI 应用的检索能力吗？Chroma 正在招聘

简介#

如今的大语言模型，输入上下文长度普遍达到数百万 token。Gemini 1.5 Pro [3] 在 2024 年初率先推出 1M 上下文窗口，随后是最近的 GPT-4.1 的 1M 上下文窗口 [4]，以及达到 10M 的 Llama 4 [5]。长上下文的用例很有说服力：上下文越长，大语言模型每次调用能处理的信息就越多，生成的输出也越有依据。

针对这些模型的长上下文评测，往往显示它们在不同输入长度下表现一致。但这些评测范围很窄，并不能代表长上下文在实践中的真实用法。最常用的测试大海捞针（Needle in a Haystack, NIAH）只是一个简单的字面检索任务，却常被用来推断模型能否可靠处理长上下文。而真实应用——比如智能体任务或摘要生成——需要模型对更广、往往也更含混的信息做多得多的处理和推理。

设计真实的长上下文基准并不容易。任务难度常常随输入长度一起上升，让人很难分清表现下滑到底是因为输入变长，还是因为题目本身变难。为此，我们的实验保持任务难度恒定，只改变输入长度——这样就能直接测量输入长度本身的影响。

贡献#

我们给出以下内容：

- 一项覆盖 18 个大语言模型的评测，涵盖领先的闭源模型和开放权重模型，揭示了表现随输入变长而变得不均匀。

- 一份关于模型在处理干扰项、以及问答相似度变化时特有行为模式的观察记录。

- 完整代码库，可复现我们的结果。

相关工作#

评测模型长上下文能力最广泛使用的基准之一是大海捞针（NIAH）。它作为一项可扩展的测试很有用，但考察的能力很窄：字面检索。模型在 NIAH 上通常表现不错，这让人们形成了「长上下文基本已被解决」的印象。

然而，NIAH 低估了大多数长上下文任务在实践中的真实要求。NIAH 的各种变体——比如包含非字面匹配针-问题对的 NoLiMa [6]——暴露出显著的性能下滑。其他难度看起来相近的任务，例如检验模型能否识别某段文本「不存在」的 AbsenceBench [7]，同样显示出随输入变长而衰退的表现。

此外，长上下文任务往往要求模型在多个干扰项之间做消歧。一个例子是多轮共指消解（Multi-round co-reference resolution, MRCR）[8] [9]：在一段多轮对话中，从多条相似的用户提问里检索出第 i 次出现的那个特定提问。不过，干扰项在长上下文设定下的影响仍然缺少研究。

长上下文任务里有个重要因素：输入长度是怎么被拉长的。Latent List [8] 是一个任务，模型要在各种输入长度下执行固定数量的 Python 列表操作。实验测试了用各种方式填充无关上下文，结果显示这些方式对模型表现的影响并不均匀 [1]。比如，加入那些局部相互抵消的列表操作，比加入 print 语句更能明显地拉低模型表现。这说明「无关内容」的类型很关键——有些无关内容会随输入变长而不断引入额外复杂度。

同样地，Graphwalks [10] 是一个图遍历任务：模型拿到一张由十六进制哈希构成的有向图，然后被要求从某个随机节点开始做广度优先搜索。输入变长意味着要遍历的图变大，结果就是任务难度也变高。很难把「任务变复杂」和「输入变长」区分开，也就很难单独分离出输入长度对表现的影响。这正说明把输入长度单独作为研究变量有多重要——只有这样，才能真正搞清大语言模型在长输入下究竟如何表现。

大海捞针扩展#

经典的大海捞针任务，是把一个随机事实（「针」）放在长上下文窗口（「草堆」）的中间，然后就此事实向模型提问。

这个任务的原始实现用的是字面匹配的针-问题对。然而，长上下文在实践中的使用，往往需要对含混任务做语义理解。

采用字面匹配的大海捞针（NIAH）设置示例NoLiMa 已经表明，随着上下文变长，非字面匹配对模型来说很成问题。这个任务使用的针-问题对，要求模型推断出隐含关联，例如：

问题：哪个角色去过赫尔辛基？

针：其实，Yuki 就住在 Kiasma 博物馆隔壁。

NoLiMa —— 针-问题对样例要回答这个问题，模型首先得知道 Kiasma 博物馆位于赫尔辛基，然后才能建立这个隐含关联。这不仅考验模型的非字面匹配能力，也考验它的世界知识。NoLiMa 中有 72.4% 的针-问题对需要这类外部知识，这让该基准更像是同时考察两项任务，而不只是纯粹的字面匹配。

单独考察非字面匹配的影响，仍然研究不足。此外，「字面」与「非字面」这种二分法，把真实场景中问答的复杂性过度简化了。针-问题对的相似度其实是一个连续谱，却全都被归进了这两个宽泛的类别。

模型往往还得应付干扰项，而已有研究表明这会拉低表现 [11]。

在本报告中，我们始终区分干扰项与无关内容：

对比 —— 干扰项 vs. 无关上下文

- 干扰项与针在主题上相关，但并不真正回答问题

- 无关内容与针和问题都不相关

已有研究表明干扰项的影响并不均匀，但多数评测的输入长度较短、用的模型也更老。当前的最先进模型被认为对干扰项更有韧性，但它们在不同输入长度下的表现并未被充分测试。

NIAH 另一个被低估的方面是草堆本身。人们往往只把它当作拉长输入长度的手段，这等于假设草堆内容本身对任务表现没有影响。如果模型确实对草堆内容不敏感，那么改动这些内容——比如草堆的主题或叙述流向——就不该影响结果。然而这个假设基本没被验证过。

我们设计了四组受控实验来考察这些因素的影响：

针-问题相似度#

我们用嵌入向量计算针-问题对之间的余弦相似度。为保证稳健性，我们在五个嵌入模型上取平均：text-embedding-3-small、text-embedding-3-large、jina-embeddings-v3、voyage-3-large 和 all-MiniLM-L6-v2。我们测量输入变长时，针-问题相似度如何影响模型表现。

干扰项的影响#

取一对高相似度的针-问题，我们写四个干扰项。设置如下：

- 基线：只有针，没有干扰项

- 单个干扰项：针 + 一个随机位置的干扰项

- 多个干扰项：针 + 全部四个干扰项，位置随机

我们在输入变长的过程中测试干扰项对模型表现的影响，以衡量干扰项之间、以及不同输入长度之间的不均匀性。

针-草堆相似度#

我们用两个主题截然不同的草堆——Paul Graham 的文章和 arXiv 论文 [12]——并分别为它们写对应的针。为了测量针-草堆相似度，我们对草堆做嵌入向量，为每个针检索出最相关的前 5 个文本块，再对它们的余弦相似度取平均。为保证稳健性，整个过程在五个不同的嵌入模型上重复。

草堆结构#

在典型的 NIAH 设置中，草堆是若干段连贯文本的拼接，每段都有自己一套想法的逻辑走向。比如最初的 NIAH 基准用的是一系列 Paul Graham 的文章，每篇文章都按结构化的方式组织观点、形成一个论证。为了评测这种结构是否影响模型表现，我们对比两种条件：

- 原始：保留每段摘录内部的自然思路走向

- 打乱：在整个草堆范围内随机重排句子，保持总体主题不变，但失去逻辑连贯性

我们证明以下结论：

- 在所有实验中，模型表现都随输入变长而持续下降。

- 针-问题对相似度越低，表现衰减的速度越快。

- 干扰项对模型表现的影响并不均匀，取决于它们彼此之间有多「干扰」。输入越长，这种影响越明显，不同模型对干扰项的反应也各不相同。

- 针-草堆相似度对模型表现的影响并不一致，说明还需要进一步研究。

- 草堆的结构模式持续地影响模型处理长输入的方式。

细节#

对针的类型、草堆主题、草堆结构的每一种独特组合，我们在以下条件下测试每个模型：

- 8 种输入长度

- 11 个针位置

除设置不兼容（即 o3）或明确不推荐（即 Qwen 的「思考模式」）之外，我们都在各模型的最大上下文窗口内、temperature=0 的条件下评测。对 Qwen 模型，我们采用 YaRN 方法 [13]，把窗口从 32,768 扩展到 131,072 个 token。

适用时，我们同时纳入标准模式和「思考模式」。

我们用经过对齐的 GPT-4.1 评审来评测模型输出，方法见附录。

我们记录了模型拒绝尝试任务的少数情况（总计 194,480 次大语言模型调用中有 69 次——0.035%）。例如，Claude Opus 4 有时输出为空，stop_reason="refusal"。

针-问题相似度#

在真实应用中，人们往往要求模型处理含混的任务，并在不依赖精确字面匹配的前提下找出相关信息。比如，当智能体拿到一个需要检索大体量语料的任务时，用户很少会指定精确的关键词来说明哪部分相关。模型得自己推断相关性。

我们改变针-问题对的相似度，用它们嵌入向量的余弦相似度来量化。我们发现，针-问题相似度越低，模型表现随输入变长而下降得越厉害。这更贴近真实场景：问答之间很少有精确匹配，而语义上的含混会让长输入处理更难。

实验#

草堆内容取自两个领域：Paul Graham 的文章（与原始 NIAH 实验相同）和 arXiv 论文。对每种草堆主题（PG 文章、arXiv），我们先确定常见主题，用来指导问题和针的撰写。

我们用聚类来找出给定语料中最常见的主题：

- 把文档切成 1-3 句的文本块

- 用 text-embedding-3-large 对每个文本块做嵌入向量

- 用 UMAP [14] 做降维，参数为：n_neighbors=30, min_dist=0.05, n_components=50, random_state=42

- 用 HDBSCAN [15] 做聚类，参数为：min_cluster_size=10, min_samples=15

- 用最大边际相关性（MMR）为最大的那些簇各取 20 个有代表性的文本块

- 人工检查最大的簇，确定它们的主题和风格

用这套方法，我们识别出 PG 文章的一个常见主题是写作建议，往往以轶事形式出现；对 arXiv 论文，常见主题是信息检索，具体来说是重排序。

我们为每个主题写一个对应的问题：

PG 文章：「我从大学同学那里得到过的最好的写作建议是什么？」

arXiv 论文：「在科研领域，低延迟的重排序器中哪一种更受青睐？」

Paul Graham 文章与 arXiv 论文的问题在写针之前，我们先确认这些问题在草堆内容里没有答案：

- 我们把之前算好的草堆文本块嵌入向量存进向量数据库。

- 用问题的嵌入向量在该向量数据库中查询前 10 条结果。

- 人工检查这些结果，确认它们没有回答给定的问题。

这样就搭起了一个公平的测试环境：确保不存在其他可选答案，任何错误答案都只能来自模型的幻觉。

每个问题我们写 8 个针，每个针都属于那个大簇——这一点用近似预测来验证。归属于写作/检索簇且概率 >0.9 的针，被认为在主题上融入了草堆。这些针都是我们人工编写的，以避免数据污染。

对这 8 个针，我们还改变含混程度，量化方法如下：

- 用嵌入模型分别计算针和问题的嵌入向量，以及两者的余弦相似度。

- 在五个嵌入模型上重复上述计算（text-embedding-3-small、text-embedding-3-large、jina-embeddings-v3、voyage-3-large 和 all-MiniLM-L6-v2）。

在 PG 文章这个主题上，我们的针-问题相似度落在 0.445-0.775 之间，五个嵌入模型上的标准差均 <0.1。在 arXiv 主题上，针-问题相似度区间是 0.521-0.829，标准差同样 <0.1。

结果#

我们观察到一个清晰的规律：针-问题对相似度越低，表现随输入变长而下降得越快。

NIAH：针-问题相似度（同一模型的思考/非思考模式分别处理）—— arXiv 草堆/arXiv 针
 高表现：性能的前 33%
 蓝：高相似度针（相似度前 50%）
 红：低相似度针（相似度后 50%）在输入较短时，即使面对低相似度的针-问题对，模型表现依然不错。这一点在高/中等表现的模型上看得最清楚，说明这些模型在这项任务上、对所有针-问题对都有能力做对。

在较长输入下观察到的表现衰减，并不是针-问题配对本身难度高造成的。通过固定针-问题对、只改变无关内容的多少，我们把输入规模分离出来，确认它是表现下滑的主要因素。

我们还考察了针的位置是否影响表现。在 11 个针位置上测试后，我们发现这项特定的 NIAH 任务的表现没有明显变化。

干扰项的影响#

在较老的模型上早就已经确认：干扰项会拉低模型表现，而且影响并不均匀。新的模型则被认为能可靠应对任何干扰项——但输入变长之后，这一条还成立吗？

我们的实验显示，随着输入变长，干扰项的影响及其不均匀性在所有模型上都在放大，包括最新的最先进模型。我们还观察到，不同模型家族在处理含混性时表现出明显不同的行为。

实验#

从每个草堆主题（PG 文章和 arXiv 论文）中，我们取一个针-问题相似度较高的针（八个里相似度第二高的那个），并人工写 4 个干扰项：

问题：「我从大学同学那里得到过的最好的写作建议是什么？」

针：「我觉得我从大学同学那里得到的最好写作建议，是每周都写。」

干扰项：

- 「我从大学教授那里得到的最好写作建议，是每天都写。」

- 「我从大学同学那里听过的最差的写作建议，是把每篇文章用五种不同的风格来写。」

- 「我从同学那里得到的最好写作建议，是把每篇文章用三种不同的风格来写，那还是高中时候的事了。」

- 「我以前觉得我从大学同学那里得到的最好写作建议，是把每篇文章用四种不同的风格来写，但现在不这么想了。」

Paul Graham 文章主题下、针-问题相似度较高的那个针所用的干扰项我们没有对全部八根针都加干扰项来测试，而是选用一根针-问题相似度较高的针，制造一个「针相对容易被识别」的条件。从前面的结果可以看到，正因为针-问题相似度高，模型在各输入长度下在这个针上都表现不错，这让我们能更好地单独分离并测量干扰项的影响。

我们跑三种测试条件：

- 无干扰项（基线）：只有针

- 单个干扰项：针 + 一个干扰项（位置随机）

- 多个干扰项：针 + 全部四个干扰项，位置随机散布在草堆中

干扰项的影响 —— 三种条件

结果#

即便是单个干扰项，也会让表现低于基线（只有针）；而加入四个干扰项会让这一衰减进一步叠加。

干扰项的影响：按干扰项数量划分的表现 —— arXiv 草堆/PG 文章针我们还能看到，干扰项的影响并不均匀。比如在 arXiv 草堆 + PG 文章针这个组合里，可以看到干扰项 3（红色）比其他干扰项造成了更大的表现下滑。

干扰项的影响：按单个干扰项划分的表现 —— arXiv 草堆/PG 文章针为了进一步研究这种不均匀影响，我们分析了 4 干扰项条件下各模型的失败尝试。在 arXiv 草堆 + PG 文章针这个组合中，我们看到干扰项 2 和 3 在各模型的幻觉回答中出现得最频繁。

干扰项的影响：失败分析 —— arXiv 草堆/PG 文章针这些失败也暴露出不同模型在处理含混性上的差异。Claude 模型的幻觉率始终最低。具体来说，Claude Sonnet 4 和 Opus 4 相当保守，不确定时会倾向弃答，并明确表示找不到答案。相比之下，GPT 模型的幻觉率最高，干扰项一出现，它们常常给出自信但错误的回答。

针-草堆相似度#

在长上下文任务中，无关上下文往往只被当作中性的填充物，用来把输入长度撑起来。通常的假设是：只要不直接干扰任务，无关上下文的内容就无关紧要。

然而，一个很自然的问题浮上来：针-草堆相似度到底会不会影响任务难度？直觉上，如果针和草堆内容融在一起，模型提取出这根针会更费劲。

我们的发现表明，针-草堆相似度对模型表现的影响并不均匀。

实验#

我们用针-问题相似度实验中的那些针，搭建了测试针-草堆相似度影响的实验。

针-草堆相似度的测量方式是：对草堆做嵌入向量，为每根针检索出最相似的前五个文本块，再对它们的余弦相似度取平均。为保证稳健性，整个过程在五个不同的嵌入模型上重复。

在 PG 文章草堆中，PG 文章针的针-草堆相似度平均分是 0.529，波动 0.101；而 arXiv 针平均是 0.368，波动 0.111。反过来，在 arXiv 草堆中，arXiv 针平均为 0.654，波动 0.0858；PG 文章针则低得多，为 0.394，波动 0.105。

在每个草堆上，我们把语义相近的针和无关的针放在一起对比。比如，我们把 PG 文章针和 arXiv 针都放进 Paul Graham 文章的草堆里，以比较这两种条件：

针-草堆相似度：实验设置

结果#

我们在两种草堆（Paul Graham 文章和 arXiv 论文）上分别测试 PG 文章针与 arXiv 针。在 Paul Graham 文章草堆中，arXiv 针的表现明显好于 PG 文章针；换句话说，当针没有在语义上融入草堆时，模型表现更好。但在 arXiv 草堆中，我们只在 arXiv 针和 PG 文章针之间观察到极小的表现差异。

针-草堆相似度结果只测两个主题，不足以得出「针-草堆相似度越高，模型在这项任务上表现越差」这样可推广的结论。不过，它确实凸显了长上下文处理的非均匀性：即便任务结构和针-问题相似度都保持不变，仅仅改变针与草堆之间的语义相似度，就可能影响结果。这指向长上下文基准中一个尚未充分探索的区域，也是未来研究一个有价值的方向。

草堆结构#

除了针-草堆相似度，我们也考虑草堆的结构模式。

如果草堆由连贯的文章组成，随机插入的针可能打断思路的逻辑走向，从而更显眼。反过来，在句子顺序随机打乱的草堆里，因为整体上下文缺乏结构，针反而更容易混进去。这背后的假设是：模型对上下文的逻辑走向是敏感的——它以结构化、对顺序敏感的方式处理上下文。

令人意外的是，我们发现结构上的连贯性会持续损害模型表现。

这看起来违反直觉，但当草堆保留了思路的逻辑走向时，模型表现确实更差。把草堆打乱、去掉局部连贯性，则能稳定地提升表现。

实验#

为评测草堆结构的影响，我们构造了两个变体：

- 原始：保留每段摘录内部的自然思路走向

- 打乱：在整个草堆范围内随机重排句子，保持总体主题不变，但失去逻辑连贯性

草堆结构：实验设置示例

结果#

在全部 18 个模型和所有针-草堆组合下，我们都观察到一个一致的规律：模型在打乱的草堆上表现优于有逻辑结构的草堆。

草堆结构：18 个模型在原始与打乱草堆上的平均表现这些结果可能对模型的内部处理意味着一些东西：输入的结构模式或许会影响注意力机制的作用方式，在输入变长时尤其如此。

虽然这超出了本报告的范围，但它指出了可解释性研究的一个可能方向：注意力如何受到输入结构的影响。理解这些随输入变长而出现的结构性影响，或许能解释这些长上下文失败模式。

LongMemEval#

为了在更贴近真实的场景中评测这些模型，我们使用 LongMemEval——一个面向对话式问答的长上下文基准。

聊天助手使用长输入，是维持后续对话所需相关历史的常见做法。要让聊天助手带上「记忆」，一个朴素的办法是在后续对话的提示词里塞进完整的对话历史。这要求模型完成两项任务，而这两项通常是在一次调用里做完的：从对话历史中找出相关部分（检索），再把它们综合成对当前查询有用的形式（推理）。

理想情况下，模型只会被喂给相关的部分，这样它就能专心推理。加入无关上下文，就多出了一步「辨认什么相关」，迫使模型同时干两件事。

我们通过两种条件，系统地测试在输入变长时多加这一步带来的影响：

- 聚焦输入，只包含相关部分，因此模型只需做简单的推理。

- 完整输入，使用 LongMemEval 完整的 113k token 输入，其中包含无关上下文。这种情况下，模型除了推理，还得在长上下文里做检索。

我们先确认模型完全有能力在聚焦输入上做好，然后观察到换成长输入时表现一致下滑。这一性能下降说明：加入无关上下文——也就是多加一步检索——会显著影响模型维持稳定表现的能力。

实验#

给定一段用户与助手之间的对话历史，模型的任务是回答一个与该对话历史某部分相关的问题。

LongMemEval —— 按问题类型划分的样例 [[2](#longmemeval-source)]我们使用 LongMemEval_s，并筛选出属于知识更新、时间推理和多会话这几个类别的任务。随后我们人工清理了这份数据集，因为有些问题过于含混和/或根本无法回答；过滤掉 38 条提示词后，最终剩下 306 条。这些提示词平均约 113k token。

这些长提示词大部分由与问题无关的内容构成，有时还夹带看起来与问题相关的干扰项。我们把模型在这类长提示词上的表现，与一个「聚焦版本」作比较——后者只包含回答问题所需的相关部分。

聚焦提示词平均约 300 token，来自原始标注数据集并经过人工调整。

模型输出由经过对齐的大语言模型评审来评判（GPT-4.1，与人类判断的一致性 >99%）。

结果#

在所有模型上，我们都看到聚焦提示词上的表现显著高于完整提示词。

LongMemEval 结果 —— Claude 家族Claude 模型在聚焦提示词与完整提示词之间的差距最为明显。这一落差主要来自含混时弃答、导致模型不确定的行为，与该模型家族在 NIAH 中面对干扰项时的表现如出一辙。这一行为在 Claude Opus 4 和 Sonnet 4 上最为突出：它们在含混时似乎格外保守，因此在完整提示词上的表现低于更早的 Claude 模型。

问题：从我参加园艺工作坊的那天，到我种下番茄苗的那天，中间过了多少天？

正确答案：6 天。7 天（含首尾两天）也可以接受。

模型输出：我无法确定园艺工作坊和种下番茄苗之间相隔多少天，因为对话历史中没有提供这两个事件的具体日期。

LongMemEval —— Claude Sonnet 4（非思考模式）在包含这些日期的完整提示词上的表现聚焦提示词上表现更强的趋势，在 GPT、Gemini 和 Qwen 各家族同样成立。对于支持思考模式的模型，启用后它们在聚焦和完整提示词上都有明显提升。不过，即便在最新模型上开启了完整推理能力，两种输入长度之间仍存在性能差距。

LongMemEval 结果 —— GPT 家族

LongMemEval 结果 —— Gemini 家族

LongMemEval 结果 —— Qwen 家族我们还观察到不同问题类型之间的规律。在非思考模式下，模型在知识更新上通常表现最好，其次是多会话，再次是时间推理——无论聚焦提示词还是完整提示词都是如此。但开启思考后，这个排序会变成：知识更新、时间推理、多会话。

LongMemEval 按问题类型划分的结果 —— Claude Opus 4

重复词#

前面的实验只考察了输入长度本身如何影响模型表现。但如果输出长度也跟着输入一起增长呢？由于这些模型是自回归的，模型的输出其实也属于它的输入；每个 token 都是在给定输入和此前已生成 token 的条件下生成的。

想象一个把某个字符串重复 n 次的基础程序——它每次产出的输出都一模一样。对于这么简单的任务，我们本以为这些模型同样可靠，也愿意把它们当成计算系统来看。

然而我们的发现表明：即使在这类直白的任务上，随着上下文长度（同时包含输入和输出长度）增长，模型表现也会变得不均匀。

实验#

我们设计了一个受控任务，要求模型复现一串重复词，并在某个特定位置插入一个独特的词。提示词明确要求模型逐字复现输入文本。

一个示例提示词是：

请照原样复现以下文本，输出完全相同的内容：apple apple apple apple apples apple apple apple apple apple apple apple apple apple apple apple apple apple apple apple apple apple apple apple apple

重复词 —— 样本提示词，其中 'apple' 是重复词，'apples' 是独特词对于给定的词组合，我们构造出 1090 种上下文长度与独特词位置的组合：

- 词数：25, 50, 75, 100, 250, 500, 750, 1000, 2500, 5000, 7500, 10000

- 位置：

- num_words <= 100 时的所有可能位置

我们在以下词组合上执行这项任务：

- 重复词："apple" | 独特词："apples"

- 重复词："apples" | 独特词："apple"

- 重复词："golden" | 独特词："Golden"

- 重复词："orange" | 独特词："run"

- 重复词："orange" | 独特词："San Francisco"

- 重复词："San Francisco" | 独特词："sf"

- 重复词："Golden Gate Bridge" | 独特词："Golden Gate Park"

注意："San Francisco" 算 1 个词，"Golden Gate Bridge/Park" 算 1 个词

模型配置：

- max_output_tokens = input_tokens *2（不超过模型的最大输出 token 上限，老模型的这个上限通常更低）

- temperature = 0

- thinking = max(0, minimum_thinking_budget)

对推理模型，我们的做法是把思考预算设为 0 或最小值，比如 Gemini 2.5 Pro 为 128 个 token。我们排除了 OpenAI 的 o3，因为它不支持基于 token 的思考预算，也无法配置固定输出长度，而后者对保持各次评测的一致性是必需的。

分数由归一化的 Levenshtein 距离计算得出。

我们遇到模型不尝试完成任务的情况，判定方式如下：

- 带有停止原因的空输出（即 GPT-3.5 turbo 的 finish_reason='content_filter'）

- 非空输出，但输出无效：

- 纯粹在陈述观察、完全没有尝试：

I notice there's a discrepancy in the text. The word "apples" appears once in the original text (instead of "apple"), located in what appears to be around line 89 or 90 of the text block. Since you asked me to replicate the exact same text, I should point out this difference. Would you like me to:

- Replicate it exactly as shown (with the one instance of "apples")

- Correct it to "apple" to match the pattern

- Simply proceed with replicating it exactly as is Please let me know how you'd like me to proceed.

重复词 —— Claude Opus 4 的输出

- 拒绝回答：

- Refusals to answer:

重复词 —— GPT-4.1 的输出

- 随机输出：

-\n-\n--\n-\n-\n-\n-\n-\n-\n-\n-\n-\n-\n-\n-...

重复词 —— Gemini 2.5 Pro 的输出我们把这类情况排除，并在结果中单独标注拒答比例和常见模式。我们只计入真正尝试了任务的案例，包括那些以如下短语开头的：

I notice there's a discrepancy in the text. At one point, "apple" changes to "apples" (with an 's'). I'll replicate the text exactly as provided:

apple apple apple apple apple apple apple apple apple...

重复词 —— Claude Opus 4 的输出对于这些案例，我们采用同样的评分流程，对未严格遵循指令的模型施加轻微惩罚。

我们完全排除 GPT-3.5 turbo，因为在 60.29% 的任务上它都拒绝生成输出，原因是 finish_reason='content_filter'。

我们从几个维度分析输出：

- 归一化的 Levenshtein 距离

- 独特词是否出现及其位置

- 正确：独特词存在，且出现在正确的下标位置

- 位置错误：独特词出现了，但下标不对

- 词数差（输入词数 - 生成的词数）

结果#

随着上下文变长，所有模型的表现都持续下降。在这项实验里，输入长度与输出长度成正比，这与我们此前那些输出长度基本固定在短水平的测试不同。这一设定让我们可以评测模型可靠复现长序列的能力。

我们还观察到模型不尝试任务的现象，这在所有模型家族中都出现了。

重复词 —— Claude 家族我们观察到 Sonnet 3.5（红色）在达到其最大输出 token 数 8192 之前，表现优于更新的 Claude 模型。Opus 4（蓝色）虽然衰减速度最慢，但也是这一家族中唯一会拒答任务的模型（占尝试次数的 2.89%）。

Opus 4 有一个常见模式：模型先做一番观察，再决定是否继续，然后要么尝试、要么不尝试。这种行为通常从 2500 个词左右开始出现。

也有一些情况，Opus 4 直接拒绝尝试任务，原因是：

- 有生成受版权保护内容的风险

I can't replicate that exact text as requested. While it appears to be just a repetition of "San Francisco," I should avoid reproducing text verbatim when asked to do so, as this could potentially be used to test if I would reproduce copyrighted material in other contexts.

Instead, I can tell you that the text contains "sf" followed by the phrase "San Francisco" repeated 24 times.

重复词 —— Claude Opus 4 的输出

- 重复序列中出现不一致

I notice there's an error in the text you provided. In one instance, "San Francisco" appears as "San Francisco sf San Francisco" (with an extra "sf" in the middle). Since you asked me to replicate the exact text, I cannot provide a perfect replication as the source contains this inconsistency.

The text consists of "San Francisco" repeated many times, but with that one error embedded within it.

重复词 —— Claude Opus 4 的输出我们还测量位置准确率：独特词是否出现在正确位置。当独特词放在序列靠前的位置时，准确率最高——输入越长越是如此。

重复词：位置准确率 —— Claude 家族此外，随着上下文变长，模型往往会一直生成重复词，直到撞上输出 token 上限。我们用输入与输出的词数之差来量化这一点：

- 正值 = 模型生成不足

- 负值 = 模型生成过量

重复词：词数差 —— Claude 家族在 GPT 家族中，我们观察到 GPT-4.1 的拒答率为 2.55%。这类拒答通常从 2500 个词左右开始出现，回复类似于“I'm sorry, but I can't help with that”。

重复词 —— GPT 家族我们还观察到 GPT-4 turbo 在 500 个词附近有一个局部性能峰值。在 50 到 250 个词之间，模型倾向于过量生成（把重复词一直写到输出上限），但到 500 个词时，它的词数变得更准确。然而越过这个点后，它又开始生成不足——从输入与输出词数之差为正可以看出这一点。

重复词：词数差 —— GPT-4 Turbo位置准确率呈现类似趋势：当独特词出现在输入靠前位置时，GPT 模型也更容易把它放对。

这个家族还有一些更鲜明的模型特有行为。

GPT-4.1 mini 会尝试所有任务，但有时在“Golden Gate Bridge”/”Golden Gate Park”这个组合上会生成随机词。所谓随机输出，是指输入中不存在的词，或词语序列。

模型输出了重复的词，比如“Golden Golden”和“Gate Gate”，它们并不存在于输入中（输入只包含“Golden Gate Bridge”和”Golden Gate Park”）。

这些重复词并不出现在独特词的位置上，而是出现在文本中更靠后的位置。

GPT-4.1 nano 在“San Francisco”/“sf”这一对上也表现类似，偶尔会输出小写的 "san"s。

模型输出片段：

San Francisco San Francisco San Francisco San Francisco San Francisco San Francisco San Francisco San Francisco San Francisco san Francisco san Francisco san Francisco san Francisco

标准答案中对应的部分：

San Francisco San Francisco San Francisco San Francisco San Francisco San Francisco San Francisco San Francisco San Francisco San Francisco San Francisco San Francisco San Francisco

重复词 —— GPT-4.1 nano在这些随机词上，我们看出了一些与位置有关的结构迹象。我们观察到独特词的位置与随机词开始出现的位置之间存在相关性，这或许是未来值得探究的方向。

GPT-4 Turbo 在这个家族中输出变化最大，意味着模型更容易生成随机输出，而且随机输出的种类也更丰富。

重复词 —— Gemini 家族总体上，随着上下文变长，各模型的表现都在下降。在 Gemini 2.5 Pro（蓝色）身上，我们看到起点更低，因为在 50 个词时，模型生成的词数就少于应有数量。

在这个家族的所有词组合和所有模型上——除了 Gemini 2.5 Flash 在“apples”/“apple”这一组——我们都观察到了输入中不存在的随机词。这通常从 500-750 个词左右开始，其中 Gemini 2.5 Pro 的波动最大，其次是 2.0 Flash，再是 2.5 Flash。

"golden" | "Golden" (2,500 words):

- - "I'-a-le-le-le-le-le-le-'a-le-le-le-le-le-le-le--le-le-le-le-le-le-le...

"orange" | "run" (10,000 words):

orange orange orange--g.-g/2021/01/20/orange-county-california-sheriff-deputies-wore...

重复词 —— Gemini 2.5 Pro 的样本输出

重复词 —— Qwen 家族我们只在 Qwen3-8B 上观察到不尝试的情况，占全部任务的 4.21%。在这个模型上，我们观察到随机输出从 5000 个词左右开始出现：

Okay, I'm going to take a break. Let me know, I'm not in the mood. I need to chill out. I'm going to go somewhere and get some fresh air. Maybe go to the beach, or just chill out somewhere. I don't know, but I need to take a break. Let me know, I'm not in the mood. I need to chill out. I'm going to go somewhere and get some fresh air. Maybe go to the beach, or just chill out somewhere. I don't know, but I need to take a break. Let me know, I'm not in the mood. I need to chill out. I'm going to go somewhere and get some fresh air. Maybe go to the beach, or just chill out somewhere. I don't know, but I need to take a break. Let me know, I'm not in the mood. I need to chill out. I'm going to go somewhere and get some fresh air. Maybe go to the beach, or just chill out somewhere. I don't know, but I need to take a break. Let me know, I'm not in the mood. I need to chill out. I'm going to go somewhere and...

重复词 —— Qwen3-8B 在 'golden' | 'Golden' 上的输出（5,000 words）

局限性与未来工作#

我们的实验表明，大语言模型在不同上下文长度下表现并不一致，即使在简单任务上也是如此。但这项评测并未穷尽真实世界的使用场景。在实践中，长上下文应用往往复杂得多，需要综合或多步推理。基于我们的发现，我们预计在这些条件下表现衰减会更严重。

我们的结果对未来的长上下文评测工作也有影响。一个常见局限——此前关于长上下文基准的研究也提到过——就是倾向于把输入长度和任务难度混为一谈，因为更长的输入往往带来更复杂的推理。我们的实验刻意把输入长度单独隔离出来作为一个因素，并把任务难度保持恒定。未来工作的一个重要方向是拆清模型的性能衰减有多少来自任务本身的内在难度，又有多少来自它有效处理长上下文的能力。

我们也没有解释这种性能衰减背后的机制。我们的观察表明，上 下文的结构属性——比如相关信息的位置安排或重复出现——会影响模型行为，但我们没有关于「为什么会这样」的确定答案。要研究这些效应，需要对机制可解释性做更深入的探究，这超出了本报告的范围。

更广地说，我们的发现指向了上下文工程的重要性：精心构建和管理模型的上下文窗口。信息在模型上下文中的呈现位置与呈现方式，会强烈影响任务表现，因此这是未来优化模型表现一个有价值的方向。

结论#

通过实验我们证明，大语言模型并不能在不同输入长度下保持一致的表现。即便在非字面检索或文本复现这样简单的任务上，我们也看到表现随输入变长而越来越不均匀。

我们的结果凸显了两个必要性：现有基准之外还需要更严格的长上下文评测，以及上下文工程本身。相关信息是否存在于模型的上下文中固然重要，但更重要的，是这些信息被如何呈现。我们证明，即便能力最强的模型对此也很敏感，因此有效的上下文工程是获得可靠表现的必要条件。

脚注#

[1]（2025 年 7 月 16 日）补充了 Latent List 的相关洞见并作了澄清，贡献者 Kiran Vodrahalli（Google Deepmind）

[2] 示例的原始来源：https://arxiv.org/pdf/2410.10813

参考文献#

[1] Kamradt, G. (2023). Needle In A Haystack - Pressure Testing LLMs [GitHub Repository]. Link

[2] Wu, D., Wang, H., Yu, W., Zhang, Y., Chang, K.-W., and Yu, D. (2025). LongMemEval: Benchmarking Chat Assistants on Long-Term Interactive Memory. arXiv preprint arXiv:2410.10813. Link

[3] Gemini Team, Georgiev, P., Lei, V. I., Burnell, R., Bai, L., Gulati, A., Tanzer, G., Vincent, D., Pan, Z., Wang, S., et al. (2024). Gemini 1.5: Unlocking multimodal understanding across millions of tokens of context. arXiv preprint arXiv:2403.05530. Link

[4] OpenAI, Kumar, A., Yu, J., Hallman, J., Pokrass, M., Goucher, A., Ganesh, A., Cheng, B., McKinzie, B., Zhang, B., Koch, C., et al. (2025). Introducing GPT-4.1 in the API. Link

[5] Meta AI, (2025). The Llama 4 herd: The beginning of a new era of natively multimodal AI innovation. Link

[6] Modarressi, A., Deilamsalehy, H., Dernoncourt, F., Bui, T., Rossi, R. A., Yoon, S., and Schütze, H. (2025). NoLiMa: Long-Context Evaluation Beyond Literal Matching. arXiv preprint arXiv:2502.05167. Link

[7] Fu, H. Y., Shrivastava, A., Moore, J., West, P., Tan, C., and Holtzman, A. (2025). AbsenceBench: Language Models Can't Tell What's Missing. arXiv preprint arXiv:2506.11440. Link

[8] Vodrahalli, K., Ontanon, S., Tripuraneni, N., Xu, K., Jain, S., Shivanna, R., Hui, J., Dikkala, N., Kazemi, M., Fatemi, B., et al. (2024). Michelangelo: Long Context Evaluations Beyond Haystacks via Latent Structure Queries. arXiv preprint arXiv:2409.12640. Link

[9] openai. (2025). mrcr [Dataset]. Hugging Face. Link

[10] openai. (2025). graphwalks [Dataset]. Hugging Face. Link

[11] Shi, F., Chen, X., Misra, K., Scales, N., Dohan, D., Chi, E., Schärli, N., and Zhou, D. (2023). Large Language Models Can Be Easily Distracted by Irrelevant Context. arXiv preprint arXiv:2302.00093. Link

[12] jamescalam. (2024). ai-arxiv2 [Dataset]. Hugging Face. Link

[13] Peng, B., Quesnelle, J., Fan, H., and Shippole, E. (2023). YaRN: Efficient Context Window Extension of Large Language Models. arXiv preprint arXiv:2309.00071. Link

[14] McInnes, L., Healy, J., and Melville, J. (2020). UMAP: Uniform Manifold Approximation and Projection for Dimension Reduction. arXiv preprint arXiv:1802.03426. Link

[15] Campello, R. J. G. B., Moulavi, D., and Sander, J. (2013). Density-Based Clustering Based on Hierarchical Density Estimates. In Pei, J., Tseng, V. S., Cao, L., Motoda, H., and Xu, G. (Eds.), Advances in Knowledge Discovery and Data Mining (PAKDD 2013), Lecture Notes in Computer Science, vol 7819. Springer, Berlin, Heidelberg. Link

附录#

清洗后的 LongMemEval 数据集，以及所用的针/干扰项，都可以在此处下载。

大语言模型评审对齐#

我们采用大语言模型评审来评测 NIAH 和 LongMemEval 实验中的输出。这些评审通过以下流程与人类判断校准：

- 人工标注一部分模型输出为错误/正确（NIAH 约 500 条输出，LongMemEval 约 600 条输出）

- 用 GPT-4.1 对同一批模型输出标注为错误/正确。

- 通过测量人类与模型判断一致的比例，算出一致性得分。

- 根据人工检查出的不一致之处迭代提示词。

- 重复第 2-4 步，直到一致性得分 > 0.99。

测试的模型#

由于上下文窗口或 thinking_budget 的限制，并非全部 18 个模型都会出现在每项实验中。

Anthropic#

- Claude Opus 4

- Claude Sonnet 4

- Claude Sonnet 3.7

OpenAI#

Google#

- Gemini 2.5 Pro

- Gemini 2.5 Flash

- Gemini 2.0 Flash

Alibaba#

- Qwen3-235B-A22B

- Qwen3-32B

- Qwen3-8B

使用的嵌入模型#

- jina-embeddings-v3 (input_type='text-matching')

- voyage-3-large (input_type=None)

- all-MiniLM-L6-v2

针-问题相似度#

注意：同一模型的思考/非思考模式分别处理

针-问题相似度 —— arXiv 草堆/PG 文章针

针-问题相似度 —— PG 文章草堆/PG 文章针

针-问题相似度 —— PG 文章草堆/arXiv 针正如我们在针-草堆相似度结果中提到的，我们注意到这一次模型表现异常出色，与其他针-草堆组合形成鲜明对比。单看这一项，似乎这些高性能模型的表现是均匀的。然而，这些模型在其余实验中并不保持这种均匀性。

干扰项的影响#

干扰项的影响：按干扰项数量划分的表现 —— arXiv 草堆/arXiv 针

干扰项的影响：按单个干扰项划分的表现 —— arXiv 草堆/arXiv 针

干扰项的影响：按干扰项数量划分的表现 —— PG 文章草堆/PG 文章针

干扰项的影响：按单个干扰项划分的表现 —— PG 文章草堆/PG 文章针

干扰项的影响：按干扰项数量划分的表现 —— PG 文章草堆/arXiv 针

干扰项的影响：按单个干扰项划分的表现 —— PG 文章草堆/arXiv 针

干扰项的影响：失败分析 —— arXiv 草堆/arXiv 针

干扰项的影响：失败分析 —— PG 文章草堆/PG 文章针

干扰项的影响：失败分析 —— PG 文章草堆/arXiv 针

重复词#

重复词：位置准确率 —— GPT 家族

重复词：位置准确率 —— Gemini 家族

重复词：位置准确率 —— Qwen 家族

重复词：词数差 —— GPT 家族

重复词：词数差 —— Gemini 家族

重复词：词数差 —— Qwen 家族

### 产品

DatabaseSyncEnterprisePackage Search MCPDocsStatusContact

### 关注

GitHubXYouTube

### 公司

AboutChangelogCareers

### 法律

PrivacyTermsSecurity
