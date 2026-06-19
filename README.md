# Freelens

A lightweight, web-based Kubernetes cluster explorer built with [Dash](https://dash.plotly.com/),
inspired by [Lens](https://k8slens.dev/).

## Features

- Browse cluster resources from a Lens-style sidebar.
- Filter by namespace, free-text search, and **native column sorting / filtering**.
- Connection status badge, active-context label and live row counter.
- **Auto-refresh** (toggle) plus a manual refresh button.
- Resource detail panel with **Overview / YAML / Logs / Exec** tabs. Logs have a
  line filter and a download button; **Exec** opens a real interactive terminal
  (TTY) into the pod via xterm.js over a WebSocket.
- **Write actions** with confirmation: scale & restart Deployments, delete Pods.
- **Multi-select delete**: checkboxes on every row delete many resources at once
  (selection resets when you switch resource type).
- **Helm** page: list releases, deploy charts (with custom values), inspect
  values / history / manifest, and roll back or uninstall — all via the `helm` CLI.
  A built-in **catalog** of popular charts (MetalLB, ingress-nginx, cert-manager,
  Prometheus, Grafana, Argo CD, …) one-click pre-fills the deploy form.
- **Custom Resources** page: CRDs are discovered live (operators installed while
  the app runs show up without a restart); pick a type to list its instances and
  view any instance's manifest.
- 14 resource types implemented out of the box:
  Pods, Deployments, DaemonSets, StatefulSets, ReplicaSets, Jobs, CronJobs,
  Services, ConfigMaps, Secrets, PersistentVolumeClaims, PersistentVolumes,
  Nodes, Namespaces. More are easy to add — see below.

## Requirements

- Python 3.10+ (`flask-sock` enables the pod terminal; the xterm.js front-end is
  served locally from `assets/vendor/`, so no internet access is required).
- Access to a Kubernetes cluster via a local `kubeconfig` or in-cluster credentials.
- The [`helm`](https://helm.sh/) CLI on `PATH` (optional — only for the Helm page).

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
python app.py
```

Then open http://127.0.0.1:8050.

Configuration is via environment variables (see `freelens/config.py`):
`FREELENS_HOST`, `FREELENS_PORT`, `FREELENS_DEBUG`, `FREELENS_TABLE_PAGE_SIZE`.

## Security & authentication

> ⚠️ By default `FREELENS_AUTH_MODE=disabled` — **no authentication**, for local
> development only. The app gives full control over the cluster to anyone who can
> reach the port.

For any shared, remote or **health-data (HDS)** deployment, run behind an
authenticating OIDC reverse proxy and set `FREELENS_AUTH_MODE=proxy`. Freelens
then requires a per-user identity, propagates it to the Kubernetes API server via
impersonation (so RBAC and audit attribute every action to the real person), and
writes a JSON audit trail. See [`SECURITY_AUDIT_HDS.md`](./SECURITY_AUDIT_HDS.md),
[`SECURITY_AUTH_DESIGN.md`](./SECURITY_AUTH_DESIGN.md) and the ready-to-apply
manifests in [`deploy/hds/`](./deploy/hds/).

As a safety net, the app **refuses to start** in `disabled` mode when bound to a
non-loopback address (set `FREELENS_ALLOW_INSECURE=true` to override on an
already-isolated network).

Auth-related variables: `FREELENS_AUTH_MODE` (`disabled`|`proxy`),
`FREELENS_TRUSTED_PROXIES`, `FREELENS_HEADER_USER/EMAIL/GROUPS`,
`FREELENS_IMPERSONATE`, `FREELENS_SECRET_KEY`, `FREELENS_ALLOWED_ORIGINS`,
`FREELENS_AUDIT_FILE`, `FREELENS_ALLOW_INSECURE`.

## Container

A hardened multi-stage image is provided (non-root uid 65532, pinned +
checksum-verified `helm`, read-only-rootfs friendly, `/healthz` healthcheck).
The image **defaults to `FREELENS_AUTH_MODE=proxy`** — secure by default; without
a proxy in front every request is `401`.

```bash
make docker-build                     # build freelens:latest
make docker-run                       # local smoke test (disabled mode, loopback)
```

For a real deployment behind oauth2-proxy, see [`deploy/hds/`](./deploy/hds/).

## Local test cluster (KinD)

No cluster handy? Spin up a local [KinD](https://kind.sigs.k8s.io/) cluster
seeded with sample workloads (requires `kind`, `kubectl` and a running Docker):

```bash
make kind-up      # create cluster 'freelens-test' + deploy deploy/sample.yaml
make run          # browse the seeded pods/deployments in the 'demo' namespace
make kind-down    # tear the cluster down
```

`make kind-up` sets your kubeconfig's active context to `kind-freelens-test`.

## Make targets

Run `make help` to list everything: `install`, `dev`, `run`, `test`, `clean`,
`kind-up`, `kind-seed`, `kind-down`.

## Architecture

The app is **declarative**: every resource type is described once in
`freelens/k8s/registry.py` as a `ResourceDescriptor`. The sidebar, URL routing,
table columns and detail panel are all generated from that registry, so the UI
and callback code stay generic.

```
app.py                     # entry point
freelens/
  config.py                # settings (env-overridable)
  terminal.py              # xterm.js page + WebSocket bridge to pod exec (TTY)
  k8s/
    client.py              # cached Kubernetes API clients (core/apps/batch) + context
    formatters.py          # shared display helpers (age, labels, ...)
    operations.py          # YAML rendering, pod logs, scale/restart/delete
    helm.py                # Helm CLI wrapper (list/install/upgrade/rollback/...)
    helm_catalog.py        # curated catalog of popular charts (pre-fill deploy form)
    crd.py                 # CRD discovery + dynamic custom-resource access
    registry.py            # ResourceDescriptor registry + sidebar menu
  ui/
    sidebar.py             # sidebar generated from the registry
    components.py          # generic detail / YAML / logs / action builders
    layout.py              # page shell with one reusable table + detail tabs
  callbacks/
    navigation.py          # collapsible groups + URL-driven view switching
    data.py                # generic data loading, status/context/auto-refresh
    details.py             # selection tracking, Overview/YAML/Logs tabs
    actions.py             # write actions: button -> confirm -> execute
    helm.py                # Helm page: list/deploy/inspect/rollback/uninstall
    crd.py                 # Custom Resources page: discover CRDs, list instances
```

## Adding a resource type

Add a `ResourceDescriptor` to `freelens/k8s/registry.py` and reference its key in
`MENU`. Define its `columns`, `detail_fields`, and the `list_fn` / `get_fn`
Kubernetes API calls — no layout or callback changes required.
