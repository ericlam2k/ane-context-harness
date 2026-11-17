import type { Plugin } from "@opencode-ai/plugin";
import { appendFile, mkdir } from "node:fs/promises";
import { homedir } from "node:os";
import { join } from "node:path";

type UsageMessage = {
  id?: string;
  sessionID?: string;
  role?: string;
  time?: { completed?: number };
  tokens?: { input?: number; cache?: { read?: number; write?: number } };
  providerID?: string;
  modelID?: string;
};

const isCount = (value: unknown): value is number =>
  typeof value === "number" && Number.isSafeInteger(value) && value >= 0;

const AneHarnessUsage: Plugin = async ({ client }) => {
  const seen = new Set<string>();
  const pendingIDs = new Set<string>();
  const pendingWrites = new Map<string, Promise<boolean>[]>();
  const bySession = new Map<string, { inputTokens: number; replies: number }>();
  return {
    event: async ({ event }) => {
      if (process.env.ANE_HARNESS_NO_USAGE_LOG) return;
      if (event.type === "session.idle") {
        const sessionID = event.properties.sessionID;
        await Promise.all(pendingWrites.get(sessionID) ?? []);
        const total = bySession.get(sessionID);
        if (!total) return;
        bySession.delete(sessionID);
        try {
          await client.tui.showToast({ body: {
            title: "Tokens sent",
            message: `This task sent ${total.inputTokens.toLocaleString()} tokens (small pieces of text) to the AI across ${total.replies} replies.`,
            variant: "info",
            duration: 7000,
          } });
        } catch {
          // Usage is already saved. A closed TUI must not affect the task.
        }
        return;
      }
      if (event.type !== "message.updated") return;
      const properties = event.properties as { info?: UsageMessage; sessionID?: string };
      const message = properties.info;
      const sessionID = message?.sessionID ?? properties.sessionID;
      if (!message || !message.id || !sessionID || message.role !== "assistant" || !message.time?.completed) return;

      const input = message.tokens?.input;
      const cacheRead = message.tokens?.cache?.read ?? 0;
      const cacheWrite = message.tokens?.cache?.write ?? 0;
      if (!isCount(input) || !isCount(cacheRead) || !isCount(cacheWrite)) return;

      const id = `opencode:${sessionID}:${message.id}`;
      if (seen.has(id) || pendingIDs.has(id)) return;
      pendingIDs.add(id);

      const dir = join(homedir(), ".ane_context_harness");
      const entry = {
        ts: Math.floor(Date.now() / 1000), kind: "actual", measurement_id: id,
        source: "opencode", input_tokens: input + cacheRead + cacheWrite,
        model: [message.providerID, message.modelID].filter(Boolean).join("/"),
      };
      const write = (async () => {
        try {
          await mkdir(dir, { recursive: true });
          await appendFile(join(dir, "usage.jsonl"), `${JSON.stringify(entry)}\n`);
          return true;
        } catch {
          // Keep OpenCode running if the local usage ledger is unavailable.
          return false;
        }
      })();
      const sessionWrites = pendingWrites.get(sessionID) ?? [];
      sessionWrites.push(write);
      pendingWrites.set(sessionID, sessionWrites);
      if (await write) {
        seen.add(id);
        const total = bySession.get(sessionID) ?? { inputTokens: 0, replies: 0 };
        total.inputTokens += input + cacheRead + cacheWrite;
        total.replies += 1;
        bySession.set(sessionID, total);
      }
      pendingIDs.delete(id);
      const remaining = sessionWrites.filter((pending) => pending !== write);
      if (remaining.length) pendingWrites.set(sessionID, remaining);
      else pendingWrites.delete(sessionID);
    },
  };
};

export default AneHarnessUsage;
