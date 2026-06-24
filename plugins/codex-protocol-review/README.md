# codex-protocol-review

`codex-protocol-review` is a CEO-level, cross-model audit for the
`harness-claude` protocol itself. It invokes the local `codex` CLI with a
GPT-5-family model, reviews the instruction authority surfaces and their
enforcers in read-only mode, writes a structured report to a harness-side path,
and sends a short summary to `ceo`.

Use it through the CEO slash command:

```bash
/codex-protocol-review
```

When the inbox summary arrives, consume the pending marker before trusting it:

```bash
/codex-protocol-review --consume
```

Codex remains outside the CTO build loop. Findings are advisory until the user
explicitly chooses a remediation path.
