# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in the A2A Payment Protocol specification or reference implementation, please report it responsibly.

**Email:** [security@tfsfventures.com](mailto:security@tfsfventures.com)

Please include:
- Description of the vulnerability
- Steps to reproduce
- Potential impact assessment
- Suggested fix (if any)

**Do not** open a public GitHub issue for security vulnerabilities.

---

## Scope

### In Scope

- Authorization bypass in the four-stage pipeline
- Data exposure through API endpoints or webhook payloads
- Webhook verification bypass or replay attacks
- Escrow manipulation (unauthorized release, funding, or state transitions)
- Spending policy circumvention
- Rate limiting bypass

### Out of Scope

- Social engineering attacks against personnel
- Denial of service (DDoS) attacks
- Vulnerabilities in third-party dependencies (report to upstream)
- Physical security of infrastructure

---

## Response Timeline

| Action | Timeframe |
|--------|-----------|
| Acknowledgement | 24 hours |
| Triage & severity assessment | 72 hours |
| Status update to reporter | 7 days |
| Fix for critical vulnerabilities | 30 days |
| Fix for non-critical vulnerabilities | 90 days |

---

## Recognition

We believe in recognizing security researchers who help keep the protocol safe. With your permission, we will acknowledge your contribution in our security advisories.

---

## Contact

**TFSF Ventures FZ-LLC**
RAKEZ License 47013955
Ras Al Khaimah, UAE

[security@tfsfventures.com](mailto:security@tfsfventures.com)
