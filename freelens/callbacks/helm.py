"""Helm page: listing releases, deploying charts and rollback / uninstall.

Mirrors the resource explorer's flow (select a row -> detail tabs; action button
-> confirmation -> execution) but talks to the ``helm`` CLI instead of the
Kubernetes API, so it lives in its own module rather than the registry.
"""

import logging

from dash import ALL, Dash, Input, Output, State, ctx, html, no_update
from dash.exceptions import PreventUpdate

from ..k8s import helm
from ..ui.components import (
    helm_placeholder,
    render_helm_actions,
    render_helm_history,
    render_helm_manifest,
    render_helm_values,
)

log = logging.getLogger(__name__)

HELM_PATH = "/helm"


def register(app: Dash) -> None:
    @app.callback(
        Output("helm-table", "data"),
        Output("helm-row-count", "children"),
        Output("helm-status", "children"),
        Input("url", "pathname"),
        Input("helm-refresh", "n_clicks"),
        Input("helm-refresh-trigger", "data"),
        Input("helm-interval", "n_intervals"),
    )
    def load_releases(pathname, _refresh, _trigger, _tick):
        if (pathname or "") != HELM_PATH:
            raise PreventUpdate
        if not helm.available():
            return [], "", "The 'helm' CLI was not found on PATH."
        try:
            releases = helm.list_releases("all")
        except helm.HelmError as exc:
            return [], "", f"Error: {exc}"

        rows = [
            {
                "name": r.get("name", ""),
                "namespace": r.get("namespace", ""),
                "revision": r.get("revision", ""),
                "status": r.get("status", ""),
                "chart": r.get("chart", ""),
                "app_version": r.get("app_version", ""),
                "updated": r.get("updated", ""),
            }
            for r in releases
        ]
        count = f"{len(rows)} release{'s' if len(rows) != 1 else ''}"
        return rows, count, ""

    @app.callback(
        Output("helm-interval", "disabled"),
        Input("helm-autorefresh-toggle", "value"),
    )
    def toggle_helm_autorefresh(value):
        return "on" not in (value or [])

    @app.callback(
        Output("helm-deploy-form", "style"),
        Input("helm-deploy-toggle", "n_clicks"),
        State("helm-deploy-form", "style"),
        prevent_initial_call=True,
    )
    def toggle_deploy_form(_n, style):
        style = dict(style or {})
        style["display"] = "none" if style.get("display") == "block" else "block"
        return style

    @app.callback(
        Output("helm-install-result", "children"),
        Output("helm-refresh-trigger", "data"),
        Input("helm-install-btn", "n_clicks"),
        State("helm-f-release", "value"),
        State("helm-f-chart", "value"),
        State("helm-f-repo", "value"),
        State("helm-f-version", "value"),
        State("helm-f-namespace", "value"),
        State("helm-f-values", "value"),
        State("helm-f-createns", "value"),
        State("helm-refresh-trigger", "data"),
        prevent_initial_call=True,
    )
    def install_chart(n, release, chart, repo, version, namespace, values, createns, trigger):
        if not n:
            raise PreventUpdate
        if not release or not chart:
            return "✗ Release name and chart are required.", trigger or 0
        try:
            helm.install(
                release=release.strip(),
                chart=chart.strip(),
                namespace=(namespace or "default").strip(),
                version=(version or "").strip(),
                values_yaml=values or "",
                create_namespace="yes" in (createns or []),
                repo_url=(repo or "").strip(),
            )
            result = f"✓ Installed '{release}' from '{chart}'"
            return result, (trigger or 0) + 1
        except helm.HelmError as exc:
            return f"✗ Install failed: {exc}", trigger or 0

    @app.callback(
        Output("helm-selected", "data"),
        Input("helm-table", "active_cell"),
        State("helm-table", "derived_viewport_data"),
    )
    def select_release(active_cell, viewport):
        if not active_cell or not viewport:
            return None
        try:
            row = viewport[active_cell["row"]]
        except (IndexError, KeyError):
            return None
        return {"name": row.get("name"), "namespace": row.get("namespace", "")}

    @app.callback(
        Output("helm-detail-actions", "children"),
        Input("helm-selected", "data"),
    )
    def render_helm_action_bar(selected):
        return render_helm_actions(selected) if selected else []

    @app.callback(
        Output("helm-detail-body", "children"),
        Input("helm-tabs", "value"),
        Input("helm-selected", "data"),
        Input("helm-refresh-trigger", "data"),
    )
    def render_helm_tab(tab, selected, _trigger):
        if not selected:
            return helm_placeholder()
        name, namespace = selected["name"], selected.get("namespace", "")
        try:
            if tab == "history":
                return render_helm_history(helm.release_history(name, namespace))
            if tab == "manifest":
                return render_helm_manifest(helm.release_manifest(name, namespace))
            return render_helm_values(helm.release_values(name, namespace))
        except helm.HelmError as exc:
            return html.Div(f"Error: {exc}", className="detail-error")

    @app.callback(
        Output("helm-confirm", "message"),
        Output("helm-confirm", "displayed"),
        Output("helm-pending", "data"),
        Input({"type": "helm-action", "index": ALL}, "n_clicks"),
        State("helm-selected", "data"),
        State("helm-rollback-rev", "value"),
        prevent_initial_call=True,
    )
    def open_confirmation(_clicks, selected, revision):
        triggered = ctx.triggered[0] if ctx.triggered else None
        if not triggered or not triggered["value"] or not selected:
            raise PreventUpdate

        action = ctx.triggered_id["index"]
        name, namespace = selected["name"], selected.get("namespace", "")
        if action == "rollback":
            target = f"revision {revision}" if revision else "the previous revision"
            message = f"Roll back release '{name}' in '{namespace}' to {target}?"
        else:
            message = f"Uninstall release '{name}' in namespace '{namespace}'?"

        pending = {"action": action, "name": name, "namespace": namespace,
                   "revision": revision}
        return message, True, pending

    @app.callback(
        Output("helm-action-result", "children"),
        Output("helm-refresh-trigger", "data", allow_duplicate=True),
        Output("helm-selected", "data", allow_duplicate=True),
        Input("helm-confirm", "submit_n_clicks"),
        State("helm-pending", "data"),
        State("helm-refresh-trigger", "data"),
        prevent_initial_call=True,
    )
    def execute(submit_n_clicks, pending, trigger):
        if not submit_n_clicks or not pending:
            raise PreventUpdate
        name, namespace = pending["name"], pending["namespace"]
        try:
            if pending["action"] == "rollback":
                helm.rollback(name, namespace, pending.get("revision") or "")
                # Keep the selection: the release still exists post-rollback.
                return f"✓ Rolled back '{name}'", (trigger or 0) + 1, no_update
            helm.uninstall(name, namespace)
            # Clear the selection so the detail panel doesn't reload a dead release.
            return f"✓ Uninstalled '{name}'", (trigger or 0) + 1, None
        except helm.HelmError as exc:
            log.warning("Helm %s failed: %s", pending["action"], exc)
            return f"✗ {pending['action'].title()} failed: {exc}", trigger or 0, no_update
