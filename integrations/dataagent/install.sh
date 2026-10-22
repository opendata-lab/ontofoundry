#!/bin/sh
# Install only self-contained skills; external registration remains an admin task.
set -eu
PACKAGE_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
: "${SKILLS_ROOT_DIR:?请设置 SKILLS_ROOT_DIR 为 DataAgent 技能根目录}"

validate_skill() {
    skill_dir=$1
    for file in SKILL.md output-schema.json requirements.txt LICENSE NOTICE PROVENANCE.md \
        references/core-model.md references/principles.md references/quick-reference.md \
        references/examples/protocol/entities.json references/extract-kit/01.json \
        scripts/init_workflow.py scripts/read_input.py scripts/show_element.py \
        scripts/show_example.py scripts/check_part.py scripts/check_result.py scripts/prepare_result.py \
        scripts/runpaths.py references/steps/finish.md; do
        [ -f "$skill_dir/$file" ] || { echo "缺少文件：$skill_dir/$file" >&2; exit 1; }
    done
    [ ! -e "$skill_dir/tests" ] && [ ! -e "$skill_dir/scripts/offline_budget.py" ] || {
        echo "技能包误含测试或离线预算：$skill_dir" >&2; exit 1;
    }
}

for skill in ontology-discovery entity-extraction semantic-grounding; do
    validate_skill "$PACKAGE_ROOT/skills/$skill"
done
for file in ontology-discovery/references/steps/plan.md ontology-discovery/references/steps/extract.md \
    ontology-discovery/references/steps/incremental.md ontology-discovery/references/steps/optimize.md \
    ontology-discovery/references/extract-tables.md \
    entity-extraction/references/steps/facts.md entity-extraction/references/extract-facts.md \
    semantic-grounding/references/steps/ground.md semantic-grounding/references/steps/answer.md; do
    [ -f "$PACKAGE_ROOT/skills/$file" ] || { echo "缺少专属方法：$file" >&2; exit 1; }
done
mkdir -p "$SKILLS_ROOT_DIR"
for skill in ontology-discovery entity-extraction semantic-grounding; do
    # Merge copies keep installation limited to the three named skill directories.
    mkdir -p "$SKILLS_ROOT_DIR/$skill"
    cp -R "$PACKAGE_ROOT/skills/$skill/." "$SKILLS_ROOT_DIR/$skill/"
    validate_skill "$SKILLS_ROOT_DIR/$skill"
    echo "已安装：$SKILLS_ROOT_DIR/$skill"
done
cat <<'STEPS'
管理员后续步骤（脚本不连接后台、不重启、不删除旧技能）：
1. 按 plugin.json 登记 OntoFoundry MCP 与授权凭据，核对五个已上线工具（含 resolve_entity）。
2. 已有 agent_ontofoundry 挂载 ontology-discovery、entity-extraction，max_turns=40；已有 agent_ontofoundry_qa 挂载 semantic-grounding。
3. 从 agents/*.md 复制“系统提示词：”后的正文，同步并发布两个已有 Agent。不要把配置说明粘入系统正文。
4. 停止旧运行后停用并移走旧 ontofoundry-modeling 目录，安排重启并检查三技能能力目录。
5. 按迁移说明.md 在新会话验收；真实 DeepSeek 运行前另行确认预算。
STEPS
