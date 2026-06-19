# Local authenticated demo (Keycloak + oauth2-proxy + Freelens)

Exercise the **real authenticated flow** on your machine: OIDC login, identity
propagation and the `proxy`-mode guard — no Kubernetes cluster required to log in.

```
Browser ─▶ oauth2-proxy :4180 ─▶ Freelens :8050 (FREELENS_AUTH_MODE=proxy)
               │ OIDC
               ▼
           Keycloak :8080
```

## Run

```bash
docker compose -f deploy/local/docker-compose.yml up --build
# or: make compose-up
```

Wait ~30–60 s for Keycloak to import its realm, then open **http://localhost:4180**
and log in:

| user  | password |
|-------|----------|
| alice | password |

`alice` is a member of the `freelens-viewers` group, forwarded to Freelens as the
`X-Forwarded-Groups` header and used for Kubernetes impersonation.

Stop it with `make compose-down` (or `Ctrl-C` then `docker compose ... down`).

## What it proves

- Unauthenticated requests are redirected to Keycloak; Freelens is never reachable
  without a valid identity (direct hits are `401`).
- After login, oauth2-proxy forwards `X-Forwarded-Preferred-Username` / `-Email` /
  `-Groups`; Freelens accepts them **only** because the request comes from the
  trusted compose subnet (`FREELENS_TRUSTED_PROXIES`).
- The Keycloak admin console is on http://localhost:8080 (`admin` / `admin`).

## Connect a real cluster (optional)

A container can't reach a **kind** cluster via the host loopback the normal
kubeconfig points at. Attach Freelens to kind's docker network and use the
*internal* kubeconfig — `docker-compose.kind.yml` does exactly that:

```bash
kind get kubeconfig --internal --name freelens-test > /tmp/freelens-kind.kubeconfig
docker compose -f deploy/local/docker-compose.yml \
               -f deploy/local/docker-compose.kind.yml up --build
```

For a **remote** cluster, just mount its kubeconfig (uncomment the `KUBECONFIG`
env and `volumes` block for the `freelens` service in `docker-compose.yml`).

## Not for production

This compose uses HTTP, demo secrets and a dev-mode Keycloak. For a real
deployment see [`../hds/`](../hds/) (TLS, secrets from a vault, hardened pods).
