// OpenCode Runner sidecar — Phase A isolation core.
//
// Dedicated, hardened container that owns the OpenCode CLI. The backend never
// spawns opencode itself when this runner is configured (OPENCODE_RUNNER_URL);
// it only POSTs capsule-shaped prompts here. This container:
//   - runs as a non-root user on a read-only rootfs (writes only in /tmp tmpfs)
//   - drops ALL Linux capabilities, no-new-privileges, pids/mem/cpu limited
//   - is attached to an internal compose network (no access to Postgres/Redis
//     or the backend/frontend default network)
//   - spawns the CLI as a direct argv exec (no shell), strict timeout, isolated
//     temp working dir, minimal environment allowlist
//
// Protocol:
//   POST /run {user_prompt, timeout_seconds?, master_system_prompt?} -> {status, output|reason}
//   GET  /health -> 200
//
// System-role delivery: the master system prompt is delivered as a genuine
// OpenCode agent (markdown + frontmatter with all tool permissions denied) so
// the model receives it as the system role — NOT concatenated into the user
// prompt. The agent file is baked into the read-only image at
// /app/agents/nazmos-brain.md. An optional in-band master_system_prompt is
// accepted for backward compatibility but the default is the baked agent.
import http from 'node:http';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const execFileP = promisify(execFile);
const PORT = Number(process.env.PORT || 8010);
const MAX_OUTPUT = 256 * 1024;
const AGENT_FILE = '/app/agents/nazmos-brain.md';
const AGENT_NAME = 'nazmos-brain';
const ALLOWED_PROVIDER_ENV = [
  'OPENAI_API_KEY',
  'GROQ_API_KEY',
  'GOOGLE_AI_API_KEY',
  'ANTHROPIC_API_KEY',
  'GEMINI_API_KEY',
];

// Write an agent .md into the per-project agents dir (<workdir>/.opencode/
// agents/). opencode `--agent <name>` resolves agent markdown by file name from
// that dir (project-scoped) — verified empirically (unknown agent warns "not
// found" + falls back; an agent placed here is found and used). We materialize
// it there so the master system prompt is delivered as a genuine system role,
// isolated to the throwaway temp workdir (no global config mutation).
function materializeAgent(workdir, systemPrompt) {
  const agentsDir = path.join(workdir, '.opencode', 'agents');
  fs.mkdirSync(agentsDir, { recursive: true });
  const target = path.join(agentsDir, `${AGENT_NAME}.md`);
  if (typeof systemPrompt === 'string' && systemPrompt.length > 0) {
    // Render on the fly from an in-band override (back-compat path only).
    const frontmatter = `---\ndescription: NazmOS isolated reasoning engine (system role)\nmode: primary\npermission:\n  read: deny\n  edit: deny\n  glob: deny\n  grep: deny\n  list: deny\n  bash: deny\n  webfetch: deny\n  websearch: deny\n  task: deny\n  todowrite: deny\n  lsp: deny\n  skill: deny\n  question: deny\n---\n\n`;
    fs.writeFileSync(target, frontmatter + systemPrompt);
  } else {
    fs.copyFileSync(AGENT_FILE, target);
  }
  return target;
}

function runOpenCode(userPrompt, timeoutSeconds, masterSystemPrompt) {
  const workdir = fs.mkdtempSync(path.join(os.tmpdir(), 'opencode-'));
  const bin = process.env.NAZMOS_OPENCODE_BIN || 'opencode';
  const args = ['run', '--format', 'json', '--pure'];
  if (process.env.NAZMOS_OPENCODE_MODEL) {
    args.push('--model', process.env.NAZMOS_OPENCODE_MODEL);
  }
  args.push('--agent', AGENT_NAME, userPrompt);

  materializeAgent(workdir, masterSystemPrompt);

  const env = {
    PATH: process.env.PATH || '',
    HOME: process.env.HOME || os.tmpdir(),
    NODE_ENV: 'production',
  };
  for (const key of ALLOWED_PROVIDER_ENV) {
    if (process.env[key]) env[key] = process.env[key];
  }

  return execFileP(bin, args, {
    cwd: workdir,
    env,
    timeout: Math.max(1, Math.min(Number(timeoutSeconds) || 30, 60)) * 1000,
    maxBuffer: MAX_OUTPUT,
  })
    .then(({ stdout }) => ({ status: 'ok', output: stdout.slice(0, MAX_OUTPUT) }))
    .catch((err) => {
      if (err && err.killed) {
        return { status: 'error', reason: 'timeout' };
      }
      const message = (err && err.message ? String(err.message) : String(err)).slice(0, 300);
      return { status: 'error', reason: message };
    })
    .finally(() => {
      try {
        fs.rmSync(workdir, { recursive: true, force: true });
      } catch {
        // ignore cleanup errors on read-only rootfs; tmpfs is safe
      }
    });
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    let data = '';
    req.on('data', (chunk) => {
      data += chunk;
      if (data.length > 1_000_000) req.destroy(new Error('payload too large'));
    });
    req.on('end', () => resolve(data));
    req.on('error', reject);
  });
}

const server = http.createServer(async (req, res) => {
  if (req.method === 'GET' && req.url === '/health') {
    res.writeHead(200, { 'content-type': 'application/json' });
    res.end('{"status":"ok"}');
    return;
  }
  if (req.method === 'POST' && req.url === '/run') {
    try {
      const body = JSON.parse(await readBody(req));
      const { user_prompt, timeout_seconds, master_system_prompt } = body;
      const userText = typeof user_prompt === 'string' ? user_prompt : '';
      if (!userText) {
        res.writeHead(400, { 'content-type': 'application/json' });
        res.end(JSON.stringify({ status: 'error', reason: 'user_prompt string required' }));
        return;
      }
      const result = await runOpenCode(userText, timeout_seconds, master_system_prompt);
      res.writeHead(200, { 'content-type': 'application/json' });
      res.end(JSON.stringify(result));
    } catch (err) {
      res.writeHead(400, { 'content-type': 'application/json' });
      res.end(JSON.stringify({ status: 'error', reason: String(err.message || err).slice(0, 300) }));
    }
    return;
  }
  res.writeHead(404, { 'content-type': 'application/json' });
  res.end('{"status":"error","reason":"not_found"}');
});

server.listen(PORT, '0.0.0.0', () => {
  process.stdout.write(`opencode_runner listening on 0.0.0.0:${PORT}\n`);
});