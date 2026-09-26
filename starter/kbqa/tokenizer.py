"""分词。"""

from __future__ import annotations

import re
import unicodedata

#: 分词规则变了，索引缓存必须失效。
TOKENIZER_VERSION = "tokenizer-3"

#: 中文里几乎不携带信息的字。只用在“查询覆盖率”上，索引照常保留全部词。
STOP_CHARS = frozenset("的了吗呢是在有和与及或就都也还把被给对从向于个些这那哪什么怎样如何多少几请帮我你他它可以能要想会一下少吧啊呀们么样过得着为所")
STOP_WORDS = frozenset("the a an of to in is are and or for on at it this that how what".split())


#: 切词规则：连续的字母/数字算一个词，每个汉字单独算一个词，其余字符是分隔符。
#: 中文书面语不写空格，按空白切会把整句变成一个词，BM25 直接全零分。
_TOKEN_RE = re.compile(r"[a-z0-9]+|[\u4e00-\u9fff]")


def normalise(text: str) -> str:
    """全角转半角、统一大小写，比较与分词都走这一层。"""
    return unicodedata.normalize("NFKC", text or "").lower()


def tokenize(text: str) -> list[str]:
    """切词，直接喂给 BM25。

    中文没有词间空格，所以不能按空白切；这里把每个汉字切成一个词，
    英文与数字保持整词。这样中文问句的用字才有机会和文档对上。
    """
    return _TOKEN_RE.findall(normalise(text))


def content_tokens(text: str) -> list[str]:
    """去掉虚词之后的查询词，用来算“这个问题被文档覆盖了多少”。"""
    kept = []
    for token in tokenize(text):
        if token in STOP_WORDS:
            continue
        if all(char in STOP_CHARS for char in token):
            continue
        kept.append(token)
    return kept
