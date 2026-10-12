import { AppState, Platform } from "react-native";
import {
  CommandStateResponse,
  SendCommandResponse,
  TakeCommandsResponse,
  type DeviceCommand,
  type DeviceKind,
  type ToolName,
} from "@bekhi/contracts";
import { apiBaseUrl } from "@/services/assistant/connect";
import type { ActionOutcome } from "@/services/ios-actions/IOSActionService";
import { syncHeaders } from "./identity";

/**
 * Commands between the user's devices linked with one sync code (apps/api commands.py): said to
 * the phone, the computer does it ("компьютерийн дууг багасга"), and the other way round
 * ("ээж рүү залга" said to the computer rings from the phone).
 */

/** Seconds the API holds one request open while waiting (long polling). */
const WAIT_S = 20;
/** The other device has this long to do it before the reply says it did not answer. */
const ANSWER_WITHIN_MS = 45_000;

const failed = (error_code: string): ActionOutcome => ({ status: "failed", executed_via: null, error_code });
const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

async function call(path: string, init: { method?: string; body?: unknown; waitS?: number } = {}): Promise<unknown> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), ((init.waitS ?? 0) + 10) * 1000);
  try {
    const res = await fetch(apiBaseUrl() + path, {
      method: init.method ?? "GET",
      headers: { ...syncHeaders(), ...(init.body !== undefined ? { "content-type": "application/json" } : {}) },
      body: init.body !== undefined ? JSON.stringify(init.body) : undefined,
      signal: controller.signal,
    });
    if (!res.ok) throw new Error(`${path} answered ${res.status}`);
    return await res.json();
  } finally {
    clearTimeout(timer);
  }
}

/** Has the user's other device do it, and returns what that device reports (data.device says which). */
export async function sendToDevice(target: DeviceKind, tool: ToolName, args: unknown): Promise<ActionOutcome> {
  const silent = target === "computer" ? "COMPUTER_NO_ANSWER" : "PHONE_NO_ANSWER";
  try {
    const { id } = SendCommandResponse.parse(
      await call("/api/v1/sync/commands", { method: "POST", body: { target, tool, arguments: args } }),
    );
    if (!id) return { status: "unsupported", executed_via: null, error_code: target === "computer" ? "NO_COMPUTER" : "NO_PHONE" };
    const until = Date.now() + ANSWER_WITHIN_MS;
    while (Date.now() < until) {
      const { state, outcome } = CommandStateResponse.parse(
        await call(`/api/v1/sync/commands/${id}?wait=${WAIT_S}`, { waitS: WAIT_S }),
      );
      if (state === "done" && outcome) return { ...outcome, data: { ...outcome.data, device: target } };
      if (state === "expired") break;
    }
    return failed(silent);
  } catch (e) {
    console.warn("command failed", e);
    return failed(silent);
  }
}

let listening = false;

/**
 * Phones: while BEKHI is open, does what the user's computer asks of the phone. `run` performs it
 * as one of the phone's own actions; its outcome goes back to the computer.
 */
export function listenForCommands(run: (command: DeviceCommand) => Promise<ActionOutcome>): void {
  if (listening || Platform.OS === "web") return; // the computer's commands are run by its API (desktop.py)
  listening = true;
  void (async () => {
    for (;;) {
      if (AppState.currentState !== "active") {
        await sleep(1000);
        continue;
      }
      try {
        const { commands } = TakeCommandsResponse.parse(
          await call(`/api/v1/sync/commands?target=phone&wait=${WAIT_S}`, { waitS: WAIT_S }),
        );
        for (const command of commands) {
          const outcome = await run(command).catch(() => failed("COMMAND_FAILED"));
          await call(`/api/v1/sync/commands/${command.id}/result`, { method: "POST", body: outcome }).catch((e: unknown) =>
            console.warn("command result failed", e),
          );
        }
      } catch {
        await sleep(5000); // offline, or an API without commands yet
      }
    }
  })();
}
