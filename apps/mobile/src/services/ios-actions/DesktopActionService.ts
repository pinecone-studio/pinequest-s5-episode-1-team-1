import { ActionStatus, type ToolArguments, type ToolName } from "@duud/contracts";
import { apiBaseUrl } from "@/services/assistant/connect";
import type { ActionOutcome } from "./IOSActionService";
import { LinkingIOSActionService } from "./LinkingIOSActionService";
import { googleMapsUrl } from "./maps";

/**
 * The web app on the Windows PC that runs the Duud API: reminders, alarms, event reminders
 * and notes are done on this PC by the API (apps/api desktop.py). Calls and messages need
 * a phone. In any other browser the API answers 404 and the action is unsupported.
 */
export class DesktopActionService extends LinkingIOSActionService {
  createReminder = (args: ToolArguments<"create_reminder">) => this.onPc("create_reminder", args);
  createAlarm = (args: ToolArguments<"create_alarm">) => this.onPc("create_alarm", args);
  createCalendarEvent = (args: ToolArguments<"create_calendar_event">) => this.onPc("create_calendar_event", args);
  createNote = (args: ToolArguments<"create_note">) => this.onPc("create_note", args);
  openApp = (args: ToolArguments<"open_app">) => this.onPc("open_app", args);
  setTimer = (args: ToolArguments<"set_timer">) => this.onPc("set_timer", args);
  listReminders = (args: ToolArguments<"list_reminders">) => this.onPc("list_reminders", args);
  cancelReminder = (args: ToolArguments<"cancel_reminder">) => this.onPc("cancel_reminder", args);
  computerControl = (args: ToolArguments<"computer_control">) => this.onPc("computer_control", args);

  openMaps = (args: ToolArguments<"open_maps">) => this.openUrl({ url: googleMapsUrl(args) });

  private async onPc(tool: ToolName, args: unknown): Promise<ActionOutcome> {
    let res: Response;
    try {
      res = await fetch(`${apiBaseUrl()}/api/v1/desktop/actions`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ tool, arguments: args }),
      });
    } catch {
      return { status: "failed", executed_via: null, error_code: "DESKTOP_UNREACHABLE" };
    }
    if (res.status === 404) return { status: "unsupported", executed_via: null, error_code: this.nativeUnavailableCode };
    const body = (await res.json().catch(() => null)) as Partial<ActionOutcome> | null;
    const status = ActionStatus.safeParse(body?.status);
    if (!res.ok || !status.success) return { status: "failed", executed_via: "backend", error_code: "DESKTOP_FAILED" };
    return {
      status: status.data,
      executed_via: "backend",
      error_code: body?.error_code ?? null,
      match_count: body?.match_count ?? null,
      data: body?.data ?? null,
    };
  }
}
