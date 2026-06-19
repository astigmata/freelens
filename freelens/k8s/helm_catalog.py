"""A small curated catalog of popular Helm charts, ready to install.

Saves pasting the chart name / repo URL by hand for the well-known ones. Every
entry here was verified to resolve via ``helm show chart <chart> --repo <url>``.
Versions are intentionally NOT pinned: leaving the version blank installs the
latest, so the catalog doesn't go stale. The user can still override anything in
the form before installing.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class CatalogEntry:
    key: str
    label: str
    description: str
    chart: str
    repo_url: str
    release: str
    namespace: str


# Kept to OSS infra/networking/observability charts whose images pull freely
# (Bitnami app charts are deliberately excluded — their images moved to a
# restricted registry, so installs would fail).
CATALOG: tuple[CatalogEntry, ...] = (
    CatalogEntry(
        "metallb", "MetalLB", "Bare-metal load-balancer for Kubernetes",
        "metallb", "https://metallb.github.io/metallb", "metallb", "metallb-system",
    ),
    CatalogEntry(
        "ingress-nginx", "ingress-nginx", "NGINX-based Kubernetes ingress controller",
        "ingress-nginx", "https://kubernetes.github.io/ingress-nginx",
        "ingress-nginx", "ingress-nginx",
    ),
    CatalogEntry(
        "haproxy-ingress", "HAProxy Ingress", "HAProxy Kubernetes ingress controller",
        "kubernetes-ingress", "https://haproxytech.github.io/helm-charts",
        "haproxy", "haproxy-controller",
    ),
    CatalogEntry(
        "traefik", "Traefik", "Cloud-native ingress controller / reverse proxy",
        "traefik", "https://traefik.github.io/charts", "traefik", "traefik",
    ),
    CatalogEntry(
        "cert-manager", "cert-manager", "X.509 certificate management for Kubernetes",
        "cert-manager", "https://charts.jetstack.io", "cert-manager", "cert-manager",
    ),
    CatalogEntry(
        "prometheus", "Prometheus", "Monitoring system & time-series database",
        "prometheus", "https://prometheus-community.github.io/helm-charts",
        "prometheus", "monitoring",
    ),
    CatalogEntry(
        "kube-prometheus-stack", "kube-prometheus-stack",
        "Prometheus + Grafana + Alertmanager, all-in-one",
        "kube-prometheus-stack", "https://prometheus-community.github.io/helm-charts",
        "kube-prometheus-stack", "monitoring",
    ),
    CatalogEntry(
        "grafana", "Grafana", "Dashboards & visualization",
        "grafana", "https://grafana.github.io/helm-charts", "grafana", "monitoring",
    ),
    CatalogEntry(
        "loki", "Loki", "Log aggregation system",
        "loki", "https://grafana.github.io/helm-charts", "loki", "logging",
    ),
    CatalogEntry(
        "argo-cd", "Argo CD", "Declarative GitOps continuous delivery",
        "argo-cd", "https://argoproj.github.io/argo-helm", "argocd", "argocd",
    ),
    CatalogEntry(
        "external-secrets", "External Secrets", "Sync secrets from external stores",
        "external-secrets", "https://charts.external-secrets.io",
        "external-secrets", "external-secrets",
    ),
    CatalogEntry(
        "vault", "HashiCorp Vault", "Secrets management & data protection",
        "vault", "https://helm.releases.hashicorp.com", "vault", "vault",
    ),
    CatalogEntry(
        "jenkins", "Jenkins", "Automation server for CI/CD",
        "jenkins", "https://charts.jenkins.io", "jenkins", "jenkins",
    ),
)

CATALOG_BY_KEY: dict[str, CatalogEntry] = {e.key: e for e in CATALOG}
