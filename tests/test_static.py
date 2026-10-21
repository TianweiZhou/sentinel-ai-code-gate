from sentinel.stages import static


def test_detects_hallucinated_stdlib_api() -> None:
    issues = static.imports("from statistics import weighted_mean\n", [])
    assert [i.rule for i in issues] == ["hallucinated-api"]
    assert issues[0].severity == "critical"


def test_detects_hallucinated_attribute_call() -> None:
    issues = static.imports("import json\njson.parse('{}')\n", [])
    assert any(i.rule == "hallucinated-api" and "json.parse" in i.message for i in issues)


def test_detects_nonexistent_package() -> None:
    issues = static.imports("import fastjsonvalidatorx\n", [])
    assert issues[0].rule == "hallucinated-package"


def test_installed_but_unapproved_package_is_flagged() -> None:
    issues = static.imports("import pydantic\n", [])
    assert issues[0].rule == "unapproved-dependency"
    assert static.imports("import pydantic\n", ["pydantic"]) == []


def test_stdlib_imports_are_clean() -> None:
    assert static.imports("import os\nfrom collections import defaultdict\nos.getcwd()\n", []) == []


def test_complexity_flags_deep_nesting() -> None:
    code = "def f(a: int) -> int:\n" + "".join(
        "    " * (d + 1) + f"if a > {d}:\n" for d in range(5)
    ) + "    " * 6 + "return a\n    return 0\n"
    issues, functions, _ = static.complexity(code)
    assert functions[0].max_depth == 5
    assert {i.rule for i in issues} >= {"nesting"}


def test_parse_reports_line_of_syntax_error() -> None:
    issues = static.parse("def f(:\n    pass\n")
    assert issues[0].rule == "syntax-error" and issues[0].line == 1
