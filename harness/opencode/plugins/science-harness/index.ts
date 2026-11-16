// science-harness — OpenCode 플러그인 (V2 setup API + V1 server() 폴백)
//
// Claude Science 가 대화에 넣어 주는 맥락을 OpenCode 에서 재현한다.
//   prompt 훅  : 사용자 요청이 들어오면 sciharness 로 [Memory] 회상 + [skill_discovery] 계산(요청 원문은 수정하지 않음)
//   context 훅 : 매 모델 호출 직전 system 에 위 블록 + [figure_review_pending] + [frame] 을 덧붙임
//   compaction 훅 : 압축 요약이 수치·경로·id·계획 상태를 보존하도록 지시 추가
//   tool execute.after : 도구 실행을 .science/lineage.jsonl 에 기록, 직접 쓴 그림 PNG 를 미검토 목록에 추가
//
// 설정(선택): 환경변수 SCIHARNESS_PYTHON = sciharness 가 설치된 python 경로 (기본 "python")
//            opencode.jsonc  "plugins": [{ "package": "./.opencode/plugins/science-harness", "options": { "python": "..." } }]
import { execFile } from "node:child_process"
import { appendFile, mkdir, readFile, writeFile } from "node:fs/promises"
import { existsSync } from "node:fs"
import { join, resolve } from "node:path"

type Json = Record<string, any>
const latest = new Map<string, string>() // sessionID -> 마지막으로 계산한 회상/탐색 블록

function py(opts: Json): string {
  return (opts && opts.python) || process.env.SCIHARNESS_PYTHON || "python"
}

function runContext(python: string, root: string, prompt: string): Promise<Json> {
  return new Promise((ok) => {
    execFile(
      python,
      ["-m", "sciharness.hooks", "context", "--json", "--no-frame", "--root", root, "--prompt", prompt.slice(0, 4000)],
      { timeout: 20000, maxBuffer: 4 << 20, env: { ...process.env, PYTHONIOENCODING: "utf-8" }, windowsHide: true },
      (err, stdout) => {
        if (err) return ok({ text: "", error: String(err).slice(0, 300) })
        try { ok(JSON.parse(stdout)) } catch { ok({ text: "", error: "parse" }) }
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

function sid(e: Json): string {
  return e?.sessionID ?? e?.session?.id ?? e?.sessionId ?? "default"
}

function promptText(e: Json): string {
  const p = e?.prompt
  if (typeof p === "string") return p
  if (p && typeof p.text === "string") return p.text
  return ""
}

function figurePath(tool: string, input: Json): string | undefined {
  if (!/^(write|edit|patch|apply_patch)$/i.test(tool)) return
  const p = input?.filePath ?? input?.file_path ?? input?.path
  if (typeof p === "string" && p.toLowerCase().endsWith(".png") && p.split(/[\\/]/).includes("figures")) return p
}

export default {
  id: "science-harness",
  async setup(ctx: any) {
    const root: string = ctx?.location?.directory ?? process.cwd()
    const python = py(ctx?.options ?? {})

    await ctx.session.hook("prompt", async (event: Json) => {
      const text = promptText(event)
      if (!text.trim()) return
      const r = await runContext(python, root, text)
      latest.set(sid(event), r.text || "")
    })

    await ctx.session.hook("context", async (event: Json) => {
      const blocks = [latest.get(sid(event)) || "", await pendingBlock(root), await frameBlock(root)].filter(Boolean)
      if (blocks.length && Array.isArray(event.system)) {
        event.system.push({ type: "text", text: "<harness_context>\n" + blocks.join("\n\n") + "\n</harness_context>" })
      }
    })

    await ctx.session.hook("compaction", async (event: Json) => {
      if (Array.isArray(event.system)) event.system.push({ type: "text", text: COMPACTION_RULES })
    })

    await ctx.tool.hook("execute.after", async (event: Json) => {
      const tool = String(event?.tool ?? "")
      try {
        await logTool(root, { tool, status: event?.status })
        const fp = figurePath(tool, event?.input ?? {})
        if (fp && event?.status === "completed") await addPending(root, fp)
      } catch {}
    })
  },

  // ---- OpenCode V1 (1.18.29+) 폴백: 같은 동작을 V1 훅 이름으로 (V1 경로는 실기 검증 전) ----
  async server(input: Json) {
    const root: string = input?.directory ?? process.cwd()
    const python = py({})
    let last = ""
    return {
      "chat.message": async (_i: Json, output: Json) => {
        const parts: Json[] = output?.parts ?? []
        const text = parts.filter((p) => p?.type === "text").map((p) => p.text).join("\n")
        if (text.trim()) last = (await runContext(python, root, text)).text || ""
      },
      "experimental.chat.system.transform": async (_i: Json, output: Json) => {
        const blocks = [last, await pendingBlock(root), await frameBlock(root)].filter(Boolean)
        if (blocks.length && Array.isArray(output?.system)) output.system.push(blocks.join("\n\n"))
      },
      "tool.execute.after": async (i: Json, _o: Json) => {
        try { await logTool(root, { tool: i?.tool }) } catch {}
      },
    }
  },
}
