"""把文档切成检索用的小块。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .loader import Document

#: 切块参数变了，索引缓存必须失效，所以写进缓存键里。
CHUNKER_VERSION = "chunker-3"

CHUNK_SIZE = 300

#: markdown 表格的分隔行：`|---|---|`，紧随表头行之后。
_TABLE_SEPARATOR = re.compile(r"^\s*\|?[\s:|-]+\|[\s:|-]*$")


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _is_separator(line: str) -> bool:
    stripped = line.strip()
    return bool(stripped) and "|" in stripped and bool(_TABLE_SEPARATOR.match(stripped))


def _is_table_row(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("|") and stripped.count("|") >= 2


def chunk_document(document: Document) -> list[Chunk]:
    """一篇文档按行切块，尽量凑满 `CHUNK_SIZE` 字。

    两个要点：
    1. **按行边界切**，不按固定字符数硬切。硬切会把一行表格劈成两半
       （实测 KB-040 的 `| P02 |` 和 `味增拉面 | ✓ | …` 落在两个 chunk 里），
       引用出来就是半截句子。
    2. **表格块带上表头**。过敏原表那种 `| P06 | 牛肉poke | ✓ | ✓ | …` 的行，
       `✓` 本身不说明是哪种过敏原，含义全在表头（麸质/大豆/芝麻…）。
       把表头记进 `Chunk.table_header`，渲染时才能把 `✓` 还原成列名。
    """
    text = document.text
    lines = text.splitlines()

    # 先按"表格 / 非表格"分段，表格段记住自己的表头。
    segments: list[tuple[str, list[str]]] = []  # (内容, 表头)
    buffer: list[str] = []
    header: list[str] = []
    in_table = False

    def flush() -> None:
        if buffer:
            segments.append(("\n".join(buffer), list(header)))
            buffer.clear()

    for line in lines:
        if _is_table_row(line):
            if not in_table:
                # 表格开始：上一行如果是表头文字，它会紧跟分隔行。
                flush()
                in_table = True
            buffer.append(line)
            continue
        if in_table:
            if _is_separator(line):
                buffer.append(line)
                continue
            # 表格结束。第一行是表头，第二行是分隔行。
            rows = [row for row in buffer if not _is_separator(row)]
            if rows:
                header[:] = _cells(rows[0])
            flush()
            header.clear()
            in_table = False
        buffer.append(line)
    if in_table:
        # 文档以表格收尾：补一次表头，再冲最后一段。
        rows = [row for row in buffer if not _is_separator(row)]
        if rows:
            header[:] = _cells(rows[0])
        flush()
        header.clear()
    else:
        # 文档不在表格里收尾。**这一句不能少**：漏了它，最后一段永远留在
        # buffer 里不进 segments，整篇会被当成"没有内容"而退化成单块。
        flush()

    chunks: list[Chunk] = []
    number = 0
    for content, table_header in segments:
        is_table = bool(table_header)
        for piece in _split_piece(content, is_table):
            number += 1
            chunks.append(
                Chunk(
                    doc_id=document.doc_id,
                    chunk_id="%s#%d" % (document.doc_id, number),
                    text=piece,
                    source_text=piece,
                    heading=document.title,
                    kind="table" if is_table else "text",
                    table_header=list(table_header),
                )
            )
    if not chunks:
        piece = text.strip() or document.title
        chunks.append(
            Chunk(
                doc_id=document.doc_id,
                chunk_id="%s#1" % document.doc_id,
                text=piece,
                source_text=piece,
                heading=document.title,
            )
        )
    return chunks


def _split_piece(content: str, is_table: bool) -> list[str]:
    """把一段内容按 `CHUNK_SIZE` 切开，优先在行边界下刀。

    * 表格行不劈开 —— 劈开的半行引用出去没有意义；
    * 但**单行本身超长时必须硬切**（`.txt` 邮件正文常常一整段没有换行），
      否则整篇会挤成一个几千字的块，检索粒度全丢了。
    """
    if len(content) <= CHUNK_SIZE:
        return [content]
    pieces: list[str] = []
    current: list[str] = []
    size = 0

    def flush() -> None:
        if current:
            pieces.append("\n".join(current))
            current.clear()

    for line in content.splitlines():
        # 超长单行：先冲掉已攒的，再按 CHUNK_SIZE 硬切成几段。
        while len(line) + 1 > CHUNK_SIZE:
            flush()
            size = 0
            pieces.append(line[:CHUNK_SIZE])
            line = line[CHUNK_SIZE:]
        line_size = len(line) + 1
        if current and size + line_size > CHUNK_SIZE:
            flush()
            size = 0
        if line:
            current.append(line)
            size += line_size
    flush()
    if not is_table:
        return pieces
    # 表格里被切开的块各自补一行表头，保证每块单独看也读得懂。
    header = pieces[0].splitlines()[0] if pieces else ""
    return [piece if index == 0 else header + "\n" + piece for index, piece in enumerate(pieces)]


@dataclass
class Chunk:
    doc_id: str
    chunk_id: str
    text: str
    source_text: str
    heading: str = ""
    kind: str = "text"
    table_header: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "doc_id": self.doc_id,
            "chunk_id": self.chunk_id,
            "text": self.text,
            "source_text": self.source_text,
            "heading": self.heading,
            "kind": self.kind,
            "table_header": self.table_header,
        }


def chunk_documents(documents: list[Document]) -> list[Chunk]:
    chunks: list[Chunk] = []
    for document in documents:
        chunks.extend(chunk_document(document))
    return chunks
