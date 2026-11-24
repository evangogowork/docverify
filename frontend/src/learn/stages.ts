// The learn page's stage list. Status and data come from GET /v1/learn/runs/{case_id};
// this file only says how to present each stage and which source anchors explain it.
export type StageDef = { id: string; title: string; sub: string; part: string; anchors: string[]; explain: string };

export const STAGES: StageDef[] = [
  { id: "upload", title: "上传", sub: "POST /v1/cases", part: "p01-upload", anchors: ["upload", "auth"],
    explain: "平台用自己的 API client 换来的 JWT 调用 v1 接口。API 先在 DynamoDB 里建 case（NEW → UPLOADED，attribute_not_exists 防止重复创建），再把文件写进 S3。" },
  { id: "s3", title: "S3", sub: "对象落地 + 事件", part: "p03-intake", anchors: ["s3-notification"],
    explain: "对象 key 是 账户/case/轮次/文件名，元数据里带 case_id 和轮次。桶上配置了 ObjectCreated 事件通知，指向 intake Lambda。" },
  { id: "lambda", title: "Lambda intake", sub: "UPLOADED → QUEUED", part: "p03-intake", anchors: ["lambda-intake"],
    explain: "S3 事件触发 Lambda：读对象元数据，用条件写把 case 从 UPLOADED 推到 QUEUED，再发一条 SQS FIFO 消息。下面是这次调用在 CloudWatch 里的真实日志。" },
  { id: "sqs", title: "SQS FIFO", sub: "MessageGroupId = 账户", part: "p06-idempotency", anchors: ["worker-handle", "dedup"],
    explain: "同一账户的消息在同一个 message group 里严格有序，不同账户并行。worker 收到消息先查 Redis：done 标记在就直接确认丢弃；拿不到处理锁就退让。" },
  { id: "extraction", title: "抽取", sub: "QUEUED → EXTRACTED", part: "p04-extract", anchors: ["extractor-protocol", "ocr", "worker-process"],
    explain: "抽取器在 Extractor 接口后面，可以替换成模型。默认是本地 Tesseract OCR（扫描件）或 PDF 文字层。每个字段都带置信度。" },
  { id: "validation", title: "校验", sub: "EXTRACTED → VALIDATED", part: "p04-extract", anchors: ["validate"],
    explain: "三类检查：schema（字段齐全、格式对）、确定性规则（有效期、注册号校验位、发证地）、置信度阈值。校验只产出检查结果，不做决定。" },
  { id: "decision", title: "决策", sub: "VALIDATED → ?", part: "p05-decide", anchors: ["normalize", "similarity", "alias-index", "decide", "transition"],
    explain: "商家名和地址先归一化，再用别名索引、编辑距离、token-set 和账户记录比对。只有全部检查通过、匹配也过线才自动通过；只有高置信度读出的确定性规则失败才自动驳回；其余一律进人审。" },
  { id: "review", title: "人审", sub: "IN_REVIEW → 结论", part: "p07-review", anchors: ["review-heap"],
    explain: "进人审的 case 按「风险分 × 六十秒 + 已等待秒数」排进最小堆。审核员领取时用条件写占住 case，提交结论时再用条件写确认还是自己领的。" },
  { id: "callback", title: "回调", sub: "签名 + 退避重试", part: "p08-callback", anchors: ["sign", "dispatch"],
    explain: "状态变化写进 MySQL 回调发件箱（每个 case、轮次、状态唯一），后台分发器用 HMAC-SHA256 签名投递，失败按指数退避重试。mock 平台验签并按 event_id 去重。" },
];

export const PANEL_PARTS: Record<string, string> = { state: "p02-state", eval: "p10-eval", learn: "p09-learn" };
