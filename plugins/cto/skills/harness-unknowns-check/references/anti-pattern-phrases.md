# Anti-pattern phrases

The phrases in this file are the surface signal of hallucination
inside a teammate's draft. They sound like normal professional
writing — which is exactly why they slip past self-review. Each is
a way of saying "I don't actually know, so I'm going to write the
most-common-in-training-data answer with confident phrasing."

## The four canonical phrases

```
"assume the user wants ..."
"typical pattern is ..."
"standard convention says ..."
"the framework usually ..."
```

`scripts/scan_for_hallucination_phrases.sh` matches these as exact
substrings (case-insensitive). If the scanner exits non-zero on your
spec, do not try to soften the phrasing — convert to an unknown.

## Why each is dangerous

### "assume the user wants ..."

The literal admission: you are about to encode an assumption as if
it were a requirement. The user did not say it; you are filling in.

```markdown
❌ "Assume the user wants email confirmation before login."
✅ ## Unknowns
   - [ ] should signup require email confirmation before first
         login? — relay to user
```

This is the most honest of the four phrases — it actually says
"assume" — and the easiest to catch in your own writing. If you
catch yourself writing it, you have already identified the unknown;
just promote it.

### "typical pattern is ..."

Sounds like wisdom; is actually generalization. "Typical for whom?"
Typical for the training data — which is mostly tutorials and toy
examples, not your specific user's project. The pattern that is
typical in tutorials is often wrong for production code with real
constraints.

```markdown
❌ "The typical pattern is to store the JWT in localStorage."
✅ ## Unknowns
   - [ ] JWT storage strategy (localStorage / httpOnly cookie /
         memory + refresh) — relay to user; affects XSS surface
```

### "standard convention says ..."

The most authoritative-sounding and therefore most dangerous. A
"convention" is whatever the model can pattern-match in its training
data — which may or may not be what the user's stack, team, or
domain actually uses.

```markdown
❌ "Standard convention says REST endpoints should be plural nouns."
✅ ## Unknowns
   - [ ] REST endpoint naming convention (plural / singular /
         resource-action) — read existing routes if any, else
         relay to user
```

If there really is a standard convention for the user's context,
you can self-answer and emit a `<decision>` block. The trap is invoking
"convention" without first checking that the user's project follows
it.

### "the framework usually ..."

Generalization about behavior, often wrong because frameworks have
versions, configurations, and ecosystem quirks. "Next.js usually
does X" is true for the default template, false for any non-trivial
deployment.

```markdown
❌ "Next.js usually handles session cookies in middleware."
✅ ## Unknowns
   - [ ] session cookie handling location (middleware / API route
         / edge function) — read next.config.js, else relay
```

## Phrases the scanner does NOT catch (yet)

The scanner only matches the four canonical phrases. There are
near-synonyms that produce the same hallucination signal:

- "a common approach is ..."
- "best practice is ..."
- "we'll likely want ..."
- "it makes sense to ..."
- "the conventional choice is ..."
- "in most cases ..."
- "should probably ..."

Treat these as hand-flagged anti-patterns. The scanner is a
backstop, not a substitute for reading your own draft. When you
catch a near-synonym, the same rule applies: convert to an unknown
with a resolution path.

The scanner deliberately does not match these because false
positives ("a common approach is to" can appear in legitimate
explanatory prose) would make it noisy and ignored. Keeping it
tight on the four canonical phrases keeps it useful.

## Conversion recipe

For any anti-pattern phrase you catch:

1. **Identify the assumption.** What were you about to assert? Say
   it out loud as a flat declarative ("the user wants email
   confirmation").
2. **Check the goal.** Is the answer in the original user goal? If
   yes, self-answer and emit a `<decision>` block instead of listing as
   unknown (per Gotcha #5 in SKILL.md).
3. **Pick a resolution path.** If you can read a file, do. If a
   teammate owns it, ask. Otherwise relay.
4. **Add to `## Unknowns`.** One-line description + resolution path,
   markdown checkbox format.
5. **Re-read your draft.** Did you have multiple anti-pattern
   phrases? They often cluster — one missing fact produces three
   surface symptoms.

## Cross-document sweep (the `--cross-check` mode)

When you resolve an unknown in `spec.md`, the same underlying
question may appear in `design.md` or `review.md` for the same spec
slug. Running the scanner with `--cross-check <spec-dir>` (see the
script) checks all four files in a spec dir and reports any
anti-pattern phrase that appears in more than one — those are the
likely candidates for cross-doc sync.

Example: "typical pattern is to use JWT" appears in `spec.md` and
"the framework usually handles JWT in middleware" appears in
`design.md`. Both flagged. Resolving the spec one without sweeping
design leaves design with a stale assumption.

## When the phrase IS appropriate

There are legitimate uses of these phrases — none of them belong in
a spec doc.

- Documentation of an external library's behavior (`"the next-auth
  framework usually handles session cookies in middleware"` —
  factual claim about a third-party tool, not about your project).
- Comparison sections explaining alternatives the user could pick
  (`"option A: typical pattern is X, option B: typical pattern is
  Y"`).
- Retrospective writing about how the build went after the fact.

In a `specs/` document at planning time, none of
these uses are common. If the scanner flags one and you believe
it's legitimate, leave a one-line comment in the doc explaining
why, so the next reviewer doesn't have to re-litigate.
