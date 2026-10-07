import { writeFileSync } from "node:fs";
import { join } from "node:path";
import { buildGeneratedFiles } from "./schemas";

const outDir = join(import.meta.dirname, "..", "generated");

for (const [file, content] of Object.entries(buildGeneratedFiles())) {
  writeFileSync(join(outDir, file), content, "utf8");
  console.log(`wrote generated/${file}`);
}
