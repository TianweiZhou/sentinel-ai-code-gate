# Team conventions (read by Claude Code, Codex and the Sentinel reviewer)

- **Money is `Decimal`, never `float`.** Round with `quantize(Decimal("0.01"), ROUND_HALF_UP)`.
- **SQL is always parameterised** (`?` placeholders). Never build SQL with f-strings or `+`.
- Domain errors subclass `shop.errors.ShopError`. Don't raise bare `Exception` or `ValueError` from public APIs.
- Public functions are fully type-annotated and stay under 40 lines.
- Every acceptance criterion in the issue gets at least one test tagged `@pytest.mark.req("ACn")`.
- **Never delete, skip or loosen an existing test to make CI pass.** If a test is wrong, say so in the PR.
- No new third-party dependency without approval in the issue.
