"""Bounded in-memory exchange archives; members are never extracted to disk."""

from io import BytesIO
from pathlib import PurePosixPath
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile, ZipInfo

MAX_EXPANDED_BYTES = 64 * 1024 * 1024


def read_archive(raw):
    try:
        with ZipFile(BytesIO(raw)) as archive:
            members = archive.infolist()
            if (
                len(members) > 1000
                or sum(m.file_size for m in members) > MAX_EXPANDED_BYTES
            ):
                raise ValueError("压缩包解压后超过限制")
            names = [m.filename for m in members]
            if len(names) != len(set(names)):
                raise ValueError("压缩包包含重复文件名")
            if any(
                m.is_dir()
                or m.flag_bits & 1
                or "\\" in m.filename
                or PurePosixPath(m.filename).is_absolute()
                or ".." in PurePosixPath(m.filename).parts
                for m in members
            ):
                raise ValueError("压缩包包含非法文件路径或加密成员")
            return {m.filename: archive.read(m) for m in members}
    except (BadZipFile, RuntimeError, OSError, NotImplementedError) as error:
        raise ValueError("压缩包无法读取") from error


def write_archive(files):
    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        for name, raw in sorted(files.items()):
            info = ZipInfo(name, date_time=(2026, 10, 20, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            archive.writestr(info, raw)
    return output.getvalue()


def read_ossie(raw):
    if not raw.startswith(b"PK"):
        return raw, None
    files = read_archive(raw)
    extension = files.pop("ontofoundry-extension.json", None)
    if extension is None or len(files) != 1 or not next(iter(files)).endswith(".json"):
        raise ValueError("Ossie 压缩包须包含一份 Ossie JSON 和 ontofoundry-extension.json")
    return next(iter(files.values())), extension
