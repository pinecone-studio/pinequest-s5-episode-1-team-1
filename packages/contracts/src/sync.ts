import { z } from "zod";
import { ActionStatus } from "./actions";
import { IsoDateTime, Uuid } from "./common";
import { ExecutionTarget, ToolName } from "./tools";

/**
 * Alarms and timers shared by every device linked with one sync code.
 *
 * Every request carries two headers:
 * - X-Bekhi-Sync:   the sync code (shown on the first device, typed on the others). The server
 *                   stores only its SHA-256, so the code itself never reaches the database.
 * - X-Bekhi-Device: a random id per device install.
 *
 * Each device pulls the list and schedules its own local copy ahead of time, so it rings
 * even if the network is gone at that moment. It only has to be online once after the
 * alarm was created.
 */
export const SYNC_CODE_HEADER = "X-Bekhi-Sync";
export const SYNC_DEVICE_HEADER = "X-Bekhi-Device";

/** 12 characters of Crockford base32 (60 bits), shown as "ABCD-EFGH-JKMN". */
export const SYNC_CODE_LENGTH = 12;
export const SYNC_CODE_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ";

export const SyncPlatform = z.enum(["ios", "android", "web"]);
export type SyncPlatform = z.infer<typeof SyncPlatform>;

export const SyncAlarmKind = z.enum(["alarm", "timer"]);
export type SyncAlarmKind = z.infer<typeof SyncAlarmKind>;

export const SyncAlarm = z.object({
  id: Uuid,
  kind: SyncAlarmKind,
  title: z.string().min(1).max(100),
  fire_at: IsoDateTime,
});
export type SyncAlarm = z.infer<typeof SyncAlarm>;

/** POST /api/v1/sync/devices — "I am here" (also refreshes last_seen). */
export const SyncDeviceRequest = z.object({ platform: SyncPlatform });

/** POST /api/v1/sync/alarms — publish one alarm/timer this device has just scheduled. */
export const SyncPublishRequest = SyncAlarm;

/** The other linked devices, for an honest reply ("компьютер руу бас илгээлээ"). */
export const SyncPublishResponse = z.object({ other_devices: z.array(SyncPlatform) });
export type SyncPublishResponse = z.infer<typeof SyncPublishResponse>;

/** POST /api/v1/sync/alarms/cancel */
export const SyncCancelRequest = z.object({ ids: z.array(Uuid).min(1).max(50) });

/** GET /api/v1/sync/alarms — what is still to come, and what was cancelled (to drop local copies). */
export const SyncPullResponse = z.object({
  active: z.array(SyncAlarm),
  cancelled: z.array(Uuid),
});
export type SyncPullResponse = z.infer<typeof SyncPullResponse>;

/**
 * Commands between the user's linked devices: say it to the phone and the computer does it,
 * or the other way round. The sender posts the command and waits for its outcome; the target
 * device long-polls for commands, runs them as its own actions and reports back. Commands live
 * a minute at most: one that nobody took in time is dropped, never run later by surprise.
 */
export const DeviceKind = z.enum(["computer", "phone"]);
export type DeviceKind = z.infer<typeof DeviceKind>;

/** What each kind of device may be asked to do. */
export const RELAYED_TOOLS: Record<DeviceKind, readonly ToolName[]> = {
  computer: ["open_app", "open_url", "computer_control", "type_text", "create_note"],
  phone: ["call_contact", "send_message", "open_app", "open_url"],
};

/** POST /api/v1/sync/commands */
export const SendCommandRequest = z.object({
  target: DeviceKind,
  tool: ToolName,
  arguments: z.record(z.string(), z.unknown()),
});

/** `id` is null when no device of that kind is listening right now. */
export const SendCommandResponse = z.object({ id: Uuid.nullable() });
export type SendCommandResponse = z.infer<typeof SendCommandResponse>;

/** What the target device did, as it reports any action of its own. */
export const CommandOutcome = z.object({
  status: ActionStatus,
  executed_via: ExecutionTarget.nullable(),
  error_code: z.string().max(64).nullable(),
  data: z.record(z.string(), z.unknown()).nullable().optional(),
});
export type CommandOutcome = z.infer<typeof CommandOutcome>;

/** GET /api/v1/sync/commands/{id}?wait=seconds — waits up to `wait` for the outcome. */
export const CommandStateResponse = z.object({
  state: z.enum(["pending", "taken", "done", "expired"]),
  outcome: CommandOutcome.nullable(),
});
export type CommandStateResponse = z.infer<typeof CommandStateResponse>;

export const DeviceCommand = z.object({
  id: Uuid,
  tool: ToolName,
  arguments: z.record(z.string(), z.unknown()),
  from: SyncPlatform,
});
export type DeviceCommand = z.infer<typeof DeviceCommand>;

/** GET /api/v1/sync/commands?target=phone&wait=seconds — the commands for this kind of device. */
export const TakeCommandsResponse = z.object({ commands: z.array(DeviceCommand) });
export type TakeCommandsResponse = z.infer<typeof TakeCommandsResponse>;
