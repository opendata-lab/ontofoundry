"""Explicit format selection; format adapters are isolated from core runtime."""


def get_adapter(adapter_id: str):
    from ontofoundry_api.adapters.native.importer import NativeAdapter
    from ontofoundry_api.adapters.ossie.importer import OssieAdapter

    if adapter_id == NativeAdapter.id:
        return NativeAdapter()
    if adapter_id in (OssieAdapter.id, "ossie"):
        return OssieAdapter()
    raise ValueError("不支持的格式适配器：" + adapter_id)
