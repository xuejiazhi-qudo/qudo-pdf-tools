"""安全类操作：加密、解密、权限位读写。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import pymupdf

from ..worker import Progress
from .pages import _open, _safe_dir

Progress_ = Optional[Progress]

ALGO_AES256 = "aes256"
ALGO_AES128 = "aes128"
ALGO_RC4_128 = "rc4_128"
ALGO_RC4_40 = "rc4_40"

_ALGO_CONST = {
    ALGO_AES256: pymupdf.PDF_ENCRYPT_AES_256,
    ALGO_AES128: pymupdf.PDF_ENCRYPT_AES_128,
    ALGO_RC4_128: pymupdf.PDF_ENCRYPT_RC4_128,
    ALGO_RC4_40: pymupdf.PDF_ENCRYPT_RC4_40,
}

ALGO_LABELS = {
    ALGO_AES256: "AES-256（推荐）",
    ALGO_AES128: "AES-128",
    ALGO_RC4_128: "RC4 128 位（旧格式）",
    ALGO_RC4_40: "RC4 40 位（兼容性最好）",
}


@dataclass
class PermissionDef:
    key: str
    label: str
    const: int
    default: bool = True


PERMISSION_DEFS: List[PermissionDef] = [
    PermissionDef("print", "允许打印", pymupdf.PDF_PERM_PRINT),
    PermissionDef("print_hq", "允许高质量打印", pymupdf.PDF_PERM_PRINT_HQ),
    PermissionDef("modify", "允许修改内容", pymupdf.PDF_PERM_MODIFY),
    PermissionDef("copy", "允许复制文字和图片", pymupdf.PDF_PERM_COPY),
    PermissionDef("annotate", "允许添加批注", pymupdf.PDF_PERM_ANNOTATE),
    PermissionDef("form", "允许填写表单", pymupdf.PDF_PERM_FORM),
    PermissionDef("accessibility", "允许无障碍读取", pymupdf.PDF_PERM_ACCESSIBILITY),
    PermissionDef("assemble", "允许插入/删除页面", pymupdf.PDF_PERM_ASSEMBLE),
]


def permission_mask(keys: Optional[List[str]] = None) -> int:
    """把权限 key 列表转成 PDF 权限位掩码。None 表示全部允许。"""
    if keys is None:
        return 4095
    mask = 0
    for p in PERMISSION_DEFS:
        if p.key in keys:
            mask |= p.const
    return mask


def describe_permissions(mask: int) -> Dict[str, bool]:
    return {p.key: bool(mask & p.const) for p in PERMISSION_DEFS}


@dataclass
class EncryptOptions:
    user_password: str = ""
    owner_password: str = ""
    algorithm: str = ALGO_AES256
    permission_keys: Optional[List[str]] = None
    encrypt_metadata: bool = True

    def validate(self) -> None:
        if not self.user_password and not self.owner_password:
            raise ValueError("至少需要设置一个打开密码或权限密码")
        if self.algorithm not in _ALGO_CONST:
            raise ValueError(f"不支持的加密算法：{self.algorithm}")


def encrypt_file(
    src_path: str,
    output: str,
    options: EncryptOptions,
    src_password: Optional[str] = None,
    progress: Progress_ = None,
) -> str:
    """给 PDF 设置打开密码 / 权限密码。"""
    pr = progress or Progress()
    options.validate()

    doc = _open(src_path, src_password)
    try:
        pr.report(40, "正在加密")
        _safe_dir(output)
        doc.save(
            output,
            garbage=4,
            deflate=1,
            use_objstms=1,
            encryption=_ALGO_CONST[options.algorithm],
            permissions=permission_mask(options.permission_keys),
            owner_pw=options.owner_password or options.user_password,
            user_pw=options.user_password or options.owner_password,
        )
    finally:
        doc.close()

    pr.report(100, "完成")
    return output


def decrypt_file(
    src_path: str,
    output: str,
    password: str,
    progress: Progress_ = None,
) -> str:
    """移除 PDF 密码（必须提供正确密码）。"""
    pr = progress or Progress()
    doc = _open(src_path, password)
    try:
        pr.report(40, "正在移除密码")
        _safe_dir(output)
        doc.save(
            output,
            garbage=4,
            deflate=1,
            use_objstms=1,
            encryption=pymupdf.PDF_ENCRYPT_NONE,
        )
    finally:
        doc.close()

    pr.report(100, "完成")
    return output


def probe_encryption(src_path: str, password: Optional[str] = None) -> Dict[str, object]:
    """探测加密状态与权限位。加密文档必须先认证才能读到真实权限。"""
    doc = pymupdf.open(src_path)
    try:
        needs = bool(doc.needs_pass)
        encrypted = bool(doc.is_encrypted)
        if needs and password:
            doc.authenticate(password)
        perms = int(doc.permissions)
        method = (doc.metadata or {}).get("encryption") or ""
        return {
            "needs_password": needs,
            "encrypted": encrypted,
            "permissions": perms,
            "permission_detail": describe_permissions(perms),
            "method": str(method),
            "page_count": doc.page_count,
        }
    finally:
        doc.close()


def verify_password(src_path: str, password: str) -> bool:
    doc = pymupdf.open(src_path)
    try:
        if not doc.needs_pass:
            return True
        return bool(doc.authenticate(password))
    finally:
        doc.close()
