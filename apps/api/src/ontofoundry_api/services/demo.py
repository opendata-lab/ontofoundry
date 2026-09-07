from uuid import UUID

from ontofoundry_api.domain.models import (
    AttributeDefinition,
    LinkTypeDefinition,
    Multiplicity,
    ObjectTypeDefinition,
    OntologyDraft,
    ValueKind,
)

DEMO_WORKSPACE_ID = UUID("10375c4d-64e2-4ddf-a6e6-f3fc36d23001")
SUPPLIER_ID = UUID("10375c4d-64e2-4ddf-a6e6-f3fc36d23101")
MATERIAL_ID = UUID("10375c4d-64e2-4ddf-a6e6-f3fc36d23102")
BATCH_ID = UUID("10375c4d-64e2-4ddf-a6e6-f3fc36d23103")
PERSON_ID = UUID("10375c4d-64e2-4ddf-a6e6-f3fc36d23104")
EQUIPMENT_ID = UUID("10375c4d-64e2-4ddf-a6e6-f3fc36d23105")


def _attribute(
    value: str,
    name: str,
    technical_name: str,
    *,
    identifier: bool = False,
    value_kind: ValueKind = ValueKind.STRING,
) -> AttributeDefinition:
    return AttributeDefinition(
        id=UUID(value),
        name=name,
        technical_name=technical_name,
        identifier=identifier,
        required=identifier,
        value_kind=value_kind,
    )


def build_demo_draft() -> OntologyDraft:
    object_types = [
        ObjectTypeDefinition(
            id=SUPPLIER_ID,
            name="供应商",
            technical_name="supplier",
            description="向企业提供物料或服务的组织。",
            tags=["采购", "供应链"],
            attributes=[
                _attribute(
                    "10375c4d-64e2-4ddf-a6e6-f3fc36d23201",
                    "供应商编码",
                    "supplier_code",
                    identifier=True,
                ),
                _attribute(
                    "10375c4d-64e2-4ddf-a6e6-f3fc36d23202",
                    "供应商名称",
                    "supplier_name",
                ),
                _attribute(
                    "10375c4d-64e2-4ddf-a6e6-f3fc36d23203",
                    "供应商等级",
                    "supplier_grade",
                ),
            ],
        ),
        ObjectTypeDefinition(
            id=MATERIAL_ID,
            name="物料",
            technical_name="material",
            description="采购、生产与库存环节管理的物料。",
            tags=["采购", "生产"],
            attributes=[
                _attribute(
                    "10375c4d-64e2-4ddf-a6e6-f3fc36d23211",
                    "物料编码",
                    "material_code",
                    identifier=True,
                ),
                _attribute(
                    "10375c4d-64e2-4ddf-a6e6-f3fc36d23212",
                    "物料名称",
                    "material_name",
                ),
                _attribute(
                    "10375c4d-64e2-4ddf-a6e6-f3fc36d23213",
                    "标准成本",
                    "standard_cost",
                    value_kind=ValueKind.DECIMAL,
                ),
            ],
        ),
        ObjectTypeDefinition(
            id=BATCH_ID,
            name="产品批次",
            technical_name="product_batch",
            description="生产过程形成并可追溯的一组产品。",
            tags=["生产", "质量"],
            attributes=[
                _attribute(
                    "10375c4d-64e2-4ddf-a6e6-f3fc36d23221",
                    "批次编号",
                    "batch_code",
                    identifier=True,
                ),
                _attribute(
                    "10375c4d-64e2-4ddf-a6e6-f3fc36d23222",
                    "生产日期",
                    "production_date",
                    value_kind=ValueKind.DATE,
                ),
            ],
        ),
        ObjectTypeDefinition(
            id=PERSON_ID,
            name="人员",
            technical_name="person",
            description="参与业务活动的企业员工或外部人员。",
            tags=["组织"],
            attributes=[
                _attribute(
                    "10375c4d-64e2-4ddf-a6e6-f3fc36d23231",
                    "人员编号",
                    "person_code",
                    identifier=True,
                ),
                _attribute(
                    "10375c4d-64e2-4ddf-a6e6-f3fc36d23232",
                    "姓名",
                    "person_name",
                ),
            ],
        ),
        ObjectTypeDefinition(
            id=EQUIPMENT_ID,
            name="设备",
            technical_name="equipment",
            description="参与生产、检测或仓储作业的设备。",
            tags=["生产", "设备"],
            attributes=[
                _attribute(
                    "10375c4d-64e2-4ddf-a6e6-f3fc36d23241",
                    "设备编号",
                    "equipment_code",
                    identifier=True,
                ),
                _attribute(
                    "10375c4d-64e2-4ddf-a6e6-f3fc36d23242",
                    "设备名称",
                    "equipment_name",
                ),
            ],
        ),
    ]
    link_types = [
        LinkTypeDefinition(
            id=UUID("10375c4d-64e2-4ddf-a6e6-f3fc36d23301"),
            name="提供",
            technical_name="supplies",
            source_type_id=SUPPLIER_ID,
            target_type_id=MATERIAL_ID,
            multiplicity=Multiplicity.MANY_TO_MANY,
            description="供应商向企业提供物料。",
            tags=["采购"],
        ),
        LinkTypeDefinition(
            id=UUID("10375c4d-64e2-4ddf-a6e6-f3fc36d23302"),
            name="使用",
            technical_name="uses_material",
            source_type_id=BATCH_ID,
            target_type_id=MATERIAL_ID,
            multiplicity=Multiplicity.MANY_TO_MANY,
            description="产品批次在生产中使用物料。",
            tags=["生产"],
        ),
        LinkTypeDefinition(
            id=UUID("10375c4d-64e2-4ddf-a6e6-f3fc36d23303"),
            name="负责人",
            technical_name="owned_by",
            source_type_id=EQUIPMENT_ID,
            target_type_id=PERSON_ID,
            multiplicity=Multiplicity.MANY_TO_ONE,
            description="设备由指定人员负责。",
            tags=["设备"],
        ),
        LinkTypeDefinition(
            id=UUID("10375c4d-64e2-4ddf-a6e6-f3fc36d23304"),
            name="生产于",
            technical_name="produced_on",
            source_type_id=BATCH_ID,
            target_type_id=EQUIPMENT_ID,
            multiplicity=Multiplicity.MANY_TO_ONE,
            description="产品批次由设备生产。",
            tags=["生产"],
        ),
    ]
    return OntologyDraft(
        workspace_id=DEMO_WORKSPACE_ID,
        object_types=object_types,
        link_types=link_types,
    )
