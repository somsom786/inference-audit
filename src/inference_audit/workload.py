"""Precompute reproducible synthetic transactions and evaluate bounded task checks."""

import ast
from dataclasses import asdict, dataclass
import json
import random
import re
from typing import Any

from .config import Config, Stage


@dataclass(frozen=True)
class Task:
    id: str
    family: str
    messages: list[dict[str, Any]]
    check: str
    expected: str | int
    max_output: int
    cache: bool | None = None

    @property
    def steps(self) -> int:
        return 2 if self.check in {"tool", "warm_receipt"} else 1


def manifest(config: Config, stage: Stage) -> list[Task]:
    rng = random.Random(f"{config.seed}:{stage.fixture_set}")
    mix = ("chat",) * 8 + ("coding",) * 5 + ("rag",) * 5 + ("agent",) * 2
    deck: list[str] = []
    tasks = []
    for i in range(stage.count):
        if not deck:
            deck = list(mix)
            rng.shuffle(deck)
        family = deck.pop() if stage.pattern in {"mixed", "burst"} else stage.pattern
        key = f"{stage.name}-{i:05d}"
        value = f"R{rng.getrandbits(48):012X}"
        expected: str | int = value
        check, cap = "receipt", stage.max_output
        cache = None
        if family in {"cold", "warm", "rag"}:
            records = [
                f"Ticket {rng.randint(100000, 999999)} from district {rng.randrange(99)} contains routine details."
                for _ in range(rng.randrange(38, 150))
            ]
            records.insert(rng.randrange(len(records)), f"The approved case receipt is {value}.")
            prompt = f"Reference {i}.\n" + "\n".join(records) + "\nReply with just the approved case receipt."
            cap = min(cap, 32)
            cache = family == "warm" if family != "rag" else None
            if family == "warm":
                check = "warm_receipt"
            family = "rag"
        elif family == "coding":
            n = rng.randint(100, 999)
            prompt = f"Case {value}. Return only Python defining a zero-argument function named answer that returns the integer {n}."
            check, expected = "code", n
        elif family == "agent":
            prompt = f"Case {value}. Use the lookup_receipt tool for case {value}, then answer with only its result."
            check = "tool"
        elif i % 7 == 1 and family == "chat":
            a, b = rng.randint(40, 999), rng.randint(40, 999)
            prompt = f"Case {value}. What is {a} + {b}? Return only the integer."
            check, expected = "math", a + b
        elif i % 7 == 2 and family == "chat":
            prompt = f"Produce a JSON object with one key receipt having the string value {value}. Output only JSON."
            check = "json"
        else:
            prompt = (
                f"Begin with reference {value}. Write a practical {rng.randrange(45, 100)}-word note about "
                f"{rng.choice(['incident response', 'inventory', 'tenant migration'])}. Include a check and a rollback action."
            )
        tasks.append(
            Task(
                key,
                family if family not in {"decode", "concurrent"} else "chat",
                [{"role": "user", "content": prompt}],
                check,
                expected,
                cap,
                cache,
            )
        )
    return tasks


def planned(config: Config) -> dict[str, list[Task]]:
    result = {s.name: manifest(config, s) for s in config.stages}
    if sum(t.steps for tasks in result.values() for t in tasks) > config.max_requests:
        raise ValueError("The precomputed request plan exceeds the HTTP request budget.")
    return result


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "lookup_receipt",
            "description": "Get the verified synthetic receipt.",
            "parameters": {
                "type": "object",
                "properties": {"case": {"type": "string"}},
                "required": ["case"],
                "additionalProperties": False,
            },
        },
    }
]


def clean_code(output: str) -> str:
    block = re.fullmatch(r"```(?:python)?\s*\n(.*?)```\s*", output, re.S)
    return block[1] if block else output


def check_answer(task: Task, output: str, check: str | None = None) -> bool:
    mode = check or task.check
    stripped = output.strip()
    sequence = stripped.split()
    if not stripped or (
        len(sequence) >= 24
        and (
            len(set(sequence)) <= 2
            or any(
                sequence[-width * 6 :] == sequence[-width:] * 6
                for width in range(2, 9)
                if len(sequence) >= width * 6
            )
        )
    ):
        return False
    try:
        if mode == "json":
            return json.loads(stripped) == {"receipt": task.expected}
        if mode == "math":
            return stripped == str(task.expected)
        if mode == "code":
            tree = ast.parse(clean_code(stripped))
            if len(tree.body) != 1 or not isinstance(func := tree.body[0], ast.FunctionDef):
                return False
            args = func.args
            return (
                func.name == "answer"
                and not func.decorator_list
                and not (args.args or args.posonlyargs or args.kwonlyargs or args.vararg or args.kwarg)
                and len(func.body) == 1
                and isinstance(result := func.body[0], ast.Return)
                and isinstance(result.value, ast.Constant)
                and type(result.value.value) is int
                and result.value.value == task.expected
            )
        if task.family in {"rag", "agent"} and mode in {"receipt", "warm_receipt"}:
            return stripped == str(task.expected)
        return bool(
            re.search(r"(?<![A-Za-z0-9])" + re.escape(str(task.expected)) + r"(?![A-Za-z0-9])", stripped)
        )
    except (ValueError, SyntaxError, RecursionError):
        return False


def task_record(task: Task) -> dict[str, Any]:
    return asdict(task)
