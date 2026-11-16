// science-harness — OpenCode 1.x 플러그인 (V1 훅 API, @opencode-ai/plugin 1.19.x 타입 기준)
//
// 훅 대응 (V2 플러그인과 같은 동작):
//   chat.message                         : 사용자 메시지 수신 → sciharness 로 [Memory] 회상 + [skill_discovery] 계산
//   experimental.chat.system.transform   : 매 모델 호출 직전 system(string[]) 에 회상/탐색 + [figure_review_pending] + [frame] 추가
//   experimental.session.compacting      : 압축 요약에 보존 규칙·진행 상태 추가(output.context)
//   tool.execute.after                   : 도구 실행 계보 기록, write/edit 로 만든 그림 PNG 를 미검토 목록에 추가
//
// 이 파일은 .opencode/plugins/ 에 두면 시작 시 자동 로드된다. 외부 패키지 import 없음(Bun 내장 node: 모듈만 사용).
// python 경로: 환경변수 SCIHARNESS_PYTHON (없으면 "python").
import { execFile } from "node:child_process"
import { appendFile, mkdir, readFile, writeFile } from "node:fs/promises"
import { existsSync } from "node:fs"
import { join, resolve } from "node:path"

type Json = Record<string, any>
const PY = process.env.SCIHARNESS_PYTHON || "python"
const latest = new Map<string, string>()

function runContext(root: string, prompt: string): Promise<string> {
  return new Promise((ok) => {
    execFile(
      PY,
      ["-m", "sciharness.hooks", "context", "--json", "--no-frame", "--root", root, "--prompt", prompt.slice(0, 4000)],
      { timeout: 20000, maxBuffer: 4 << 20, env: { ...process.env, PYTHONIOENCODING: "utf-8" }, windowsHide: true },
      (err, stdout) => {
        if (err) return ok("")
        try { ok(JSON.parse(stdout).text || "") } catch { ok("") }
      },
    )
  })
}

async function pendingBlock(root: string): Promise<string> {
  const f = join(root, ".science", "pending_figure_review.json")
  if (!existsSync(f)) return ""
  try {
    const list: string[] = JSON.parse(await readFile(f, "utf-8")).filter((p: string) => existsSync(p))
    if (!list.length) return ""
    const rel = list.slice(0, 10).map((p) => (p.startsWith(root) ? p.slice(root.length + 1) : p))
    return `[figure_review_pending] 저장됐지만 아직 이미지로 확인하지 않은 그림 ${list.length}개: ${rel.join(", ")}\n` +
      `→ 보고서에 넣거나 완료를 보고하기 전에 view_image 로 각 그림(패널별 크롭 포함)을 확인할 것.`
  } catch { return "" }
}

async function frameBlock(root: string): Promise<string> {
  const f = join(root, ".science", "frame.md")
  if (!existsSync(f)) return ""
  const t = (await readFile(f, "utf-8")).trim()
  return t ? `[frame] 세션 메모장(.science/frame.md) — 진행 상태:\n${t.slice(-1500)}` : ""
}

async function logTool(root: string, rec: Json) {
  const d = join(root, ".science"); await mkdir(d, { recursive: true })
  await appendFile(join(d, "lineage.jsonl"), JSON.stringify({ t: new Date().toISOString(), kind: "tool", ...rec }) + "\n", "utf-8")
}

async function addPending(root: string, p: string) {
  const f = join(root, ".science", "pending_figure_review.json")
  let list: string[] = []
  try { list = existsSync(f) ? JSON.parse(await readFile(f, "utf-8")) : [] } catch {}
  const abs = resolve(root, p)
  if (!list.includes(abs)) list.push(abs)
  await mkdir(join(root, ".science"), { recursive: true })
  await writeFile(f, JSON.stringify(list), "utf-8")
}

const COMPACTION_RULES =
  "압축 요약 규칙(science-harness): 사용자 요청과 승인된 계획(.science/plan.md 단계 상태), 확정된 수치와 그 출처 파일, " +
  "산출물 경로와 artifact id, 서브에이전트 deviations, 사용자 선호·교정 사항, 남은 단계를 빠짐없이 보존한다. " +
  "수치·식별자는 원문 그대로 옮긴다. 압축은 작업 종료가 아니다 — 요약 뒤 하던 단계를 이어간다."

export const ScienceHarness = async (input: Json) => {
  const root: string = input?.directory ?? process.cwd()
  return {
    "chat.message": async (i: Json, output: Json) => {
      const text = (output?.parts ?? []).filter((p: Json) => p?.type === "text" && !p?.synthetic).map((p: Json) => p.text).join("\n")
      if (text.trim()) latest.set(i?.sessionID ?? "default", await runContext(root, text))
    },
    "experimental.chat.system.transform": async (i: Json, output: Json) => {
      const blocks = [latest.get(i?.sessionID ?? "default") || "", await pendingBlock(root), await frameBlock(root)].filter(Boolean)
      if (blocks.length && Array.isArray(output?.system)) output.system.push("<harness_context>\n" + blocks.join("\n\n") + "\n</harness_context>")
    },
    "experimental.session.compacting": async (_i: Json, output: Json) => {
      if (Array.isArray(output?.context)) {
        output.context.push(COMPACTION_RULES)
        const extra = [await frameBlock(root), await pendingBlock(root)].filter(Boolean)
        if (extra.length) output.context.push(extra.join("\n\n"))
      }
    },
    "tool.execute.after": async (i: Json, _o: Json) => {
      try {
        const tool = String(i?.tool ?? "")
        await logTool(root, { tool, session: i?.sessionID })
        const fp = i?.args?.filePath ?? i?.args?.file_path ?? i?.args?.path
        if (/^(write|edit|apply_patch)$/i.test(tool) && typeof fp === "string" && fp.toLowerCase().endsWith(".png")
            && fp.split(/[\\/]/).includes("figures")) await addPending(root, fp)
      } catch {}
    },
  }
}
