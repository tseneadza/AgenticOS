/**
 * Mock script data for testing
 */

export const mockScript = {
  id: "app1/test-script",
  app_id: "app1",
  name: "test-script",
  path: "/apps/app1/test-script.sh",
  description: "A test script that does something",
  type: "Test",
  project: "app1",
};

export const mockScripts = [
  {
    id: "app1/start-server",
    app_id: "app1",
    name: "start-server",
    path: "/apps/app1/start-server.sh",
    description: "Start the application server",
    type: "Launcher",
    project: "app1",
  },
  {
    id: "app1/run-tests",
    app_id: "app1",
    name: "run-tests",
    path: "/apps/app1/run-tests.sh",
    description: "Run the test suite",
    type: "Test",
    project: "app1",
  },
  {
    id: "app1/seed-db",
    app_id: "app1",
    name: "seed-db",
    path: "/apps/app1/seed-db.py",
    description: "Seed the database with sample data",
    type: "Data",
    project: "app1",
  },
  {
    id: "app2/fetch-data",
    app_id: "app2",
    name: "fetch-data",
    path: "/apps/app2/fetch-data.py",
    description: "Fetch external data",
    type: "Scraper",
    project: "app2",
  },
  {
    id: "app2/diagnose",
    app_id: "app2",
    name: "diagnose",
    path: "/apps/app2/diagnose.sh",
    description: "Diagnose system health",
    type: "Diagnostic",
    project: "app2",
  },
];

export const mockScriptInfo = {
  purpose: "Run the test suite and report results",
  fullHeader: `#!/bin/bash
# Run tests for the application
#
# Usage: ./run-tests.sh [--coverage] [--watch]
#
# Options:
#   --coverage    Generate coverage report
#   --watch       Watch mode for development
#
# Requires: node, npm
# Environment: TEST_ENV
`,
  usageLines: [
    "./run-tests.sh",
    "./run-tests.sh --coverage",
    "./run-tests.sh --watch",
  ],
  paramLines: [
    "--coverage      Generate coverage report",
    "--watch         Watch mode for development",
  ],
  envVars: ["TEST_ENV", "NODE_ENV"],
  deps: ["node", "npm"],
  noteLines: ["Requires Node.js to be installed"],
  lineCount: 145,
};

export const mockScriptContent = `#!/bin/bash
# Run tests for the application
#
# Usage:
#   ./run-tests.sh
#   ./run-tests.sh --coverage
#   ./run-tests.sh --watch
#
# Options:
#   --coverage    Generate coverage report
#   --watch       Watch mode for development

set -e

cd "$(dirname "$0")"

# Default values
COVERAGE=false
WATCH=false

# Parse arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --coverage) COVERAGE=true; shift ;;
    --watch) WATCH=true; shift ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

echo "Running tests..."
npm test $([ "$COVERAGE" = true ] && echo -- --coverage) $([ "$WATCH" = true ] && echo -- --watch)
`;
