#!/bin/bash

##############################################################################
# Branch Setup Automation Script
#
# Purpose: Create a new branch and prepare environment for seamless continuation
# Usage: ./scripts/setup-branch.sh <branch-name> [phase-number]
#
# Example: ./scripts/setup-branch.sh phase2-gui-sprint2 2
##############################################################################

set -e  # Exit on error

BRANCH_NAME=${1:-}
PHASE_NUM=${2:-}
DATE=$(date +"%Y-%m-%d")
TIME=$(date +"%H:%M:%S")
COMMIT_SHA=$(git rev-parse --short HEAD)
BASE_BRANCH=$(git rev-parse --abbrev-ref HEAD)

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Validation
if [ -z "$BRANCH_NAME" ]; then
  echo "❌ Error: Branch name required"
  echo ""
  echo "Usage: $0 <branch-name> [phase-number]"
  echo "Examples:"
  echo "  $0 phase2-gui-sprint2 2"
  echo "  $0 phase3-scripts-view 3"
  exit 1
fi

echo -e "${BLUE}🔧 Branch Setup Automation${NC}"
echo "=================================================="
echo ""

# 1. Check git status
echo -e "${YELLOW}1️⃣  Checking git status...${NC}"
if [ -n "$(git status --porcelain)" ]; then
  echo "⚠️  Warning: Uncommitted changes detected. Commit or stash them first:"
  git status --short
  echo ""
  read -p "Continue anyway? (y/n) " -n 1 -r
  echo
  if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "❌ Aborted"
    exit 1
  fi
fi
echo -e "${GREEN}✅ Working directory clean${NC}"
echo ""

# 2. Create and checkout branch
echo -e "${YELLOW}2️⃣  Creating branch: $BRANCH_NAME${NC}"
if git rev-parse --verify "$BRANCH_NAME" >/dev/null 2>&1; then
  echo "⚠️  Branch already exists, checking out..."
  git checkout "$BRANCH_NAME"
else
  git checkout -b "$BRANCH_NAME"
fi
echo -e "${GREEN}✅ Branch ready${NC}"
echo ""

# 3. Update CONTINUATION.md
echo -e "${YELLOW}3️⃣  Updating CONTINUATION.md...${NC}"
cat >> docs/CONTINUATION.md << 'CONTINUATION_EOF'

---

CONTINUATION_EOF

cat >> docs/CONTINUATION.md << CONTINUATION_EOF
**$DATE ($TIME) — $BRANCH_NAME Branch Created**

## Branch Info
- **Branch:** $BRANCH_NAME
- **Created:** $DATE $TIME
- **Base:** $BASE_BRANCH ($COMMIT_SHA)
- **Phase:** ${PHASE_NUM:-TBD}

## Session Setup ✅
- [x] Branch created and checked out
- [x] Documentation updated
- [x] Environment ready
- [ ] Tests verified (run: npm test && pytest)
- [ ] Ready to start work

## Ready-to-Start Checklist
Before starting work on this branch:

\`\`\`bash
# 1. Verify branch
git branch -v
git log --oneline -1

# 2. Pull latest from main (optional)
git pull origin main

# 3. Run tests
npm run lint
npm test
pytest

# 4. Read documentation
cat docs/CONTINUATION.md
\`\`\`

## Next Steps
1. Review previous CONTINUATION.md entries for context
2. Check PHASE_${PHASE_NUM:-X}_LAYOUT_DECISIONS.md for design decisions
3. Read PHASE_${PHASE_NUM:-X}_IMPLEMENTATION_PLAN.md for task breakdown
4. Start with first pending task from task tracking system

## Key Documentation
- \`docs/PHASE_${PHASE_NUM:-X}_LAYOUT_DECISIONS.md\` — Design decisions
- \`docs/PHASE_${PHASE_NUM:-X}_IMPLEMENTATION_PLAN.md\` — Implementation breakdown
- \`docs/CHANGELOG.md\` — Project history
- \`docs/roadmap.md\` — Phase status

---

CONTINUATION_EOF

echo -e "${GREEN}✅ CONTINUATION.md updated${NC}"
echo ""

# 4. Update CHANGELOG.md
echo -e "${YELLOW}4️⃣  Updating CHANGELOG.md...${NC}"
cat >> docs/CHANGELOG.md << CHANGELOG_EOF

## $DATE — $BRANCH_NAME — Branch Created

- **Branch:** $BRANCH_NAME (based on $BASE_BRANCH)
- **Phase:** ${PHASE_NUM:-TBD}
- **Status:** Ready for work
- Session setup complete with automated branch initialization
- Full context preserved in CONTINUATION.md
- Ready-to-start checklist prepared

CHANGELOG_EOF

echo -e "${GREEN}✅ CHANGELOG.md updated${NC}"
echo ""

# 5. Verify environment
echo -e "${YELLOW}5️⃣  Verifying environment...${NC}"
echo "  📦 npm: $(npm --version)"
echo "  🐍 python: $(python3 --version)"
echo "  🔗 git: $(git --version 2>&1 | head -1)"
echo -e "${GREEN}✅ Environment verified${NC}"
echo ""

# 6. Stage and commit setup
echo -e "${YELLOW}6️⃣  Committing branch setup...${NC}"
git add docs/CONTINUATION.md docs/CHANGELOG.md
git commit -m "Setup: $BRANCH_NAME branch created with documentation + ready-to-start checklist"
echo -e "${GREEN}✅ Initial commit made${NC}"
echo ""

# 7. Show final status
echo -e "${BLUE}=================================================="
echo -e "✅ Branch Setup Complete!${NC}"
echo "=================================================="
echo ""
echo -e "${GREEN}Branch:${NC} $(git branch --show-current)"
echo -e "${GREEN}Commit:${NC} $(git log --oneline -1)"
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo "  1. Read docs/CONTINUATION.md for full context"
echo "  2. Run: npm test && pytest"
echo "  3. Review PHASE_${PHASE_NUM:-X}_IMPLEMENTATION_PLAN.md"
echo "  4. Start with first pending task"
echo ""
echo -e "${BLUE}👉 Happy coding! 🚀${NC}"
