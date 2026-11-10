# JobPilot — Security, Privacy & Reliability Architecture

**Document Status:** Comprehensive Threat Model & Defense Specification  
**Security Standard:** Defense-in-Depth, Zero-Trust External Content, Strict Candidate Consent  
**Compliance Mandate:** No anti-bot bypass, no automated submissions, zero exposure of private infrastructure.

---

## 1. Threat Modeling & Attack Surface Overview

JobPilot interacts with external web servers, parses untrusted candidate documents, and assists with external job applications. The primary threat vectors addressed in this security specification are:
1. **Server-Side Request Forgery (SSRF):** Malicious career URLs designed to probe internal networks, AWS/GCP cloud metadata endpoints (`169.254.169.254`), or Docker container internals.
2. **DNS Rebinding Attacks:** Attackers configuring public DNS domains that resolve initially to legitimate public IPs and subsequently rebind to private IP addresses.
3. **Malicious File Uploads:** Uploaded resumes containing PDF exploit payloads, polyglot executables, decompression bombs, or script injections.
4. **Untrusted Web Content & Indirect Prompt Injection:** Scraped job descriptions containing hidden control sequences designed to alter extraction logic or compromise system integrity.
5. **Unauthorized Automated Actions & Spam:** Automated spamming of recruiters or accidental submission of erroneous applications without candidate consent.
6. **Multi-Tenant Data Leakage:** Unauthorized cross-tenant data access between registered candidates or privilege escalation to admin status.

---

## 2. SSRF, DNS Rebinding & Redirect Defense

Any discovery request triggered by a user-supplied career URL must traverse the **JobPilot Secure Fetch Gateway**:

```
[ User-Supplied Career URL ]
             │
             ▼
+───────────────────────────────────────────+
| 1. URL Structure & Protocol Validation    |
|    - Protocol MUST be http:// or https:// |
|    - Port MUST be 80 or 443               |
|    - User-info (@) explicitly forbidden   |
+────────────────────┬──────────────────────+
                     │
                     ▼
+───────────────────────────────────────────+
| 2. Pre-Flight DNS Resolution              |
|    - Resolve target hostname to all IPv4  |
|      and IPv6 socket addresses            |
+────────────────────┬──────────────────────+
                     │
                     ▼
+───────────────────────────────────────────+
| 3. Private & Reserved IP Filter Gate      |
|    - 10.0.0.0/8 (RFC 1918)                |
|    - 172.16.0.0/12 (RFC 1918)             |
|    - 192.168.0.0/16 (RFC 1918)            |
|    - 127.0.0.0/8 (Loopback)               |
|    - 169.254.0.0/16 (Link-Local & Cloud)  |
|    - ::1 (IPv6 Loopback), fe80::/10       |
|    - 169.254.169.254 (Cloud Metadata)     |
|                                           |
|    [FAIL] -> Block Request Immediately.   |
+────────────────────┬──────────────────────+
                     │
               [IP VERIFIED]
                     │
                     ▼
+───────────────────────────────────────────+
| 4. Socket Connection Pinning              |
|    - Direct socket connection pinned to   |
|      the exact verified IP address        |
|    - Eliminates DNS Rebinding Vulnerability|
+────────────────────┬──────────────────────+
                     │
                     ▼
+───────────────────────────────────────────+
| 5. Redirect Re-Validation Loop            |
|    - Every HTTP 301/302/307/308 redirect  |
|      MUST re-execute steps 1 through 4    |
|    - Max redirects bounded: <= 5 hops     |
+───────────────────────────────────────────+
```

---

## 3. File Upload & Document Parsing Security

Resumes uploaded to JobPilot are treated as untrusted binary streams:
1. **Magic Byte Verification:** File header must start with `%PDF-` (bytes `0x25 0x50 0x44 0x46 0x2D`). Files disguised with `.pdf` extensions but containing executable or script headers are rejected immediately (`HTTP 415`).
2. **File Size Hard Limit:** Enforced at the streaming gateway ($\le 5$ MB). Chunked reads abort as soon as byte limits are exceeded.
3. **PyMuPDF Sandboxed Parsing:**
   - PDF opened in a transient memory buffer.
   - Password protection test (`doc.needs_pass`) prevents infinite hangs.
   - Page count bounds strictly enforced (1 to 15 pages).
4. **Secure File Storage:**
   - Server-assigned UUID file naming (`resumes/{uuid4}.pdf`).
   - Never use original client-supplied filenames on disk, preventing directory traversal (`../../etc/passwd`).
   - User files stored in isolated tenant directories (`/data/users/{user_id}/resumes/`).

---

## 4. Browser Extension Permission Model & Form Safety

The **Fill with JobPilot** Manifest V3 extension adheres to strict user safety principles:
1. **Minimal Host Permissions:** Uses active tab inspection and scoped ATS platform match patterns (`*://boards.greenhouse.io/*`, `*://jobs.lever.co/*`, `*://jobs.ashbyhq.com/*`).
2. **Strict User-Controlled Assistance:**
   - The extension assists with filling profile fields (Name, Email, Phone, LinkedIn, verified answers).
   - **No Anti-Bot Bypass:** The extension does not attempt to detect, bypass, or tamper with anti-bot mechanisms, Cloudflare challenges, or hidden honeypot fields.
   - **No Automated Form Submission:** The extension explicitly refuses to trigger form submission events or click submit buttons. The candidate must visually verify all data and click Submit manually.
3. **Sensitive Field Guards:** Fields relating to race, gender, veteran status, disability, or consent checkboxes are never filled automatically.

---

## 5. Recruiter Email Dispatching & Anti-Spam Controls

When executing application assistance via Route C (Recruiter Email):
1. **Verified Domain Association:** Recruiter email addresses must be explicitly published on the verified job description or official careers portal. JobPilot **never guesses** email patterns.
2. **Explicit Candidate Consent:** An application email is **never** sent automatically. The candidate is shown the exact recipient, subject, body, and attached resume, and must click "Send Application Email" explicitly.
3. **Rate Limiting & Throttling:**
   - Strict throttle: Maximum 5 recruiter emails per hour per user.
   - Prevents accidental spamming or abuse of candidate SMTP credentials.
4. **Transport Security:** SMTP connections enforce TLS (`STARTTLS` or SSL on port 465/587) with certificate verification.

---

## 6. Multi-Tenant Data Isolation & RBAC

1. **Relational Isolation:** Every query on user-owned tables (`applications`, `resumes`, `candidate_profiles`, `saved_searches`, `interviews`, `offers`) explicitly filters on `user_id == current_user.id`.
2. **Cryptographic Token Security:**
   - JWT Access Tokens: Valid for 15 minutes, signed with HS256 using a high-entropy secret (`JWT_SECRET`).
   - Refresh Tokens: Stored in the database exclusively as **SHA-256 hashes**.
   - Token Family Rotation: Using a revoked refresh token triggers immediate automatic invalidation of the entire token family, neutralizing stolen token replays.
3. **Admin RBAC Enforcement:**
   - Admin routes (`/api/v1/admin/*`) strictly enforce the `CurrentAdmin` dependency (`user.role == 'admin'`).
   - Live verified: Non-admin users attempting to access admin routes receive a `403 Forbidden` response.
4. **Immutable Security Audit Log:**
   - All critical actions (Logins, Role Changes, User Deactivation, Invite Generation, Application Dispatches, Account Deletions) record the actor, timestamp, event type, and client IP address in `audit_logs`.
5. **Self-Service Account Erasure:**
   - Account deletion requires entering the user's password.
   - Cascades zero-residue deletion across all relational records, physical resumes, and stored artifacts.
