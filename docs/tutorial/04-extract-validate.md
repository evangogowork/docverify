# 04 抽取和校验：每个字段都带置信度

> 视频：[p04-extract.mp4](../videos/p04-extract.mp4) · tag：`step-04`

## 这一章解决什么问题？

队列里有消息了，现在要有人把文件读出来：商家名、注册号、地址、发证日期、有效期、发证地。
读法有很多种：OCR、PDF 文字层、版面模型、大模型。它们有一个共同点：**都会读错**。

所以这一章的关键设计不是「怎么读」，而是**读出来的东西长什么样**：每个字段都是 `(值, 置信度, 来源)`。
校验和决策只认这个形状，不关心背后是哪个引擎。

## 抽取器接口

```python
class Extractor(Protocol):
    name: str
    def extract(self, data: bytes, content_type: str) -> Extraction: ...
```

默认实现按文件的魔数（magic bytes）分派，不信客户端声明的 Content-Type：

- PNG / JPEG → Tesseract OCR，取每个词的置信度，一行的置信度取这一行最差的四分之一的平均。
- PDF → 文字层，置信度 0.98；没有文字层就当成不支持的格式。
- 其它 → `UnsupportedFormat`，case 直接进 RESUBMIT_REQUESTED，请平台重新提交。

想换成模型，设置 `DOCVERIFY_EXTRACTOR=包.模块:类名` 就行。

## 假设：图片越糊，置信度就该越低，而不是读出错的值还说很有把握

真实跑一次，同一份执照渲染成不同质量：

```
clean   {'business_name': ('Nguyén Van An Trading Co.', 0.91), 'registration_number': ('CA-123456782', 0.89), ...}
blur    {'business_name': ('Nguyén Van An Trading Co', 0.87), ..., 'issue_date': ('2025-03-01', 0.62)}  missing: expiry_date, issuing_authority
lowres  {'business_name': (..., 0.44), 'registration_number': ('CA-123456782', 0.28), 'issuing_authority': ('GA', 0.0)}
rotate  {'address': ('4200 Market si, San Francisco, cA 94102', 0.34), 'issue_date': ('9025-03-01', 0.59), ...}
pdf     {'business_name': ('Nguyễn Văn An Trading Co.', 0.98), ...}
```

两点值得注意：

1. 低分辨率把 CA 读成了 GA，但置信度是 0.0。如果只看值，这会变成一条「发证地和注册号前缀不一致」的规则失败，看起来像是被篡改的文档。
   置信度让我们能分辨：这是读坏了，不是文档有问题。
2. 旋转之后，2025 被读成了 9025。值完全错了，但置信度 0.59，低于阈值。
3. 模糊图上读到的字段置信度照样有 0.87。它被拦下，靠的是有两个字段没读出来，不是置信度。换一个 Tesseract 版本（CI 上的 Ubuntu 版），六个字段全读出来、全过阈值，模糊图就被自动通过了。
   所以假设只对了一半：**OCR 的置信度说的是「这个字读得准不准」，不是「这张图清不清楚」。**
   抽取现在还会直接量图像的清晰度（拉普拉斯方差，`docverify/extract.py` 锚点 `sharpness`），低于阈值就把所有字段的置信度压到 0.5，案子一定进人审。来龙去脉见 [日常问题 q11](../problems.md)。

## 校验只产出检查结果，不做决定

`validate()` 返回三类检查：

| 类型 | 例子 |
|---|---|
| schema | 字段齐不齐，注册号是不是 `XX-dddddddd + 校验位`，日期是不是 ISO 格式 |
| rule（确定性规则） | Luhn 校验位、未过期、发证不在未来、发证地是已知州、注册号前缀等于发证地 |
| confidence | 每个字段的置信度是否过它自己的阈值 |

每条检查都记下它依赖的字段的置信度。到第 05 章就能看到为什么这一点很重要。

## 代码

- 接口：`docverify/extract.py`（锚点 `@learn:extractor-protocol`、`@learn:ocr`）
- 校验：`docverify/validate.py`（锚点 `@learn:validate`）
- worker 的推进循环：`docverify/worker.py`（锚点 `@learn:worker-process`）

## 怎么跑到这一步

```bash
git checkout step-04
brew install tesseract            # Ubuntu: apt-get install tesseract-ocr
.venv/bin/pytest tests/test_step04_pipeline.py
```
