# HDS-ready deployment

Reference manifests to run Freelens with the controls an HDS / health-data
context requires: **authentication**, **per-user imputability**, **encryption in
transit**, **least privilege** and an **audit trail**.

## Architecture

```
          TLS                      loopback (trusted)
Browser ───────▶ Ingress ─▶ oauth2-proxy ──────────────▶ Freelens ─┐
  │  OIDC login          (sidecar, :4180)   X-Forwarded-*  :8050 │
  │                                                                 │ Impersonate-User/-Group
  └────────────────────────────────────────────────── Kubernetes API server
                                                       (enforces user RBAC,
                                                        audits the real actor)
```

- **oauth2-proxy** performs the OIDC login and injects `X-Forwarded-Preferred-Username`,
  `-Email`, `-Groups`. It talks to Freelens over loopback inside the pod.
- **Freelens** runs with `FREELENS_AUTH_MODE=proxy` and trusts those headers only
  from `127.0.0.1`, so they cannot be forged from outside the pod. Every request
  without a valid identity gets `401`; cross-origin state-changing requests get
  `403`.
- **Impersonation**: Freelens forwards the user to the API server, which applies
  that user's RBAC and logs the real actor. The app's ServiceAccount can *only*
  impersonate (`01-rbac.yaml`).
- **Audit**: a JSON audit event per sensitive action (delete/scale/exec/secret
  read/helm…) is written to stdout — ship it to an immutable sink.

## Apply

```bash
kubectl create namespace freelens
# Fill the Secrets in 03-ingress.yaml from your vault first.
kubectl apply -f 01-rbac.yaml -f 02-freelens.yaml -f 03-ingress.yaml
```

## Checklist before handling health data

- [ ] OIDC IdP enforces MFA and password policy for Freelens users.
- [ ] End-user RBAC bound to OIDC groups, scoped to least privilege (per
      namespace / team). The app SA only has `impersonate`.
- [ ] TLS certificate provisioned (cert-manager) and HSTS on at the edge.
- [ ] Audit stream shipped to an append-only/immutable store with defined
      retention; access to the audit store is itself restricted and logged.
- [ ] Cluster API-server audit logging enabled (records the impersonated actor).
- [ ] Network policy restricts who can reach the Ingress.
- [ ] `FREELENS_DEBUG=false` (never enable the Werkzeug debugger in production).
- [ ] Rate limiting / WAF at the Ingress.
- [ ] Hosting on an HDS-certified infrastructure.

See [`../../SECURITY_AUDIT_HDS.md`](../../SECURITY_AUDIT_HDS.md) and
[`../../SECURITY_AUTH_DESIGN.md`](../../SECURITY_AUTH_DESIGN.md) for the rationale.
