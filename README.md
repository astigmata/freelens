# Freelens

A lightweight, web-based Kubernetes cluster explorer built with [Dash](https://dash.plotly.com/),
inspired by [Lens](https://k8slens.dev/).

## Features

- Browse cluster resources from a Lens-style sidebar.
- Filter by namespace, free-text search, and **native column sorting / filtering**.
- Connection status badge, active-context label and live row counter.
- **Auto-refresh** (toggle) plus a manual refresh button.
- Resource detail panel with **Overview / YAML / Logs** tabs.
- **Write actions** with confirmation: scale & restart Deployments, delete Pods.
- **Helm** page: list releases, deploy charts (with custom values), inspect
  values / history / manifest, and roll back or uninstall — all via the `helm` CLI.
- **Custom Resources** page: CRDs are discovered live (operators installed while
  the app runs show up without a restart); pick a type to list its instances and
  view any instance's manifest.
- 14 resource types implemented out of the box:
  Pods, Deployments, DaemonSets, StatefulSets, ReplicaSets, Jobs, CronJobs,
  Services, ConfigMaps, Secrets, PersistentVolumeClaims, PersistentVolumes,
  Nodes, Namespaces. More are easy to add — see below.

## Requirements

- Python 3.10+
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
  k8s/
    client.py              # cached Kubernetes API clients (core/apps/batch) + context
    formatters.py          # shared display helpers (age, labels, ...)
    operations.py          # YAML rendering, pod logs, scale/restart/delete
    helm.py                # Helm CLI wrapper (list/install/upgrade/rollback/...)
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
