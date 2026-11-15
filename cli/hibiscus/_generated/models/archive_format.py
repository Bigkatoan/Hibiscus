from enum import Enum


class ArchiveFormat(str, Enum):
    RAR = "rar"
    TAR = "tar"
    TAR_GZ = "tar.gz"
    TAR_ZST = "tar.zst"
    ZIP = "zip"

    def __str__(self) -> str:
        return str(self.value)
