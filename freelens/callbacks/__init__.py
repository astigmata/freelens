"""Callback registration entry point."""

from dash import Dash

from . import actions, bulk, crd, data, details, helm, navigation


def register_callbacks(app: Dash) -> None:
    navigation.register(app)
    data.register(app)
    details.register(app)
    actions.register(app)
    bulk.register(app)
    helm.register(app)
    crd.register(app)
