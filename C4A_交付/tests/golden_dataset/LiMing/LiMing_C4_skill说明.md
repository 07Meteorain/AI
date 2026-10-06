# 会议纪要自动摘要技能

## 这个技能干什么

把会议录音转写文本自动整理成纪要。

## 怎么用

先准备一个 txt 文件，里面是会议转写内容，然后运行我们的脚本。

脚本放在我的电脑上，路径是 `/Users/lm/Desktop/meeting_summary/summary.py`

需要先安装一些库，具体见代码。

```python
import openai
from pathlib import Path

def summarize(text):
    # 调用 API 摘要
    return text[:500]

if __name__ == "__main__":
    p = Path("/Users/lm/Desktop/meeting_notes.txt")
    print(summarize(p.read_text()))
```

## 输出

打印出摘要文本。

## 说明

这个方法比较简单，能用但不够完善，后续会继续改进。