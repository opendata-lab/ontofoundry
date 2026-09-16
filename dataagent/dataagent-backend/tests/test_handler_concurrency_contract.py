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

BACKEND_ROOT = Path(__file__).resolve().parents[1]

ROUTE_MODULES = [
    "api/admin_routes.py",
]


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


@pytest.mark.parametrize("relative_path", ROUTE_MODULES)
def test_route_handlers_that_never_await_are_not_declared_async(relative_path: str):
    module_path = BACKEND_ROOT / relative_path
    tree = ast.parse(module_path.read_text(encoding="utf-8"))

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


@pytest.mark.parametrize("relative_path", ROUTE_MODULES)
def test_the_contract_still_sees_route_handlers(relative_path: str):
    """Fail loudly if the decorator convention changes and the check goes blind.

    A check that silently matches nothing always passes, which is worse than
    having no check at all.
    """
    module_path = BACKEND_ROOT / relative_path
    tree = ast.parse(module_path.read_text(encoding="utf-8"))

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
