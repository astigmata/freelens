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

Uncomment the `KUBECONFIG` env and `volumes` block for the `freelens` service in
`docker-compose.yml`. For a local kind/minikube cluster you also need network
reachability from the container (e.g. host networking, or rewrite the kubeconfig
server to `host.docker.internal`).

## Not for production

This compose uses HTTP, demo secrets and a dev-mode Keycloak. For a real
deployment see [`../hds/`](../hds/) (TLS, secrets from a vault, hardened pods).
