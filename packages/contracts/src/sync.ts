import { z } from "zod";
import { IsoDateTime, Uuid } from "./common";

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
