"""Native packages preserve the draft and every referenced material byte."""

import hashlib
import json
from dataclasses import replace

from ontofoundry_api.adapters.archive import read_archive, write_archive
from ontofoundry_api.adapters.documents import SourceDocument
from ontofoundry_api.adapters.exporting import ExportBuilder, file_stem, json_bytes
from ontofoundry_api.adapters.native.importer import NativeAdapter
from ontofoundry_api.domain.core import COLLECTIONS


def unpack(raw):
    files = read_archive(raw)
    manifest = SourceDocument.parse(files.pop("manifest.json")).value
    draft = SourceDocument.parse(files.pop("draft.json")).value
    if not isinstance(manifest, dict) or not isinstance(draft, dict):
        raise ValueError("完整包清单和草稿必须是对象")
    if not isinstance(manifest.get("materials"), list):
        raise ValueError("完整包清单缺少材料列表")
    if (
        manifest.get("format") != "ontofoundry"
        or manifest.get("schema_version") != "core-1"
    ):
        raise ValueError("仅支持 ontofoundry core-1 完整包")
    materials = []
    ids = set()
    for entry in manifest["materials"]:
        if (
            not isinstance(entry, dict)
            or not all(
                isinstance(entry.get(key), str) and entry[key]
                for key in ("path", "material_id", "sha256", "name")
            )
            or not isinstance(entry.get("byte_size"), int)
        ):
            raise ValueError("完整包材料清单无效")
        data = files.pop(entry["path"])
        if entry["material_id"] in ids:
            raise ValueError("材料身份重复")
        ids.add(entry["material_id"])
        if (
            hashlib.sha256(data).hexdigest() != entry["sha256"]
            or len(data) != entry["byte_size"]
        ):
            raise ValueError("完整包材料 SHA-256 或大小不匹配")
        data.decode("utf-8")
        materials.append({**entry, "data": data})
    if files:
        raise ValueError("完整包包含未声明成员")
    required = {
        evidence["material_sha256"]
        for collection in draft.values()
        if isinstance(collection, list)
        for element in collection
        if isinstance(element, dict)
        for evidence in element.get("evidence", [])
        if isinstance(evidence, dict) and evidence.get("kind") == "material"
    }
    if required - {entry["sha256"] for entry in materials}:
        raise ValueError("完整包缺少被引用材料")
    return json_bytes(
        {
            "format": "ontofoundry",
            "schema_version": "core-1",
            "exported_at": manifest["exported_at"],
            "draft": draft,
            "connection_names": manifest.get("connection_names", {}),
        }
    ), tuple(materials)


class NativePackageAdapter(NativeAdapter):
    id = "ontofoundry-core-1-package"
    label = "OntoFoundry 原生完整包"
    file_extensions = (".ontofoundry.zip", ".zip")

    def export_document(self, model, ctx):
        standalone = super().export_document(model, ctx)
        report = ExportBuilder(self.id, model)
        if standalone.document is None:
            report.report.issues.extend(standalone.report.issues)
            return report.finish(None, file_stem(ctx) + ".ontofoundry.zip")
        from .exporter import exchange_draft
        files = {"draft.json": json_bytes(exchange_draft(model))}
        materials = []
        for entry in ctx.materials or ():
            data = entry["data"]
            metadata = {key: value for key, value in entry.items() if key != "data"}
            files[metadata["path"]] = data
            materials.append(metadata)
        required = {
            e.material_sha256
            # Every collection with evidence, including ones added later (value types).
            for name in COLLECTIONS
            for element in getattr(model, name)
            for e in getattr(element, "evidence", [])
            if e.kind == "material"
        }
        if required - {m["sha256"] for m in materials}:
            report.issue("", "error", "document", None, "被引用材料缺失，无法生成完整包")
            return report.finish(None, file_stem(ctx) + ".ontofoundry.zip")
        wrapper = json.loads(standalone.document)
        files["manifest.json"] = json_bytes(
            {
                "format": "ontofoundry",
                "schema_version": "core-1",
                "exported_at": wrapper["exported_at"],
                "materials": materials,
                "connection_names": {str(k): v for k, v in (ctx.connection_names or {}).items()},
            }
        )
        report.issue(
            "", "converted", "document", None, "完整包保留核心模型及全部被引用材料"
        )
        return report.finish(
            write_archive(files), file_stem(ctx) + ".ontofoundry.zip", "application/zip"
        )

    def import_document(self, raw, ctx):
        result = super().import_document(raw, ctx)
        return replace(result, report=result.report.model_copy(update={"adapter": self.id}))
