import { readFileSync } from "node:fs"
import { homedir } from "node:os"
import { isAbsolute, join, resolve } from "node:path"

const HOME = homedir()
const GIT_ENV_FILE = join(HOME, ".local/share/agent-config/git-env.json")
const PROTECTED_PATHS = [".codex", ".claude", ".claude.json", ".claudex", ".local/bin/claudex", ".config/dcg-claudex"].map(
  (p) => `${HOME}/${p}`,
)

const MUTATING_SHELL = /(?:^|[;&|]\s*)(?:rm|mv|cp|install|chmod|chown|touch|mkdir|ln|tee|sed\s+-i|perl\s+-i)\b|(?:^|[^<])>{1,2}/
const BROAD_GIT_STAGE = /\bgit(?:\s+-C\s+\S+)?\s+add\b[^;&|]*\s(?:-A|--all|\.)(?=\s|$)/
const COMMIT_ALL = /\bgit(?:\s+-C\s+\S+)?\s+commit\b[^;&|]*\s-(?!-)[A-Za-z]*a[A-Za-z]*(?=\s|$)/
const FILE_TOOLS = new Set(["write", "edit", "patch", "apply_patch"])

function gitEnv(): Record<string, string> {
  try {
    return JSON.parse(readFileSync(GIT_ENV_FILE, "utf8"))
  } catch {
    return {}
  }
}

function mentionsProtectedPath(value: unknown, cwd: string) {
  const serialized = (JSON.stringify(value) ?? "")
    .replaceAll("${HOME}/", `${HOME}/`)
    .replaceAll("$HOME/", `${HOME}/`)
    .replaceAll("~/", `${HOME}/`)
  if (PROTECTED_PATHS.some((path) => serialized.includes(path))) return true
  const target = (value as { path?: unknown; filePath?: unknown } | undefined)?.path ?? (value as any)?.filePath
  if (typeof target !== "string" || isAbsolute(target)) return false
  const abs = resolve(cwd, target)
  return PROTECTED_PATHS.some((path) => abs === path || abs.startsWith(`${path}/`))
}

export default {
  id: "workflow-guard",
  setup: async (ctx: any) => {
    const cwd: string = ctx.location.directory

    await ctx.shell.hook("create.before", (input: { env: Record<string, string | undefined> }) => {
      Object.assign(input.env, gitEnv())
    })

    await ctx.tool.hook("execute.before", (input: { tool: string; input: any }) => {
      if (FILE_TOOLS.has(input.tool) && mentionsProtectedPath(input.input, cwd)) {
        throw new Error("Native Codex and Claude configuration is read-only in OpenCode")
      }
      if (input.tool !== "shell") return
      const command = String(input.input?.command ?? "")
      if (BROAD_GIT_STAGE.test(command) || COMMIT_ALL.test(command)) {
        throw new Error("Broad git staging is disabled; stage explicit paths")
      }
      if (mentionsProtectedPath(command, cwd) && MUTATING_SHELL.test(command)) {
        throw new Error("Native Codex and Claude configuration is read-only in OpenCode")
      }
    })
  },
}
