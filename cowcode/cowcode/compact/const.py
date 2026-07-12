"""上下文管理硬编码常量。"""

# 单条工具结果落盘阈值，单位 UTF-8 字节。
SINGLE_RESULT_LIMIT = 50000
# 单条 tool 消息内工具结果聚合阈值，单位 UTF-8 字节。
MESSAGE_AGGREGATE_LIMIT = 200000
# 摘要模型输出预留 token。
SUMMARY_RESERVE = 20000
# 自动压缩的估算安全余量。
AUTO_SAFETY_MARGIN = 13000
# 手动与紧急压缩的摘要请求安全余量。
MANUAL_SAFETY_MARGIN = 3000
# 恢复段最多展示的最近文件数。
RECOVERY_FILE_LIMIT = 5
# 恢复段单文件快照 token 上限。
RECOVERY_TOKENS_PER_FILE = 5000
# 摘要后保留近期原文 token 下界。
RECENT_KEEP_TOKENS = 10000
# 摘要后保留近期原文消息数下界。
RECENT_KEEP_MESSAGES = 5
# 自动摘要连续失败熔断阈值。
MAX_CONSECUTIVE_AUTO_COMPACT_FAILURES = 3
# 摘要请求自身 prompt too long 的直接重试次数。
PTL_RETRY_LIMIT = 3
# 直接重试后每次丢弃的消息组比例。
PTL_DROP_PERCENTAGE = 0.2
# 字符到 token 的估算比例。
ESTIMATE_CHARS_PER_TOKEN = 3.5
# 预览体头部字节上限。
PREVIEW_HEAD_BYTES = 2048
# 预览体头部行数上限。
PREVIEW_HEAD_LINES = 20
