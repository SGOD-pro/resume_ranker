# Per-Session Rate Limit Bypass Limitation & Mitigation Strategy

## Executive Summary
In the v2.2 dev stack, `POST /api/v2/jobs` enforces a limit of **20 jobs per session per day** using a `session_id` transmitted via HTTP cookie or header. While this provides immediate protection against accidental client loops or well-behaved duplicate invocations, **client-controlled session identifiers are bypassable** by an adversarial user.

---

## 1. Vulnerability Analysis

### Root Cause
1. **Client-Controlled Identity**: If `session_id` is supplied by the browser (via cookie or header) and the endpoint does not require cryptographically verified authentication (e.g. signed JWT or authenticated user record in DynamoDB), a client can rotate session IDs arbitrarily:
   ```bash
   curl -H "Cookie: session_id=$(uuidgen)" http://localhost:8000/api/v2/jobs ...
   ```
2. **DynamoDB Partitioning**: The rate limit is tracked using `PK = SESSION#{session_id}, SK = METRICS#{YYYY-MM-DD}`. Rotating the session ID creates a new partition key, resetting the counter to 0.

---

## 2. Multi-Layer Defense in Depth (Current Protections)

Even if a malicious actor rotates session IDs, the system is protected by downstream architectural barriers:

| Layer | Mechanism | Protection |
| :--- | :--- | :--- |
| **L1: API Gateway Throttling** | `rate_limit = 20 req/s, burst = 50` | Prevents rapid-fire automated flooding regardless of session ID. |
| **L2: S3 File Size Constraints** | `content-length-range 1..10485760` | Enforces 10 MB maximum payload per file at the S3 bucket edge. |
| **L3: Batch File Limit** | Max 100 files per job | Blocks massive file batch exhaustion attacks. |
| **L4: Atomic Global Daily LLM Cap** | DynamoDB conditional counter | Caps expensive Bedrock invocations globally per day. |
| **L5: AWS Budgets Alarm** | $15.00/month threshold (80%) | Triggers SNS notifications and operational alerts before budget exhaustion. |

---

## 3. Production Remediation Plan (Phase 3 Authentication)

To make rate limiting cryptographically non-bypassable:
1. **Authenticated User Scoping**: Replace `session_id` with `user_id` and `org_id` verified via signed, httpOnly, secure session tokens (JWT or server-side session store).
2. **DynamoDB Tenant Partitioning**: Rate limit key changes to:
   `PK = ORG#{org_id}, SK = RATE_LIMIT#JOBS#{YYYY-MM-DD}`.
3. **AWS WAF Client IP Throttling**: Configure AWS WAF with an IP-based rate limiting rule (e.g., max 100 requests per 5 minutes per IP address) at the API Gateway v2 stage.
4. **Anonymous ATS Check Isolation**: The candidate-facing ATS checker route (`/api/v2/ats-check`) must use strict IP-based DynamoDB token bucket limiting with AWS WAF IP reputation lists.
