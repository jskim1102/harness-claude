export const meta = {
  name: 'harness-audit',
  description: 'Read-only SEMANTIC audit of the harness-claude project. 결정론 검사는 ./run.sh doctor + smoke 가 선행 담당 — 이 워크플로우는 의미 수준만. Six parallel perspective agents (canon-consistency 포함) inspect plugins/, hooks/, harness/, run.sh, docs/. Findings classified KEEP/SHRINK/MOVE/SPLIT/CONVERT/DELETE; adversarial reviewer challenges destructive recommendations (감사 false-positive 62% 교훈 — 검증 필수).',
  phases: [
    { title: 'Inventory', detail: 'list every harness-owned file + size' },
    { title: 'Analyze',   detail: '5 parallel perspective agents' },
    { title: 'Plan',      detail: 'classify each finding KEEP/SHRINK/MOVE/SPLIT/CONVERT/DELETE' },
    { title: 'Adversarial', detail: 'challenge every DELETE/SHRINK to prevent regressions' },
    { title: 'Report',    detail: 'write markdown report to ~/.harness-claude/audits/' },
  ],
}

// Repo root is supplied by the invoking command (harness-audit.md) via args.repo
// so the audit works on any clone. Workflow scripts run sandboxed — no __dirname/env.
const REPO = (args && args.repo) || (typeof args === 'string' ? args : null)
if (!REPO) throw new Error('harness-audit: args.repo (absolute harness root) is required')

const FINDING_SCHEMA = {
  type: 'object',
  required: ['findings'],
  properties: {
    findings: {
      type: 'array',
      items: {
        type: 'object',
        required: ['path', 'issue', 'evidence'],
        properties: {
          path:      { type: 'string', description: 'file path relative to repo root' },
          issue:     { type: 'string', description: 'one-line problem statement' },
          evidence:  { type: 'string', description: 'concrete excerpt or count' },
          severity:  { type: 'string', enum: ['low', 'medium', 'high'] },
        },
      },
    },
  },
}

const CLASSIFIED_SCHEMA = {
  type: 'object',
  required: ['classified'],
  properties: {
    classified: {
      type: 'array',
      items: {
        type: 'object',
        required: ['path', 'issue', 'recommendation', 'rationale'],
        properties: {
          path:           { type: 'string' },
          issue:          { type: 'string' },
          recommendation: { type: 'string', enum: ['KEEP', 'SHRINK', 'MOVE', 'SPLIT', 'CONVERT', 'DELETE'] },
          rationale:      { type: 'string' },
          target:         { type: 'string', description: 'destination for MOVE/CONVERT, optional otherwise' },
          risk:           { type: 'string', enum: ['low', 'medium', 'high'] },
        },
      },
    },
  },
}

const ADVERSARIAL_SCHEMA = {
  type: 'object',
  required: ['verdicts'],
  properties: {
    verdicts: {
      type: 'array',
      items: {
        type: 'object',
        required: ['path', 'original_recommendation', 'survives', 'reason'],
        properties: {
          path:                   { type: 'string' },
          original_recommendation:{ type: 'string' },
          survives:               { type: 'boolean', description: 'true = recommendation holds. false = refuted, keep file' },
          reason:                 { type: 'string' },
          downgrade_to:           { type: 'string', enum: ['KEEP', 'SHRINK', 'MOVE', 'SPLIT', 'CONVERT', 'DELETE'], description: 'safer alternative when survives=false' },
        },
      },
    },
  },
}

phase('Inventory')
const inventory = await agent(
  `Read-only inventory of the harness-claude project at ${REPO}.
List every file under: plugins/, hooks/, harness/, docs/. Also include
top-level files: run.sh, README.md, CLAUDE.md (if present).
For each file emit: path (relative), size_lines, role (e.g. role.md, slash-command, agent-def, rule, skill, hook, daemon, doc).
Use Bash + Read. Return as plain text — no schema.`,
  { label: 'inventory' }
)

phase('Analyze')
const analyses = await parallel([
  () => agent(
    `Context-Tax Agent. Audit at ${REPO}.
Target files: plugins/ceo/role.md, plugins/cto/role.md, plugins/cto/rules/*, README.md.
These get auto-injected into every claude session = pay token tax forever.
Find: (a) duplicated guidance between CEO/CTO role.md, (b) prose-style examples that could move to Skill on-demand, (c) "general best practice" lines that claude code already knows, (d) any rule > 5 lines that could compress.
Report each finding with file:line range + the redundant text excerpt.
Use Read + Grep.

Inventory context:
${JSON.stringify(inventory).slice(0, 4000)}`,
    { label: 'analyze:context-tax', phase: 'Analyze', schema: FINDING_SCHEMA }
  ),

  () => agent(
    `Skill-Quality Agent. Audit at ${REPO}.
Target: plugins/cto/skills/*/SKILL.md.
For each skill check: (a) description specific enough to trigger correctly? (b) SKILL.md body < 250 lines? (c) when-NOT-to-use section present? (d) reference/examples extractable to separate files?
Use Read + Glob.`,
    { label: 'analyze:skill-quality', phase: 'Analyze', schema: FINDING_SCHEMA }
  ),

  () => agent(
    `Product-Overlap Agent. Audit at ${REPO}.
Target: plugins/ceo/commands/*, plugins/cto/commands/*, plugins/cto/agents/*, plugins/cto/skills/*.
For each item ask: does claude code v2.1.160+ ship a default that already does this? E.g. /memory, /quit, /clear, MCP-based messaging, Agent Teams native sub-agents.
Flag items that duplicate native functionality.
Use Read + WebFetch (claude code docs site).`,
    { label: 'analyze:product-overlap', phase: 'Analyze', schema: FINDING_SCHEMA }
  ),

  () => agent(
    `Safety-Permission Agent. Audit at ${REPO}.
Target: run.sh write_role_settings (CEO + CTO settings.json templates), hooks/*.
Find: (a) allow lists that grant too-broad Bash patterns, (b) dangerouslySkip flags without container isolation, (c) hooks that exit 0 silently on error (hide failure), (d) missing defense-in-depth where bypass mode is on.
Use Read.`,
    { label: 'analyze:safety-permission', phase: 'Analyze', schema: FINDING_SCHEMA }
  ),

  () => agent(
    `Hook-Convert Agent. Audit at ${REPO}.
Target: plugins/ceo/role.md, plugins/cto/role.md, plugins/cto/rules/*.
Look for prose rules that are DETERMINISTIC — "always do X before Y" — and could be enforced by a Hook instead (UserPromptSubmit / PreToolUse / SessionStart / TaskCompleted etc).
Hook conversion wins: rule never violated, role.md shrinks, model token saved.
List each candidate with: rule excerpt + suggested hook type + one-line implementation sketch.
Use Read + Grep.`,
    { label: 'analyze:hook-convert', phase: 'Analyze', schema: FINDING_SCHEMA }
  ),

  () => agent(
    `Canon-Consistency Agent. Audit at ${REPO}.
설계 정본 = ${REPO}/plans/harness.md (먼저 정독). 운영 추출본 = plugins/_shared/PROCESS.md, 하드룰 = plugins/_shared/RULES.md.
Target: plugins/ 전체 + hooks/ + harness/*.py + run.sh.
Find SEMANTIC drift the deterministic doctor grep cannot catch:
(a) 정본과 모순되는 활성 지시 (예: 잘못된 phase 의미의 예시, 폐기 흐름을 가르치는 field manual),
(b) 문서 간 상호참조 불일치 (§번호, 파일 경로, 스킬 이름),
(c) 에이전트 4종(planner/designer/developer/reviewer)·spawn-prompt·PROCESS 간 핸드오프 가정 어긋남,
(d) 형식 규약 불일치 ([F<n>]/← F<n>/[supplied:]/specs/ 경로).
2026-06-12 리뷰에서 버그 17건 중 11건이 이 계급이었다 — 참조망 2~3차 문서까지 파라.
Use Read + Grep.`,
    { label: 'analyze:canon-consistency', phase: 'Analyze', schema: FINDING_SCHEMA }
  ),
])

const allFindings = analyses.filter(Boolean).flatMap(r => r.findings || [])

phase('Plan')
const plan = await agent(
  `Refactor Planner. Below is a JSON array of findings from 5 perspective agents.
Classify each finding into exactly ONE: KEEP, SHRINK, MOVE, SPLIT, CONVERT, DELETE.
Definitions:
- KEEP   = leave as-is. Explain why the finding is wrong or low-impact.
- SHRINK = same role, fewer lines. Cut redundancy.
- MOVE   = same content, different location (e.g. role.md → Skill, role.md → Hook).
- SPLIT  = one file → two+ (e.g. long SKILL.md → SKILL.md + reference.md + examples.md).
- CONVERT= different mechanism (e.g. prose rule → deterministic Hook).
- DELETE = remove entirely. Function gone or already covered by claude code defaults.

For each: include target if MOVE/CONVERT, and a risk rating (low/medium/high).

Findings:
${JSON.stringify(allFindings)}`,
  { label: 'plan:refactor', phase: 'Plan', schema: CLASSIFIED_SCHEMA }
)

phase('Adversarial')
const destructive = (plan?.classified || []).filter(
  c => c.recommendation === 'DELETE' || c.recommendation === 'SHRINK' || c.recommendation === 'CONVERT'
)
const verdicts = destructive.length === 0
  ? []
  : await parallel(destructive.map(c => () =>
      agent(
        `Adversarial Reviewer. Default to refuting.
Try to find a reason this recommendation is UNSAFE, would lose information, or break a workflow:

  path: ${c.path}
  issue: ${c.issue}
  recommendation: ${c.recommendation}
  rationale: ${c.rationale}
  risk: ${c.risk}

If the recommendation has merit AND no real downside, survives=true.
If there's any plausible downside (lost guardrail, used by external script, semantic shift), survives=false and propose a safer downgrade_to.`,
        { label: `adversarial:${c.path.slice(0, 40)}`, phase: 'Adversarial', schema: ADVERSARIAL_SCHEMA }
      ).then(v => ({ ...c, verdicts: v?.verdicts || [] }))
    ))

phase('Report')
const timestamp = (args && args.timestamp) || 'pending'
const report = {
  meta: {
    workflow: 'harness-audit',
    repo: REPO,
    generated_at: timestamp,
  },
  inventory_summary: String(inventory).slice(0, 2000),
  findings_by_perspective: analyses.filter(Boolean).map((r, i) => ({
    perspective: ['context-tax', 'skill-quality', 'product-overlap', 'safety-permission', 'hook-convert', 'canon-consistency'][i],
    findings: r.findings || [],
  })),
  classified: plan?.classified || [],
  adversarial_verdicts: verdicts.filter(Boolean).flatMap(v => v.verdicts || []),
  counts: {
    findings: allFindings.length,
    KEEP:    (plan?.classified || []).filter(c => c.recommendation === 'KEEP').length,
    SHRINK:  (plan?.classified || []).filter(c => c.recommendation === 'SHRINK').length,
    MOVE:    (plan?.classified || []).filter(c => c.recommendation === 'MOVE').length,
    SPLIT:   (plan?.classified || []).filter(c => c.recommendation === 'SPLIT').length,
    CONVERT: (plan?.classified || []).filter(c => c.recommendation === 'CONVERT').length,
    DELETE:  (plan?.classified || []).filter(c => c.recommendation === 'DELETE').length,
  },
}

log(`harness-audit complete: ${report.counts.findings} findings, ${report.counts.DELETE} DELETE / ${report.counts.SHRINK} SHRINK / ${report.counts.CONVERT} CONVERT.`)
log(`Recommend writing report to ~/.harness-claude/audits/harness-audit-<date>.md from the returned object.`)

return report
