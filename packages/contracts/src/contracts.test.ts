import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import type { z } from "zod";
import { buildGeneratedFiles } from "../scripts/schemas";
import {
  ActionResultsRequest,
  ActionResultsResponse,
  AssistantContext,
  AssistantTurn,
  LimitationCode,
  TOOL_ARGUMENT_SCHEMAS,
  TOOL_MANIFEST,
  TOOL_NAMES,
  ToolName,
  type ToolManifestEntry,
  type ToolName as ToolNameT,
} from "./index";

const root = join(import.meta.dirname, "..");
const readJson = (path: string): unknown => JSON.parse(readFileSync(join(root, path), "utf8"));

const EXAMPLE_SCHEMAS: Record<string, z.ZodType> = {
  context: AssistantContext,
  turn: AssistantTurn,
  results: ActionResultsRequest,
  "results-response": ActionResultsResponse,
};

describe("examples/", () => {
  const files = readdirSync(join(root, "examples")).filter((f) => f.endsWith(".json"));

  it("has examples", () => expect(files.length).toBeGreaterThan(0));

  it.each(files)("%s matches its schema", (file) => {
    const prefix = file.split(".")[0]!;
    const schema = EXAMPLE_SCHEMAS[prefix];
    expect(schema, `no schema for prefix "${prefix}"`).toBeDefined();
    const parsed = schema!.safeParse(readJson(`examples/${file}`));
    expect(parsed.error?.issues ?? []).toEqual([]);
  });
});

describe("AssistantTurn invariants", () => {
  const milestone = readJson("examples/turn.reminder-milestone.json") as Record<string, unknown>;

  it("rejects a 'final' turn that still has unexecuted device actions (no fake success)", () => {
    const bad = { ...milestone, stage: "final", response: "За, хийчихлээ." };
    expect(AssistantTurn.safeParse(bad).success).toBe(false);
  });

  it("rejects a confirmation-required action without a prompt", () => {
    const call = readJson("examples/turn.call-confirmation.json") as any;
    call.actions[0].confirmation.prompt = null;
    expect(AssistantTurn.safeParse(call).success).toBe(false);
  });

  it("rejects relative dates in device action arguments", () => {
    const bad = structuredClone(milestone) as any;
    bad.actions[0].arguments.due_at = "tomorrow";
    expect(AssistantTurn.safeParse(bad).success).toBe(false);
  });

  it("rejects backend tools without an inline result", () => {
    const multi = readJson("examples/turn.call-then-weather.json") as any;
    multi.actions[1].result = null;
    expect(AssistantTurn.safeParse(multi).success).toBe(false);
  });
});

describe("open_app arguments", () => {
  const args = TOOL_ARGUMENT_SCHEMAS.open_app;

  it("opens an app, or searches inside it", () => {
    expect(args.parse({ app_name: "YouTube" })).toEqual({ app_name: "YouTube" });
    expect(args.parse({ app_name: "YouTube", query: " Монгол дуу " })).toEqual({ app_name: "YouTube", query: "Монгол дуу" });
  });

  it("rejects an empty search", () => {
    expect(args.safeParse({ app_name: "Spotify", query: "  " }).success).toBe(false);
  });
});

describe("tool manifest", () => {
  it("covers every tool", () => {
    expect(Object.keys(TOOL_MANIFEST).sort()).toEqual([...TOOL_NAMES].sort());
    expect(Object.keys(TOOL_ARGUMENT_SCHEMAS).sort()).toEqual([...TOOL_NAMES].sort());
  });

  it("always confirms calls and messages", () => {
    expect(TOOL_MANIFEST.call_contact.confirmation).toBe("always");
    expect(TOOL_MANIFEST.send_message.confirmation).toBe("always");
  });

  it("keeps backend tools on the backend and device tools off it", () => {
    for (const name of TOOL_NAMES) {
      const entry: ToolManifestEntry = TOOL_MANIFEST[name];
      expect(entry.strategy.includes("backend")).toBe(entry.executor === "backend");
    }
  });
});

describe("fixtures/intent-cases.json", () => {
  const fixtures = readJson("fixtures/intent-cases.json") as any;
  const allExpectations = [
    ...fixtures.cases.map((c: any) => [c.id, c.expected]),
    ...fixtures.conversations.flatMap((c: any) =>
      c.turns.map((t: any, i: number) => [`${c.id}#${i}`, t.expected]),
    ),
  ] as [string, any][];

  it.each(allExpectations)("%s references valid tools and arguments", (_id, expected) => {
    expected.tools.forEach((tool: string, i: number) => {
      expect(ToolName.safeParse(tool).success).toBe(true);
      const args = expected.arguments?.[i];
      if (args) {
        const partial = (TOOL_ARGUMENT_SCHEMAS[tool as ToolNameT] as z.ZodObject).partial();
        expect(partial.safeParse(args).error?.issues ?? []).toEqual([]);
      }
    });
    if (expected.limitation) {
      expect(expected.tools).toEqual([]);
      expect(LimitationCode.safeParse(expected.limitation).success).toBe(true);
    }
  });

  it("covers all ten required spec cases", () => {
    expect(fixtures.cases.filter((c: any) => /^(0[1-9]|10)_/.test(c.id))).toHaveLength(10);
  });
});

describe("generated/", () => {
  it.each(Object.entries(buildGeneratedFiles()))("%s is up to date (run npm run contracts:export)", (file, content) => {
    const committed = readFileSync(join(root, "generated", file), "utf8").replace(/\r\n/g, "\n");
    expect(committed).toBe(content);
  });
});
