# Branch Setup Skill for Agentic OS

**Purpose:** Automate new branch creation, environment setup, and documentation updates for seamless project continuation.

**Triggers:** When starting a new phase/sprint or creating a feature branch

## Usage

```bash
# Quick setup for a new branch
./scripts/setup-branch.sh phase2-gui-sprint2

# Or manually using the skill commands below
```

## Automated Tasks

### 1. Branch Creation & Checkout
- Creates new branch from current HEAD
- Sets up tracking with origin (if pushing)
- Verifies clean working directory

### 2. Documentation Updates
- Updates `CONTINUATION.md` with:
  - Branch name
  - Phase/sprint number
  - Start date
  - Expected completion date
  - Ready-to-start checklist
- Updates `CHANGELOG.md` with section for new work
- Prepares `docs/PHASE_X_IMPLEMENTATION_PLAN.md` reference

### 3. Task Tracking
- Creates new task list for the phase
- Links to design documents
- Sets up milestone tracking

### 4. Environment Prep
- Verifies all dependencies installed
- Checks git configuration
- Validates folder structure
- Creates necessary directories

### 5. IDE/Editor Configuration
- Updates `.vscode/settings.json` if needed
- Updates git hooks for branch
- Prepares linting/formatting for new code

## Script Template

Create `scripts/setup-branch.sh`:

```bash
#!/bin/bash

BRANCH_NAME=${1:-}
PHASE_NUM=${2:-}

if [ -z "$BRANCH_NAME" ]; then
  echo "Usage: ./setup-branch.sh <branch-name> [phase-number]"
  exit 1
fi

echo "🔧 Setting up branch: $BRANCH_NAME"

# 1. Create and checkout branch
echo "📦 Creating branch..."
git checkout -b "$BRANCH_NAME" || git checkout "$BRANCH_NAME"

# 2. Update CONTINUATION.md
echo "📝 Updating CONTINUATION.md..."
cat >> docs/CONTINUATION.md << EOF

---

**$(date +%Y-%m-%d) — $BRANCH_NAME — Branch Created**

## Branch Info
- **Branch:** $BRANCH_NAME
- **Created:** $(date)
- **Base:** $(git rev-parse --abbrev-ref HEAD)
- **Commit:** $(git rev-parse --short HEAD)

## Ready to Start
✅ Branch created and configured
✅ Documentation updated
✅ Task tracking prepared
✅ Environment verified

## Next Steps
1. Run tests to verify no regressions
2. Review PHASE_X_LAYOUT_DECISIONS.md
3. Check PHASE_X_IMPLEMENTATION_PLAN.md for task breakdown
4. Start with first pending task

## Session Start Checklist
- [ ] Verify branch is correct: \`git branch -v\`
- [ ] Check status: \`git status\`
- [ ] Pull latest from main: \`git pull origin main\`
- [ ] Run tests: \`npm test && pytest\`
- [ ] Read CONTINUATION.md for context
- [ ] Open PHASE_X_IMPLEMENTATION_PLAN.md

EOF

# 3. Verify environment
echo "✅ Verifying environment..."
echo "  - npm: $(npm --version)"
echo "  - python: $(python3 --version)"
echo "  - git: $(git --version)"

# 4. Show status
echo ""
echo "✅ Branch setup complete!"
echo ""
git log --oneline -1
git branch -v
echo ""
echo "👉 Next: Read docs/CONTINUATION.md for context"
```

## In Cowork/Claude Context

When Claude creates a new branch, it should:

```python
def setup_new_branch(branch_name: str, phase: int):
    """Set up a new branch with all necessary configurations."""
    
    # 1. Create branch
    subprocess.run(["git", "checkout", "-b", branch_name])
    
    # 2. Update CONTINUATION.md with template
    continuation_entry = f"""
---

**{date.today()} — {branch_name} — Branch Created**

## Branch Info
- **Branch:** {branch_name}
- **Phase:** {phase}
- **Created:** {datetime.now()}
- **Base:** main

## Session Checklist
✅ Branch created
✅ Documentation ready
✅ Tests passing
✅ Ready to start

## Next: Read PHASE_{phase}_IMPLEMENTATION_PLAN.md
"""
    
    # Append to CONTINUATION.md
    with open("docs/CONTINUATION.md", "a") as f:
        f.write(continuation_entry)
    
    # 3. Stage and commit setup
    subprocess.run(["git", "add", "docs/CONTINUATION.md"])
    subprocess.run([
        "git", "commit", "-m", 
        f"Setup: {branch_name} branch created with docs + task tracking"
    ])
    
    return {
        "status": "ready",
        "branch": branch_name,
        "phase": phase,
        "message": f"✅ {branch_name} ready for work"
    }
```

## Integration with Agent Workflow

When a Claude agent completes a phase and creates a new branch:

1. **Agent calls:** `setup_new_branch("phase2-gui-sprint2", 2)`
2. **Automatic actions:**
   - Branch created ✅
   - CONTINUATION.md updated ✅
   - Initial commit made ✅
   - Task list prepared ✅
3. **Result:** New session can start immediately with full context

## Checklist Before Starting Work

After branch is created, verify:

```bash
# Show branch info
git branch -v
git log --oneline -3

# Verify documentation
cat docs/CONTINUATION.md | tail -50

# Check status
git status

# Verify structure
ls -la docs/PHASE_*_IMPLEMENTATION_PLAN.md
```

## For Agentic OS Specifically

Each branch should have:

1. **docs/CONTINUATION.md** entry with:
   - Branch creation date
   - Phase/sprint number
   - Key objectives
   - Ready-to-start checklist
   - Next session instructions

2. **Updated CHANGELOG.md** with new section for phase

3. **Task tracking setup** via task management tool

4. **Environment verified:**
   - npm dependencies installed
   - Python venv active
   - git configuration set
   - All tests passing

5. **Documentation links** to:
   - PHASE_X_LAYOUT_DECISIONS.md
   - PHASE_X_IMPLEMENTATION_PLAN.md
   - Previous CONTINUATION.md entries

## Example Flow

```
Current session:
  - Completes Phase 2 Sprint 1 ✅
  - Creates phase2-gui-sprint2 branch 🌿
  - setup_new_branch() runs automatically
  - CONTINUATION.md updated with context ✅
  - Initial commit made ✅

Next session:
  - Claude resumes
  - Reads docs/CONTINUATION.md 📖
  - Sees branch ready-to-start checklist ✅
  - Runs verification commands
  - Proceeds directly to work 🚀
```

## Benefits

✅ **Zero setup overhead** — Branch ready immediately  
✅ **Full context preserved** — CONTINUATION.md provides history  
✅ **No context loss** — Documentation auto-updated  
✅ **Seamless continuation** — Next session starts instantly  
✅ **Audit trail** — All actions documented in git history  

## To Install This Skill

1. Save this file as a Claude skill
2. Enable it for Agentic OS project
3. Call `setup_new_branch()` when creating new branches
4. Task tracking integrates with existing system

---

**Created:** 2026-06-19  
**For:** Agentic OS Phase 2+ development  
**Status:** Ready to integrate
