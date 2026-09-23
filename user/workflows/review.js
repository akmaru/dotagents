// /review — SCC ③（review）の機械レビュー。reviewer の指摘を反証的に検証してから、
// 人間レビューに渡す一覧（review.json の元）を返す。他人の MR / PR にも同じ形で使う。
// 人間ノード（human-review）は main 側（docs/adr/0020）。
export const meta = {
  name: 'review',
  description: 'SCC ③: reviewer が差分を読み、指摘を反証検証で絞ってから人間レビュー用の一覧を返す',
  whenToUse: 'PR を出した後の人間レビューの前、または他人の MR / PR のレビューを頼まれたとき。args に range / ledgerDir が必須',
  phases: [
    { title: 'Review', detail: 'reviewer が決定との整合・正しさ・テストの観点で読む' },
    { title: 'Verify', detail: '止める / 直す の指摘を 1 件ずつ反証し、残ったものだけ返す' },
  ],
}

// ---- 入力 -----------------------------------------------------------------
// args = {
//   task: string,
//   range: string,           差分の範囲。例 "main...HEAD"、"origin/main..feature/x"
//   description: string,     PR / MR の説明（あれば）
//   confirmed: [{axis, choice, reason}],   決定（差分が守るべきもの）
//   adrPath: string|null,
//   ledgerDir: string,
//   verifyFindings: boolean, 反証検証を行うか（既定 true）
// }
if (!args || !args.range || !args.ledgerDir) {
  throw new Error('args.range / args.ledgerDir は必須（docs/design/workflow-graph.md「/review の入力」）')
}
const task = args.task || 'task'
const ledgerDir = args.ledgerDir
const confirmed = args.confirmed || []
const verifyFindings = args.verifyFindings !== false

const bullets = (xs, f) => (xs.length ? xs.map(x => `- ${f ? f(x) : x}`).join('\n') : '- （なし）')
const confirmedText = bullets(confirmed, c => `【確定済み】${c.axis}: ${c.choice}（${c.reason || ''}）`)
const REPORT_RULE = (path) => `報告の全文は Bash のヒアドキュメントで ${path} に書く（出力先を明示的に指定されたので、このファイルにだけ書いてよい）。最終出力には全文を載せない。`

const FINDING = {
  type: 'object',
  required: ['severity', 'file', 'line', 'what', 'fix', 'separateIssue'],
  properties: {
    severity: { type: 'string', enum: ['止める', '直す', '任意'] },
    file: { type: 'string' },
    line: { type: 'number' },
    what: { type: 'string', description: 'X の場合に Y が起きる、まで書く' },
    fix: { type: 'string' },
    separateIssue: { type: 'boolean', description: '別 issue に回すべきか' },
  },
}

// ---- Review ----------------------------------------------------------------
const reviewPath = `${ledgerDir}/review-v1.md`
const review = await agent(
  `差分の範囲: \`${args.range}\`（\`git diff ${args.range}\` と \`git log ${args.range}\` で読む）。\n` +
  `${args.description ? `\n## PR / MR の説明\n${args.description}\n` : ''}` +
  `\n## 決定（差分が守るべきもの）\n${confirmedText}\n${args.adrPath ? `ADR: ${args.adrPath}\n` : ''}` +
  `\n${REPORT_RULE(reviewPath)}`,
  { agentType: 'reviewer', phase: 'Review', label: 'review:v1',
    schema: { type: 'object', required: ['summary', 'consistency', 'items', 'testsAssessment', 'mergeOpinion', 'reportPath'], properties: {
      summary: { type: 'string' },
      consistency: { type: 'array', items: { type: 'string' }, description: '実装されていない決定 / 反する実装 / スコープ外' },
      items: { type: 'array', items: FINDING },
      testsAssessment: { type: 'string' },
      mergeOpinion: { type: 'string', enum: ['可', '指摘対応後に可', '不可'] },
      reportPath: { type: 'string' },
    } } },
)
if (!review) throw new Error('reviewer が結果を返さなかった')

// ---- Verify（反証） --------------------------------------------------------
// 止める / 直す だけを反証にかける。任意はそのまま通す（コストに見合わない）
const toVerify = review.items.filter(i => i.severity !== '任意')
const optional = review.items.filter(i => i.severity === '任意')
let kept = toVerify
let dropped = []
if (verifyFindings && toVerify.length) {
  const verdicts = await pipeline(toVerify, (f, _item, i) =>
    agent(
      `次のレビュー指摘を反証せよ。差分の範囲は \`${args.range}\`。該当箇所を実際に読み、指摘が「起きない」「既に対処されている」「差分の外の話」なら refuted=true。` +
      `迷う場合は refuted=false（人間に見せる側に倒す）。\n\n指摘: ${f.file}:${f.line} [${f.severity}] ${f.what}\n提案された直し方: ${f.fix}`,
      { phase: 'Verify', label: `verify:${i + 1}`,
        schema: { type: 'object', required: ['refuted', 'reason'], properties: { refuted: { type: 'boolean' }, reason: { type: 'string' } } } },
    ).then(v => ({ f, v })),
  )
  kept = []
  for (const r of verdicts.filter(Boolean)) {
    if (r.v && r.v.refuted) dropped.push({ ...r.f, refutedBecause: r.v.reason })
    else kept.push(r.f)
  }
  const missing = verdicts.length - verdicts.filter(Boolean).length
  if (missing) log(`Verify: ${missing} 件の反証エージェントが結果を返さなかった。該当の指摘はそのまま残す`)
  if (dropped.length) log(`Verify: ${dropped.length} 件の指摘を反証で落とした（詳細は戻り値 dropped）`)
}

return {
  task,
  range: args.range,
  summary: review.summary,
  consistency: review.consistency,
  items: [...kept, ...optional].map(f => ({ ...f, status: 'open' })),
  dropped,
  testsAssessment: review.testsAssessment,
  mergeOpinion: review.mergeOpinion,
  reportPath: review.reportPath,
}
