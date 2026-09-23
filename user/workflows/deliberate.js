// /deliberate — SCC ①（deliberate）の機械部分を、人間の decide の手前まで 1 周回す。
// research（事実が足りない小問だけ）→ design → critique → 致命的指摘が残れば designer を呼び直す。
// 戻り値が decisions.json の元になる。人間ノードは main 側（docs/adr/0020, docs/design/workflow-graph.md）。
export const meta = {
  name: 'deliberate',
  description: 'SCC ①: research → design → critique を回し、人間が決められる状態（未確定行）を返す',
  whenToUse: '調査・設計が要るタスクで、人間の decide の前に案と反対意見を揃えるとき。args に goal / ledgerDir が必須',
  phases: [
    { title: 'Research', detail: '事実が足りない小問だけ researcher で埋める' },
    { title: 'Design', detail: 'designer が代替案・推奨・未決事項を出す' },
    { title: 'Critique', detail: 'critic が反対の立場で検証。致命的が残れば designer を呼び直す' },
  ],
}

// ---- 入力 -----------------------------------------------------------------
// args = {
//   task: string,            台帳ディレクトリ名（ログ用）
//   goal: string,            何を決めたいか
//   constraints: string[],   制約
//   confirmed: [{axis, choice, reason}],           確定済み（再オープン禁止）
//   open: [{axis, question, options}],             前回の未確定行（2 周目以降）
//   reports: string[],       先行する報告の絶対パス
//   researchQuestions: string[],  事実が足りない小問（無ければ Research を飛ばす）
//   ledgerDir: string,       報告と台帳の置き場（絶対パス）
//   maxRounds: number,       design ⇄ critique の周回数の上限（既定 2。空転は別に検知する）
// }
if (!args || !args.goal || !args.ledgerDir) {
  throw new Error('args.goal と args.ledgerDir は必須（docs/design/workflow-graph.md「/deliberate の入力」）')
}
const task = args.task || 'task'
const ledgerDir = args.ledgerDir
const maxRounds = args.maxRounds || 2
const constraints = args.constraints || []
const confirmed = args.confirmed || []
const priorOpen = args.open || []
const reports = [...(args.reports || [])]

const bullets = (xs, f) => (xs.length ? xs.map(x => `- ${f ? f(x) : x}`).join('\n') : '- （なし）')
const confirmedText = bullets(confirmed, c => `【確定済み】${c.axis}: ${c.choice}（${c.reason || '理由の記載なし'}）`)
const openText = bullets(priorOpen, o => `${o.axis}: ${o.question}（選択肢: ${(o.options || []).join(' / ')}）`)
const reportsText = () => bullets(reports, p => `絶対パス: ${p}`)

const OPEN_ITEM = {
  type: 'object',
  required: ['axis', 'question', 'options'],
  properties: {
    axis: { type: 'string', description: '判断軸の短い名前' },
    question: { type: 'string', description: 'ユーザーに聞く質問' },
    options: { type: 'array', items: { type: 'string' }, description: '選択肢 2〜4 個' },
  },
}
const REPORT_RULE = (path) => `報告の全文は Bash のヒアドキュメントで ${path} に書く（出力先を明示的に指定されたので、このファイルにだけ書いてよい）。最終出力（StructuredOutput）には全文を載せず、要約と reportPath を返す。`

// ---- Research --------------------------------------------------------------
const questions = args.researchQuestions || []
if (questions.length) {
  log(`Research: ${questions.length} 件の小問を researcher で埋める`)
  const results = await pipeline(questions, (q, _item, i) => {
    const path = `${ledgerDir}/research-${i + 1}.md`
    return agent(
      `目的: 「${args.goal}」を決めるための事実集め。あなたに割り当てられた小問は 1 つ。\n\n` +
      `## 小問\n${q}\n\n## 制約\n${bullets(constraints)}\n\n## 確定済み事項（これらは前提。再検討しない）\n${confirmedText}\n\n` +
      `## 先行する報告\n${reportsText()}\n\n${REPORT_RULE(path)}`,
      { agentType: 'researcher', phase: 'Research', label: `research:${i + 1}`,
        schema: { type: 'object', required: ['summary', 'open', 'reportPath'], properties: {
          summary: { type: 'string', description: '結論の要約 3〜5 行' },
          open: { type: 'array', items: OPEN_ITEM, description: '報告末尾の未決事項' },
          reportPath: { type: 'string' },
        } } },
    )
  })
  for (const r of results.filter(Boolean)) reports.push(r.reportPath)
  const dropped = results.length - results.filter(Boolean).length
  if (dropped) log(`Research: ${dropped} 件のエージェントが結果を返さなかった（停止または API エラー）`)
}

// ---- Design ⇄ Critique -----------------------------------------------------
let design = null
let critique = null
let prevFatalKey = null
let stoppedBecause = 'max-rounds'
let round = 0

for (round = 1; round <= maxRounds; round++) {
  const designPath = `${ledgerDir}/design-v${round}.md`
  const critiquePath = `${ledgerDir}/critique-v${round}.md`
  const revision = critique
    ? `\n\n## 前回の批評（必ず読み、致命的な指摘に答える）\n絶対パス: ${critique.reportPath}\n致命的: ${bullets(critique.fatal, f => f.title)}\n重要: ${bullets(critique.important, f => f.title)}`
    : ''

  design = await agent(
    `目的（ゴール）: ${args.goal}\n\n## 制約\n${bullets(constraints)}\n\n## 確定済み事項（前提として扱う。再オープンしない）\n${confirmedText}\n\n` +
    `## 前回までの未決事項（今回の案で答えるか、未決のまま引き継ぐ）\n${openText}\n\n## 先行する報告\n${reportsText()}${revision}\n\n` +
    `これは第 ${round} 版。${REPORT_RULE(designPath)}`,
    { agentType: 'designer', phase: 'Design', label: `design:v${round}`,
      schema: { type: 'object', required: ['options', 'recommendation', 'open', 'reportPath'], properties: {
        options: { type: 'array', items: { type: 'object', required: ['name', 'summary'], properties: {
          name: { type: 'string' }, summary: { type: 'string', description: 'Good / Bad を 2〜3 行で' } } } },
        recommendation: { type: 'string', description: '推奨案と根拠（3 行以内）' },
        open: { type: 'array', items: OPEN_ITEM, description: '報告末尾の未決事項' },
        reportPath: { type: 'string' },
      } } },
  )
  if (!design) { stoppedBecause = 'designer-failed'; break }
  reports.push(design.reportPath)

  critique = await agent(
    `批評対象: 設計報告（絶対パス: ${design.reportPath}）。目的は「${args.goal}」。\n\n## 確定済み事項（覆さない。食い違いは食い違いとして指摘する）\n${confirmedText}\n\n` +
    `## 参照できる先行報告\n${reportsText()}\n\n${REPORT_RULE(critiquePath)}`,
    { agentType: 'critic', phase: 'Critique', label: `critique:v${round}`,
      schema: { type: 'object', required: ['fatal', 'important', 'minorCount', 'acceptableIf', 'open', 'reportPath'], properties: {
        fatal: { type: 'array', items: { type: 'object', required: ['title', 'summary'], properties: { title: { type: 'string' }, summary: { type: 'string' } } }, description: '採用を覆す指摘。無ければ空配列' },
        important: { type: 'array', items: { type: 'object', required: ['title', 'summary'], properties: { title: { type: 'string' }, summary: { type: 'string' } } } },
        minorCount: { type: 'number' },
        acceptableIf: { type: 'string', description: 'それでも採用してよい条件' },
        open: { type: 'array', items: OPEN_ITEM },
        reportPath: { type: 'string' },
      } } },
  )
  if (!critique) { stoppedBecause = 'critic-failed'; break }
  reports.push(critique.reportPath)

  if (critique.fatal.length === 0) { stoppedBecause = 'critic-accepted'; break }
  // 同じ致命的指摘が丸ごと残る周は空転（同じものの再発）。回数ではなくここで止める
  const fatalKey = critique.fatal.map(f => f.title).sort().join('|')
  if (fatalKey === prevFatalKey) { stoppedBecause = 'no-progress'; break }
  prevFatalKey = fatalKey
  log(`Critique v${round}: 致命的 ${critique.fatal.length} 件。designer を呼び直す`)
}
if (stoppedBecause === 'max-rounds') log(`design ⇄ critique が上限 ${maxRounds} 周に達した（backstop）。致命的指摘が残ったまま返す`)

// ---- 台帳（decisions.json の元） --------------------------------------------
const mergedOpen = []
const seenAxis = new Set()
for (const o of [...(design ? design.open : []), ...(critique ? critique.open : [])]) {
  if (seenAxis.has(o.axis)) continue
  seenAxis.add(o.axis)
  mergedOpen.push(o)
}

return {
  task,
  rounds: Math.min(round, maxRounds),
  stoppedBecause,
  confirmed,
  open: mergedOpen,
  recommendation: design ? design.recommendation : null,
  options: design ? design.options : [],
  fatalRemaining: critique ? critique.fatal : [],
  acceptableIf: critique ? critique.acceptableIf : null,
  reports,
}
