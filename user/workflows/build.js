// /build — SCC ②（build）の implement ⇄ verify ループを、全 pass か離脱条件まで回す。
// 人間ノード（human-op）はワークフロー内に置けないので、特権操作が要ると分かった時点で
// needs_human_op を返して止まる。戻り値が verify.json の元になる（docs/adr/0020）。
export const meta = {
  name: 'build',
  description: 'SCC ②: implement → verify を、全 pass か「同一原因 2 回 / ベンチ未達」の離脱まで回す',
  whenToUse: '決定（ADR）が出た後、この worktree で実装と検証を回すとき。args に decision / checks / ledgerDir が必須',
  phases: [
    { title: 'Implement', detail: 'この worktree で決定どおりに実装する（commit はしない）' },
    { title: 'Verify', detail: 'verifier が検証項目を実行し、fail の原因を実装 / 設計の前提で分類する' },
  ],
}

// ---- 入力 -----------------------------------------------------------------
// args = {
//   task: string,
//   decision: string,        何をどう実装するか（決定の要約）
//   adrPath: string|null,    決定を記録した ADR の絶対パス
//   checks: [{name, kind: 'test'|'build'|'bench'|'startup', command, target}],
//   ledgerDir: string,       報告と台帳の置き場（絶対パス）
//   prevCause: string|null,  前回の /build で最後に fail した原因（周を跨いだ同一原因の判定用）
//   notes: string,           実装者への補足
//   maxRounds: number,       backstop（既定 6）。離脱条件は回数ではなく再発
//   models: {implement, verify}, ノードごとのモデル上書き（undefined = セッション継承）
// }
// 役割ファイルの model: は tests/test_user_config.py が禁止しているので（ADR 0014）、呼び出しごとに指定する
const MODELS = {
  implement: 'sonnet',   // 決定どおりに書く作業。判断は ① で済んでいる
  verify: 'sonnet',      // コマンド実行と原因の分類
  ...(args && args.models ? args.models : {}),
}
if (!args || !args.decision || !args.checks || !args.ledgerDir) {
  throw new Error('args.decision / args.checks / args.ledgerDir は必須（docs/design/workflow-graph.md「/build の入力」）')
}
const task = args.task || 'task'
const ledgerDir = args.ledgerDir
const checks = args.checks
const maxRounds = args.maxRounds || 6
const SAME_CAUSE_LIMIT = 2

const bullets = (xs, f) => (xs.length ? xs.map(x => `- ${f ? f(x) : x}`).join('\n') : '- （なし）')
const checksText = bullets(checks, c => `${c.name}（${c.kind}）: \`${c.command}\`${c.target ? ` 目標: ${c.target}` : ''}`)
const REPORT_RULE = (path) => `報告の全文は Bash のヒアドキュメントで ${path} に書く（出力先を明示的に指定されたので、このファイルにだけ書いてよい）。最終出力には全文を載せない。`

const HUMAN_OP = { type: ['object', 'null'], required: ['command', 'reason'], properties: { command: { type: 'string' }, reason: { type: 'string' } } }
const VERIFY_ITEM = {
  type: 'object',
  required: ['name', 'kind', 'result', 'cause', 'layer', 'sameAsPrev', 'flaky'],
  properties: {
    name: { type: 'string' },
    kind: { type: 'string', enum: ['test', 'build', 'bench', 'startup'] },
    result: { type: 'string', enum: ['pass', 'fail', 'skipped'] },
    cause: { type: 'string', description: 'fail の原因（pass なら空文字）' },
    layer: { type: 'string', enum: ['implementation', 'design-premise', 'unknown', 'n/a'] },
    sameAsPrev: { type: 'boolean', description: '前回の原因と同じか' },
    flaky: { type: 'boolean' },
  },
}

let lastVerify = null
let lastCause = args.prevCause || null
let sameCauseCount = 0
let status = 'backstop'
let needsHumanOp = null
const reports = []
let round = 0

for (round = 1; round <= maxRounds; round++) {
  // ---- Implement ----
  const implPath = `${ledgerDir}/implement-r${round}.md`
  const prevText = lastVerify
    ? `\n\n## 前回の検証結果（fail を直す）\n${bullets(lastVerify.items.filter(i => i.result !== 'pass'), i => `${i.name}: ${i.cause}（層: ${i.layer}）`)}\n報告: ${lastVerify.reportPath}`
    : ''
  const impl = await agent(
    `この作業ツリー（git worktree）で、次の決定どおりに実装する。commit / push はしない。\n\n## 決定\n${args.decision}\n` +
    `${args.adrPath ? `\n決定の記録（ADR）: ${args.adrPath}\n` : ''}${args.notes ? `\n## 補足\n${args.notes}\n` : ''}` +
    `\n## 通すべき検証項目\n${checksText}${prevText}\n\n` +
    `ルール: 要求された範囲だけを変える。認証・デプロイ・課金・対話が要る操作（特権操作）に当たったら実行せず、needsHumanOp にコマンドと理由を入れて止まる。` +
    `テストを追加・修正した場合はその理由を報告に書く。${REPORT_RULE(implPath)}`,
    { phase: 'Implement', label: `implement:r${round}`, model: MODELS.implement,
      schema: { type: 'object', required: ['summary', 'filesChanged', 'needsHumanOp', 'reportPath'], properties: {
        summary: { type: 'string', description: '何をどう変えたか 3〜5 行' },
        filesChanged: { type: 'array', items: { type: 'string' } },
        needsHumanOp: HUMAN_OP,
        reportPath: { type: 'string' },
      } } },
  )
  if (!impl) { status = 'implementer-failed'; break }
  reports.push(impl.reportPath)
  if (impl.needsHumanOp) { status = 'needs_human_op'; needsHumanOp = impl.needsHumanOp; break }

  // ---- Verify ----
  const verifyPath = `${ledgerDir}/verify-r${round}.md`
  const verify = await agent(
    `検証項目を実行し、結果と原因を報告する。\n\n## 検証項目\n${checksText}\n\n` +
    `## 直前の実装の要約\n${impl.summary}\n変更ファイル: ${impl.filesChanged.join(', ') || '（報告なし）'}\n\n` +
    `## 前回の失敗原因（同じ原因かどうかを必ず判定する）\n${lastCause || '（なし）'}\n\n${REPORT_RULE(verifyPath)}`,
    { agentType: 'verifier', phase: 'Verify', label: `verify:r${round}`, model: MODELS.verify,
      schema: { type: 'object', required: ['items', 'escape', 'humanOp', 'treeChanged', 'reportPath'], properties: {
        items: { type: 'array', items: VERIFY_ITEM },
        escape: { type: 'string', enum: ['continue', 'deliberate'], description: '離脱の推奨' },
        humanOp: HUMAN_OP,
        treeChanged: { type: 'boolean', description: '起動前後で git status に差が出たか' },
        reportPath: { type: 'string' },
      } } },
  )
  if (!verify) { status = 'verifier-failed'; break }
  reports.push(verify.reportPath)
  lastVerify = verify
  if (verify.treeChanged) log(`Verify r${round}: verifier の実行で作業ツリーに差分が出た（報告 ${verify.reportPath}）`)
  if (verify.humanOp) { status = 'needs_human_op'; needsHumanOp = verify.humanOp; break }

  const failing = verify.items.filter(i => i.result !== 'pass')
  if (failing.length === 0) { status = 'pass'; break }

  // ---- 離脱条件（回数ではなく再発） ----
  if (failing.some(i => i.kind === 'bench')) { status = 'escape_deliberate'; log('ベンチ未達。性能は設計の帰結なので ① に戻す'); break }
  const cause = failing.map(i => `${i.name}: ${i.cause}`).sort().join(' | ')
  const repeated = failing.some(i => i.sameAsPrev) || (lastCause !== null && cause === lastCause)
  sameCauseCount = repeated ? sameCauseCount + 1 : 0
  lastCause = cause
  if (sameCauseCount >= SAME_CAUSE_LIMIT || verify.escape === 'deliberate' || failing.some(i => i.layer === 'design-premise')) {
    status = 'escape_deliberate'
    log(`同一原因の再発 ${sameCauseCount} 回 / 層=${failing.map(i => i.layer).join(',')}。① に戻す`)
    break
  }
  log(`Verify r${round}: fail ${failing.length} 件。implement に戻す`)
}
if (status === 'backstop') log(`implement ⇄ verify が backstop ${maxRounds} 周に達した。fail を残したまま返す`)

return {
  task,
  status,
  rounds: Math.min(round, maxRounds),
  items: lastVerify ? lastVerify.items : checks.map(c => ({ name: c.name, kind: c.kind, result: 'skipped', cause: '未実行', layer: 'n/a', sameAsPrev: false, flaky: false })),
  sameCauseCount,
  lastCause,
  needsHumanOp,
  reports,
}
