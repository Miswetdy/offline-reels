import { createHash } from "node:crypto";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";

export const OFFLINE_SHELL_URL = "/offline";
export const VIDEOS_SHELL_URL = "/videos";
export const WEB_MANIFEST_URL = "/manifest.webmanifest";

export type ApplicationShellPrecacheEntry = {
  url: typeof OFFLINE_SHELL_URL | typeof VIDEOS_SHELL_URL | typeof WEB_MANIFEST_URL;
  revision: string;
};

export function createApplicationShellPrecacheEntry(
  url: ApplicationShellPrecacheEntry["url"],
  buildInput: string,
): ApplicationShellPrecacheEntry {
  return {
    url,
    revision: createHash("sha256").update(buildInput).digest("hex"),
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

export function createApplicationShellPrecacheEntriesFromBuildInputs(
  projectDirectory = process.cwd(),
): ApplicationShellPrecacheEntry[] {
  const buildInputs = [
    ...listSourceFiles(join(projectDirectory, "app")),
    ...listSourceFiles(join(projectDirectory, "components")),
    ...listSourceFiles(join(projectDirectory, "lib")),
    join(projectDirectory, "package.json"),
  ];
  const revisionInput = buildInputs
    .filter((filePath) => statSync(filePath).isFile())
    .map((filePath) => `${relative(projectDirectory, filePath)}\0${readFileSync(filePath, "utf8")}`)
    .join("\0");

  return [
    createApplicationShellPrecacheEntry(OFFLINE_SHELL_URL, revisionInput),
    createApplicationShellPrecacheEntry(VIDEOS_SHELL_URL, revisionInput),
    createApplicationShellPrecacheEntry(WEB_MANIFEST_URL, revisionInput),
  ];
}
