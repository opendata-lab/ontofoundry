"""Guards which HTTP handlers may sit on the event loop.

FastAPI runs an ``async def`` handler *on the event loop* and a plain ``def``
handler in a threadpool. A handler that only does blocking work — psycopg has no
async driver here, and bcrypt is CPU-bound — must therefore be ``def``, or it
freezes the whole process for its duration, including every open SSE chat
stream.

This is not hypothetical. Before the fix, ``api/admin_routes.py`` had 35
handlers declared ``async def`` that never awaited anything; loading the Skill
settings page serialized against every other request in flight.

The rule is derived rather than listed: a handler is genuinely async only if its
own body contains ``await`` / ``yield`` / ``async for`` / ``async with``. Nested
function bodies do not count, because their awaits belong to the inner scope. An
allowlist of handler names would have to be edited every time a route is added;
this check maintains itself.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

import dataagent_backend

from conftest import PACKAGE_ROOT

# 合并之后这条约束必须覆盖同一进程里的每一个路由模块：一个长任务占住事件
# 循环，拖慢的不再只是 DataAgent 自己的请求，而是包括本体编辑在内的所有请求。
ROUTE_MODULES = [
    PACKAGE_ROOT / "api" / "admin_routes.py",
    PACKAGE_ROOT / "api" / "routes.py",
    PACKAGE_ROOT / "api" / "auth_routes.py",
] + sorted(
    f
    for f in (PACKAGE_ROOT.parent / "ontofoundry_api" / "api").glob("*.py")
    if f.name != "__init__.py"  # 包标记文件，不承载路由
)


def _decorator_names(node: ast.AsyncFunctionDef) -> list[str]:
    names = []
    for decorator in node.decorator_list:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        names.append(ast.unparse(target))
    return names


def _is_route_handler(node: ast.AsyncFunctionDef) -> bool:
    return any("router." in name for name in _decorator_names(node))


def _awaits_anything(node: ast.AsyncFunctionDef) -> bool:
    for child in ast.walk(node):
        if child is not node and isinstance(child, (ast.AsyncFunctionDef, ast.FunctionDef)):
            continue
        if isinstance(child, (ast.Await, ast.Yield, ast.YieldFrom, ast.AsyncFor, ast.AsyncWith)):
            return True
    return False


@pytest.mark.parametrize("relative_path", ROUTE_MODULES, ids=lambda p: Path(p).name)
def test_route_handlers_that_never_await_are_not_declared_async(relative_path: str):
    tree = ast.parse(Path(relative_path).read_text(encoding="utf-8"))

    offenders = [
        f"{node.name} (:{node.lineno})"
        for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef)
        and _is_route_handler(node)
        and not _awaits_anything(node)
    ]

    assert not offenders, (
        f"{relative_path} 中以下路由处理器声明为 async def 却从不 await，"
        "会直接占用事件循环，应改为 def 交给 FastAPI 线程池：\n  "
        + "\n  ".join(offenders)
    )


@pytest.mark.parametrize("relative_path", ROUTE_MODULES, ids=lambda p: Path(p).name)
def test_the_contract_still_sees_route_handlers(relative_path: str):
    """Fail loudly if the decorator convention changes and the check goes blind.

    A check that silently matches nothing always passes, which is worse than
    having no check at all.
    """
    tree = ast.parse(Path(relative_path).read_text(encoding="utf-8"))

    handlers = [
        node
        for node in tree.body
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef))
        and any(
            "router." in ast.unparse(d.func if isinstance(d, ast.Call) else d)
            for d in node.decorator_list
        )
    ]

    assert handlers, f"{relative_path} 中没有解析到任何路由处理器，装饰器约定可能变了"
