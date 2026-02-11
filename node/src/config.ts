import { readFileSync, existsSync } from 'node:fs';
import { resolve, dirname } from 'node:path';

/**
 * Parsed environment config from DEVLOGS_* vars and .env.devlogs files.
 */
export interface EnvConfig {
  url?: string;
  index?: string;
  application?: string;
  component?: string;
  area?: string;
  environment?: string;
  version?: string;
}

let envLoaded = false;

/**
 * Minimal .env file parser. No external dependencies.
 * Handles KEY=VALUE, KEY="VALUE", KEY='VALUE', and # comments.
 */
function parseDotenv(content: string): Record<string, string> {
  const result: Record<string, string> = {};
  for (const line of content.split('\n')) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;

    const eqIndex = trimmed.indexOf('=');
    if (eqIndex === -1) continue;

    const key = trimmed.slice(0, eqIndex).trim();
    let value = trimmed.slice(eqIndex + 1).trim();

    // Strip surrounding quotes
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }

    result[key] = value;
  }
  return result;
}

/**
 * Search upward from cwd for a file by name.
 */
function findFileUpward(filename: string, startDir?: string): string | null {
  let dir = startDir || process.cwd();
  const root = resolve('/');

  while (true) {
    const candidate = resolve(dir, filename);
    if (existsSync(candidate)) {
      return candidate;
    }
    const parent = dirname(dir);
    if (parent === dir || dir === root) {
      return null;
    }
    dir = parent;
  }
}

/**
 * Load environment variables from .env.devlogs (preferred) or .env file.
 * Only sets variables that are not already defined in process.env.
 * Called once automatically on first config load.
 */
export function loadDotenv(): void {
  if (envLoaded) return;
  envLoaded = true;

  const dotenvPath = process.env.DOTENV_PATH;
  let filePath: string | null = null;

  if (dotenvPath) {
    filePath = dotenvPath;
  } else {
    // Prefer .env.devlogs over .env
    filePath = findFileUpward('.env.devlogs');
    if (!filePath) {
      filePath = findFileUpward('.env');
    }
  }

  if (!filePath || !existsSync(filePath)) return;

  try {
    const content = readFileSync(filePath, 'utf-8');
    const vars = parseDotenv(content);
    for (const [key, value] of Object.entries(vars)) {
      // Don't override existing env vars
      if (process.env[key] === undefined) {
        process.env[key] = value;
      }
    }
  } catch {
    // Silently ignore read errors
  }
}

/**
 * Reset the loaded state (for testing).
 */
export function resetDotenvLoaded(): void {
  envLoaded = false;
}

/**
 * Load configuration from DEVLOGS_* environment variables.
 * Automatically loads .env.devlogs on first call.
 */
export function loadEnvConfig(): EnvConfig {
  loadDotenv();

  return {
    url: process.env.DEVLOGS_URL || undefined,
    index: process.env.DEVLOGS_INDEX || undefined,
    application: process.env.DEVLOGS_APPLICATION || undefined,
    component: process.env.DEVLOGS_COMPONENT || undefined,
    area: process.env.DEVLOGS_AREA || undefined,
    environment: process.env.DEVLOGS_ENVIRONMENT || undefined,
    version: process.env.DEVLOGS_VERSION || undefined,
  };
}
