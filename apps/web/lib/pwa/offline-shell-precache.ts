import { createHash } from "node:crypto";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";

export const OFFLINE_SHELL_URL = "/offline";

export type OfflineShellPrecacheEntry = {
  url: typeof OFFLINE_SHELL_URL;
  revision: string;
};

export function createOfflineShellPrecacheEntry(shellHtml: string): OfflineShellPrecacheEntry {
  return {
    url: OFFLINE_SHELL_URL,
    revision: createHash("sha256").update(shellHtml).digest("hex"),
  };
}

function listSourceFiles(directory: string): string[] {
  return readdirSync(directory, { withFileTypes: true })
    .flatMap((entry) => {
      const entryPath = join(directory, entry.name);
      return entry.isDirectory() ? listSourceFiles(entryPath) : [entryPath];
    })
    .sort();
}

export function createOfflineShellPrecacheEntryFromBuildInputs(projectDirectory = process.cwd()): OfflineShellPrecacheEntry {
  const buildInputs = [
    ...listSourceFiles(join(projectDirectory, "app")),
    ...listSourceFiles(join(projectDirectory, "components")),
    ...listSourceFiles(join(projectDirectory, "lib", "offline")),
    join(projectDirectory, "package.json"),
  ];
  const revisionInput = buildInputs
    .filter((filePath) => statSync(filePath).isFile())
    .map((filePath) => `${relative(projectDirectory, filePath)}\0${readFileSync(filePath, "utf8")}`)
    .join("\0");

  return createOfflineShellPrecacheEntry(revisionInput);
}
