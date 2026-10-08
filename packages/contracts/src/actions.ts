import { z } from "zod";
import { ActionId, SpokenText } from "./common";
import { ExecutionTarget, TOOL_ARGUMENT_SCHEMAS, ToolName } from "./tools";

/**
 * Outcome of one action. "Never return a fake success" is encoded here:
 *
 * - succeeded:          the iOS API confirmed the action (e.g. EKEventStore.save returned)
 * - handed_off:         a system UI was opened (call prompt, Maps, Shortcut) and the app
 *                       cannot observe whether the user completed it
 * - cancelled:          the user declined the confirmation or cancelled the system UI
 * - permission_denied:  the needed iOS permission is not granted
 * - unsupported:        no strategy for this tool is available on this device / iOS version
 * - needs_clarification:the device found 0 or several matches (e.g. two "Ээж" contacts)
 * - failed:             the API returned an error
 */
export const ActionStatus = z.enum([
  "succeeded",
  "handed_off",
  "cancelled",
  "permission_denied",
  "unsupported",
  "needs_clarification",
  "failed",
]);
export type ActionStatus = z.infer<typeof ActionStatus>;

export const Confirmation = z.object({
  required: z.boolean(),
  /** Mongolian question shown/spoken before executing, e.g. "Ээж рүү тань залгах уу?" */
  prompt: SpokenText.nullable(),
});
export type Confirmation = z.infer<typeof Confirmation>;

/**
 * Result of executing an action. Contains no contact details, message bodies or
 * other personal data: only status and non-sensitive identifiers.
 */
export const ActionResult = z.object({
  action_id: ActionId,
  tool: ToolName,
  status: ActionStatus,
  executed_via: ExecutionTarget.nullable(),
  /** Machine-readable reason for non-success, e.g. "EK_SAVE_FAILED", "ALARMKIT_UNAVAILABLE". */
  error_code: z.string().max(64).nullable(),
  /** Count of on-device matches for needs_clarification (names never leave the device). */
  match_count: z.number().int().min(0).nullable().optional(),
  /** Backend-tool payload, e.g. weather summary. Device tools leave this null. */
  data: z.record(z.string(), z.unknown()).nullable().optional(),
});
export type ActionResult = z.infer<typeof ActionResult>;

function actionRequest<const T extends ToolName>(tool: T) {
  return z.object({
    id: ActionId,
    tool: z.literal(tool),
    arguments: TOOL_ARGUMENT_SCHEMAS[tool],
    confirmation: Confirmation,
    /** Present only for backend-executed tools, which already ran before the response was sent. */
    result: ActionResult.nullable(),
  });
}

/**
 * One action the backend wants performed. Device actions arrive with result=null;
 * the app executes them in array order and reports results back.
 */
export const ActionRequest = z.discriminatedUnion("tool", [
  actionRequest("call_contact"),
  actionRequest("create_reminder"),
  actionRequest("create_calendar_event"),
  actionRequest("create_alarm"),
  actionRequest("get_weather"),
  actionRequest("open_maps"),
  actionRequest("create_note"),
  actionRequest("send_message"),
  actionRequest("web_search"),
  actionRequest("get_current_time"),
  actionRequest("open_url"),
  actionRequest("open_app"),
  actionRequest("set_timer"),
  actionRequest("list_reminders"),
  actionRequest("cancel_reminder"),
  actionRequest("computer_control"),
  actionRequest("add_todo"),
  actionRequest("list_todos"),
  actionRequest("complete_todo"),
  actionRequest("delete_todo"),
]);
export type ActionRequest = z.infer<typeof ActionRequest>;
