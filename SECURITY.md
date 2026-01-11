# Security Policy

## Overview

Milton is a local-first AI agent system designed for secure, privacy-preserving operation on personal workstations. This security policy outlines how we handle vulnerabilities, maintain secure defaults, and protect user data.

**Key Security Principles:**
- **Local-first:** All processing happens on your machine (no cloud APIs by default)
- **Fail loudly:** No silent fallbacks or hidden credentials
- **Minimal attack surface:** Services bind to localhost only by default
- **Artifact integrity:** Model bundles verified with SHA256 checksums
- **Transparent defaults:** All secrets must be explicitly configured via `.env`

---

## Supported Versions

Milton follows a **main-branch development** model with semantic versioning for releases:

| Branch/Version | Supported          | Notes |
| -------------- | ------------------ | ----- |
| `main` branch  | ✅ Yes             | Latest stable code, security fixes applied here |
| Tagged releases (v1.x.x) | ✅ Yes | Security patches backported for latest release |
| Development branches | ⚠️ No | Use at your own risk, may contain experimental code |

**Update Policy:**
- Security fixes are applied to `main` within **48 hours** of confirmation
- Critical vulnerabilities (RCE, data exfiltration) patched within **24 hours**
- Dependency updates managed via Dependabot (see [Dependency Security](#dependency-security))

---

## Reporting a Vulnerability

### Where to Report

**For security vulnerabilities, do NOT create public GitHub issues.**

Instead, use one of these private channels:

1. **GitHub Security Advisories** (preferred)
   - Go to: https://github.com/colehanan1/personal-ai-agent/security/advisories
   - Click "Report a vulnerability"
   - Provide details using the template below

2. **Email** (if GitHub advisories unavailable)
   - Contact repository maintainer via GitHub profile
   - Subject line: `[SECURITY] Milton Vulnerability Report`

### What to Include

Please provide:
- **Description:** Clear summary of the vulnerability
- **Impact:** What can an attacker do? (RCE, data leak, DoS, etc.)
- **Reproduction:** Step-by-step instructions to reproduce
- **Affected components:** Which files/modules are vulnerable?
- **Suggested fix:** (optional) Your thoughts on mitigation
- **Exploit proof-of-concept:** (if safe to share)

### Response Timeline

- **Initial response:** Within **48 hours** of report
- **Triage & validation:** Within **5 business days**
- **Fix development:** Depends on severity (24h for critical, 1-2 weeks for low)
- **Public disclosure:** After patch is released + 7 days (coordinated disclosure)

### What to Expect

**If accepted:**
- We'll acknowledge the vulnerability and work on a fix
- You'll be credited in the CHANGELOG and/or security advisory (if desired)
- We'll coordinate disclosure timeline with you

**If declined:**
- We'll explain why it's not considered a security issue (e.g., requires physical access, out of scope)
- You're free to publish after our explanation (we won't dispute good-faith reports)

---

## Security Scope & Boundaries

### In Scope

✅ **These are valid security concerns:**
- **Code execution vulnerabilities** in Python scripts, systemd units, shell scripts
- **Path traversal** in tarfile extraction, bundle deployment, file operations
- **Command injection** in subprocess calls (even if shell=True not found)
- **Secrets exposure** in logs, error messages, or committed code
- **Network exposure** of services intended for localhost only (vLLM, Weaviate)
- **Dependency vulnerabilities** with known exploits (CVEs)
- **Model artifact tampering** if checksums can be bypassed
- **Privilege escalation** via systemd units or file permissions
- **Denial of service** in inference pipeline or deployment scripts

### Out of Scope

❌ **These are NOT security vulnerabilities:**
- **Physical access attacks** (assumes attacker already has shell access)
- **Social engineering** of users to run malicious commands
- **Model quality issues** (incorrect answers, hallucinations)
- **Performance issues** that don't lead to resource exhaustion DoS
- **UI/UX issues** in scripts or logs (unless they leak secrets)
- **Third-party service vulnerabilities** (e.g., bugs in OpenAI API, unless we misuse it)
- **Theoretical attacks** without proof-of-concept (e.g., "maybe someone could...")

### Trust Boundaries

Milton operates with these trust assumptions:
1. **User is trusted:** You have full control of your machine and `.env` file
2. **Downloaded models are trusted:** HuggingFace is assumed to be a safe source
3. **Local network is trusted:** Services bind to 127.0.0.1 by default (no authentication)
4. **Filesystem is trusted:** No sandboxing of Python execution (runs as your user)

If your threat model differs (e.g., multi-user system, untrusted network), see [Hardening Guide](#hardening-for-multi-user-environments).

---

## Security Features

### 1. Localhost-Only Services (Default)

**vLLM Inference Server:**
- Binds to `127.0.0.1:8000` (not `0.0.0.0`)
- Optional API key via `VLLM_API_KEY` environment variable
- No hardcoded credentials in source code

**Weaviate Vector Database:**
- Docker Compose binds to `127.0.0.1:8080` and `127.0.0.1:50051`
- Override with `WEAVIATE_BIND_HOST=0.0.0.0` (opt-in for LAN exposure)
- No authentication enabled by default (assumes trusted local access)

### 2. Safe Archive Extraction

All tarfile operations use `safe_tar_extract()` which:
- Rejects absolute paths (`/etc/passwd`)
- Rejects path traversal (`../../sensitive/file`)
- Rejects symlinks and special files
- Compatible with Python 3.10-3.14+ (`filter='data'` on 3.12+)

**Location:** `deployment/deployment_manager.py:22-61`

### 3. Model Bundle Integrity

Edge bundles include:
- **SHA256 checksums** for all files (computed at bundle creation)
- **Manifest validation** before deployment (`_verify_checksums()`)
- **Loud failures** if checksums mismatch (deployment aborts)

**Artifact types:**
- `gguf`: Single quantized model file (~4.4 GB, fast)
- `hf-distilled`: Full HuggingFace directory (~15 GB, slow)

### 4. Environment Variable Security

- **`.env` file:** Must have `600` permissions (owner read/write only)
- **Gitignored:** `.env`, `/secrets/`, `*.key`, `*.pem`, `credentials.json`
- **No silent fallbacks:** Scripts fail loudly if required env vars missing
- **Secret redaction:** Training data export strips API keys and tokens

### 5. systemd Hardening

Service units include:
- `NoNewPrivileges=true` (prevents privilege escalation)
- `PrivateTmp=true` (isolated /tmp directory)
- `ProtectSystem=strict` (read-only /usr, /boot, /efi)
- `ProtectHome=read-only` (minimal write access via `ReadWritePaths`)
- Resource limits: `MemoryMax=8G`, `CPUQuota=400%`

**Location:** `systemd/*.service`

---

## Dependency Security

### Dependabot Integration

Milton uses **GitHub Dependabot** for automated dependency updates:
- **Python dependencies:** Monitored via `requirements.txt` and `pyproject.toml`
- **JavaScript dependencies:** Monitored via `milton-dashboard/package.json`
- **Update frequency:** Weekly scans for vulnerabilities
- **Auto-merge:** Low-risk updates (patch versions) auto-merged after CI passes

### Current Dependency Status

**Python (verified 2026-01-11):**
- ✅ `requests==2.32.5` (safe, > 2.32.0 CVE fix)
- ✅ `pydantic==2.12.5` (no known CVEs)
- ✅ `flask>=3.0.0` (no high-severity CVEs)
- ✅ `pyyaml>=6.0` (safe if using `yaml.safe_load()` - verified)
- ⚠️ `torch`, `vllm`: Large ML packages - monitor security advisories

**JavaScript:**
- ✅ `esbuild`: Fixed (Dependabot alert #1 resolved in commit b2206a5)

### Manual Audit Policy

- **Quarterly audits:** Full dependency review every 3 months
- **ML package monitoring:** Monthly checks of `torch`, `vllm`, `transformers` CVEs
- **Immediate response:** Critical CVEs patched within 24 hours

---

## Hardening for Multi-User Environments

If running Milton on a **shared system** or **untrusted network**, apply these hardening measures:

### 1. Enable vLLM Authentication
```bash
# Generate secure API key
VLLM_API_KEY=$(openssl rand -base64 32)
echo "VLLM_API_KEY=$VLLM_API_KEY" >> .env

# Restart vLLM
systemctl --user restart milton-orchestrator
```

### 2. Enable Weaviate Authentication
```yaml
# docker-compose.yml
environment:
  AUTHENTICATION_APIKEY_ENABLED: 'true'
  AUTHENTICATION_APIKEY_ALLOWED_KEYS: 'your-secret-key-here'
```

### 3. Restrict File Permissions
```bash
chmod 700 ~/.local/state/milton  # Owner-only access
chmod 600 .env                    # Already enforced
chmod 700 scripts/*.py            # Prevent tampering
```

### 4. Network Isolation
If exposing services to network:
- Use **firewall rules** to restrict access (e.g., `ufw allow from 192.168.1.0/24`)
- Use **reverse proxy** with TLS (e.g., nginx + Let's Encrypt)
- Enable **authentication** on all endpoints (vLLM, Weaviate)

### 5. systemd Sandboxing (Advanced)
Add to service units:
```ini
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictRealtime=true
RestrictNamespaces=true
```

---

## Security Checklist Before Release

Use this checklist when preparing a new release:

- [ ] **Dependency scan:** Run `pip-audit` and `npm audit` (0 high/critical vulnerabilities)
- [ ] **Secret scan:** Verify no hardcoded API keys (`rg -i "api[_-]?key.*=.*['\"][a-z0-9]{20,}"`)
- [ ] **Test suite:** All security tests pass (`pytest tests/test_*_security.py`)
- [ ] **.env.example:** Updated with all required variables
- [ ] **CHANGELOG:** Security fixes documented with CVE/advisory links
- [ ] **Permissions:** `.env` has `600`, scripts have `755` or `644`
- [ ] **Docker Compose:** Weaviate binds to `127.0.0.1` by default
- [ ] **systemd units:** All have `NoNewPrivileges=true` and `PrivateTmp=true`
- [ ] **Documentation:** Security policy and hardening guide up-to-date

---

## Security Audit History

| Date | Type | Findings | Report |
|------|------|----------|--------|
| 2026-01-11 | Internal | 1 MEDIUM, 2 LOW, 1 INFO | [SECURITY_AUDIT_REPORT.md](SECURITY_AUDIT_REPORT.md) |

**Key Findings Resolved:**
- ✅ Hardcoded API key removed (scripts/start_vllm.py, scripts/health_check.py)
- ✅ Weaviate bound to localhost by default (docker-compose.yml)
- ✅ Tarfile path traversal protection (deployment/deployment_manager.py)

**Next Audit:** Q2 2026 (April-June)

---

## References

- **Secure Deployment Guide:** [docs/DEPLOYMENT_QUICKSTART.md](docs/DEPLOYMENT_QUICKSTART.md)
- **Phase 4 Architecture:** [docs/PHASE4_COMPLETE.md](docs/PHASE4_COMPLETE.md)
- **Security Audit Report:** [SECURITY_AUDIT_REPORT.md](SECURITY_AUDIT_REPORT.md)
- **Python Security Best Practices:** https://python.readthedocs.io/en/stable/library/security_warnings.html
- **OWASP Cheat Sheets:** https://cheatsheetseries.owasp.org/

---

## Contact

For **security issues only**, use private reporting channels above.

For **general questions**, open a GitHub issue or discussion.

**Maintainer Response Time:**
- Security reports: 48 hours
- Bug reports: 1 week
- Feature requests: Best effort

---

**Last Updated:** 2026-01-11  
**Policy Version:** 1.0
