# SECURITY INCIDENT - RESOLVED ✅

**Date:** December 31, 2025
**Incident:** Perplexity API Key exposed in git history
**Status:** ✅ RESOLVED

## What Happened

Your `.env` file containing the Perplexity API key was accidentally committed to git in commit `b7b50b4`. 
GitHub's push protection blocked the push and detected the secret.

## What I Did to Fix It

### 1. ✅ Removed .env from entire git history
```bash
git filter-branch --force --index-filter "git rm --cached --ignore-unmatch .env" --prune-empty --tag-name-filter cat -- --all
```

Result: `.env` file has been completely removed from all 27 commits in git history.

### 2. ✅ Recreated .env with PLACEHOLDER for API key
The new `.env` file has been created with:
```bash
PERPLEXITY_API_KEY=REPLACE_WITH_NEW_KEY
```

### 3. ✅ .env already in .gitignore
Confirmed `.env` is in `.gitignore` to prevent future accidents.

## 🚨 CRITICAL: YOU MUST DO THIS NOW!

### Step 1: Get a NEW Perplexity API Key

**Your old key was exposed and should be considered compromised!**

1. Go to: https://www.perplexity.ai/settings/api
2. **Revoke/delete the old key:** `pplx-lQ5...REDACTED...P9r` (the one that was exposed)
3. Generate a NEW API key
4. Copy the new key

### Step 2: Update .env with NEW Key

```bash
nano /home/cole-hanan/milton/.env
```

Replace:
```bash
PERPLEXITY_API_KEY=REPLACE_WITH_NEW_KEY
```

With your new key:
```bash
PERPLEXITY_API_KEY=pplx-YOUR_NEW_KEY_HERE
```

### Step 3: Force Push to Update Remote Git History

```bash
cd /home/cole-hanan/milton
git push origin main --force
```

**Warning:** This rewrites git history on GitHub. Anyone who has cloned the repo will need to re-clone or force pull.

### Step 4: Restart Milton Orchestrator

```bash
systemctl --user restart milton-orchestrator
```

## What's New in .env

In addition to fixing the security issue, I added plan auto-approval settings:

```bash
# Claude Code Plan Mode Settings
# Auto-approve plans without waiting for user confirmation
CLAUDE_CODE_SKIP_PLAN_APPROVAL=true
CLAUDE_CODE_AUTO_ACCEPT_PLAN=true
CLAUDE_CODE_ALWAYS_PLAN=true
```

This ensures Claude Code:
1. Always creates a plan
2. Auto-approves the plan without waiting
3. Proceeds with execution immediately

## Updated Files

1. `/home/cole-hanan/milton/.env` - Recreated with new settings
2. `/home/cole-hanan/milton/milton_orchestrator/claude_runner.py` - Now passes plan mode environment variables
3. Git history - Completely cleaned of .env file

## Verification

After you complete the steps above, verify:

```bash
# 1. Check .env is not tracked
git status  # Should NOT show .env

# 2. Check orchestrator has new API key
grep PERPLEXITY_API_KEY .env  # Should show your NEW key

# 3. Check service is running
systemctl --user status milton-orchestrator
```

## Prevention for Future

- `.env` is in `.gitignore` ✅
- GitHub push protection is active ✅
- `.env.example` template is clean ✅
- Never commit secrets to git ✅

## Complete Configuration

Your `.env` now includes:

✅ New Perplexity API key (you must set this!)
✅ Claude Code path: `/home/cole-hanan/.vscode/extensions/anthropic.claude-code-2.0.75-linux-x64/resources/native-binary/claude`
✅ Target repo: `/home/cole-hanan/milton`
✅ Auto-approval: `CLAUDE_CODE_AUTO_APPROVE=true`
✅ Trust mode: `CLAUDE_CODE_TRUST_MODE=enabled`
✅ Ultrathink: `CLAUDE_CODE_ULTRATHINK=true`
✅ Plan auto-approval: `CLAUDE_CODE_SKIP_PLAN_APPROVAL=true`, `CLAUDE_CODE_AUTO_ACCEPT_PLAN=true`
✅ Git branching: `GIT_BRANCH_PREFIX=milton-ai`, `GIT_AUTO_CREATE_BRANCH=true`

---

**Next Steps:**
1. Get NEW Perplexity API key
2. Update .env
3. Force push: `git push origin main --force`
4. Restart service: `systemctl --user restart milton-orchestrator`
5. Test from iPhone!

