# Conception — Authentification, imputabilité et audit (cap HDS)

> **Statut : implémenté.** Cette conception est désormais réalisée dans le code
> (`freelens/auth.py`, `freelens/audit.py`, impersonation dans
> `freelens/k8s/client.py` + `helm.py`) et déployable via
> [`deploy/hds/`](./deploy/hds/). Le mode `proxy` correspond à l'option
> recommandée ci-dessous. Ce document reste la référence de conception.


> Document de conception répondant aux constats **C1** (authentification),
> **C2** (imputabilité), **M1** (audit) et **H3/CSRF** de
> [`SECURITY_AUDIT_HDS.md`](./SECURITY_AUDIT_HDS.md). Objectif : qu'un usage avec
> des données de santé soit défendable. Il ne s'agit pas de refactorer
> l'existant mais d'ajouter trois briques bien délimitées.

## Principes directeurs

1. **Aucun accès anonyme.** Toute requête HTTP **et** toute WebSocket est
   authentifiée, y compris `/terminal` et `/ws/exec`.
2. **Imputabilité de bout en bout.** Chaque action sur le cluster est attribuée à
   un **utilisateur nommé**, jusque dans le journal d'audit *du serveur d'API
   Kubernetes* — pas seulement dans l'app.
3. **Moindre privilège.** Les droits dans le cluster découlent de l'identité de
   l'utilisateur (RBAC Kubernetes), pas d'un compte de service tout-puissant
   partagé.
4. **Journal d'audit immuable et séparé** des logs applicatifs.

---

## 1. Authentification (C1)

### Option recommandée — reverse-proxy authentifiant (oauth2-proxy)

Le plus sûr et le moins intrusif : placer **oauth2-proxy** (ou équivalent) en
amont, branché sur l'IdP de l'établissement (OIDC : Keycloak, Azure AD…). Il
gère le flow Authorization Code + PKCE, la session, le refresh, le logout, et
**injecte l'identité** dans des en-têtes vers l'app :

```
Browser ──TLS──▶ oauth2-proxy ──▶ Freelens (gunicorn)
                    │ vérifie la session OIDC
                    └─ ajoute: X-Auth-Request-User / -Email / -Groups
```

Avantages : la logique cryptographique sensible (jetons, PKCE, sessions) reste
hors de l'app ; MFA et politique de mot de passe délégués à l'IdP ; le TLS et le
SameSite sont gérés au proxy.

> ⚠️ **L'app doit refuser tout accès direct** : binder sur `127.0.0.1` (ou un
> réseau interne), n'accepter que le trafic du proxy, et **faire confiance aux
> en-têtes uniquement s'ils proviennent du proxy** (mTLS interne ou IP de
> confiance). Sinon les en-têtes `X-Auth-Request-*` sont falsifiables.

### Brique applicative : un `before_request` qui exige l'identité

Quel que soit le mode (proxy ou OIDC intégré), l'app pose une garde unique qui
extrait et **exige** une identité, sinon `401` :

```python
# freelens/auth.py
from dataclasses import dataclass
from flask import request, abort, g

@dataclass(frozen=True)
class Identity:
    user: str
    email: str
    groups: tuple[str, ...]

def _identity_from_request():
    user = request.headers.get("X-Auth-Request-User")
    if not user:
        return None
    groups = request.headers.get("X-Auth-Request-Groups", "")
    return Identity(user=user,
                    email=request.headers.get("X-Auth-Request-Email", ""),
                    groups=tuple(g for g in groups.split(",") if g))

def register_auth(server):
    @server.before_request
    def _require_auth():
        # Laisse passer les assets statiques publics si besoin (xterm, css).
        if request.path.startswith("/assets/"):
            return
        ident = _identity_from_request()
        if ident is None:
            abort(401)
        g.identity = ident
```

> **Variante sans proxy (OIDC intégré).** Utiliser
> [`flask-oidc`](https://pypi.org/project/flask-oidc/) / `authlib`. Il faut alors
> : un `secret_key` Flask robuste (depuis un secret, jamais en dur), un cookie de
> session `Secure; HttpOnly; SameSite=Strict`, et la même garde `before_request`.
> Plus de surface de code sensible — à réserver si un proxy n'est pas possible.

### WebSocket `/ws/exec` (point critique)

`flask-sock` s'exécute dans le contexte de requête Flask : la session / les
en-têtes y sont disponibles. La garde doit donc s'appliquer **avant** d'ouvrir le
stream exec, en plus du contrôle d'`Origin` déjà en place :

```python
@sock.route("/ws/exec")
def exec_socket(ws):
    if not _origin_allowed(request):          # déjà implémenté (anti-CSWSH)
        ws.send("Origin not allowed.\r\n"); return
    ident = _identity_from_request()          # NOUVEAU : exiger l'identité
    if ident is None:
        ws.send("Authentication required.\r\n"); return
    ...
    resp = stream(get_user_clients(ident).core.connect_get_namespaced_pod_exec, ...)
```

### CSRF (H3)

- Avec oauth2-proxy + cookie `SameSite=Strict`, les requêtes cross-site ne
  portent pas la session → CSRF fortement atténué.
- En complément, **valider l'`Origin`/`Referer`** sur toutes les requêtes
  mutatives (les `POST /_dash-update-component`), via le même `before_request`.
- Définir un `server.secret_key` (depuis un secret) pour que les sessions Flask
  soient signées.

---

## 2. Imputabilité — impersonation Kubernetes (C2)

Aujourd'hui `get_clients()` renvoie un client **partagé** mis en cache
(`lru_cache(maxsize=1)`), construit sur un kubeconfig/SA unique. Pour l'audit, on
remplace ce singleton par **un client par identité** qui **impersonne**
l'utilisateur auprès de l'API server :

```python
# freelens/k8s/client.py (évolution)
from kubernetes import client

def get_user_clients(identity) -> Clients:
    _load_config()                       # SA/kubeconfig de base inchangé
    cfg = client.Configuration.get_default_copy()
    api = client.ApiClient(cfg)
    api.set_default_header("Impersonate-User", identity.user)
    for grp in identity.groups:
        # plusieurs valeurs : en-têtes répétés gérés par le transport
        api.set_default_header("Impersonate-Group", grp)
    return Clients(core=client.CoreV1Api(api), apps=client.AppsV1Api(api),
                   batch=client.BatchV1Api(api), apiext=client.ApiextensionsV1Api(api),
                   custom=client.CustomObjectsApi(api))
```

Effets :

- Le **serveur d'API Kubernetes applique le RBAC de l'utilisateur** (moindre
  privilège, M5) et **journalise l'identité réelle** dans son *audit log* —
  l'imputabilité est garantie au niveau de l'infrastructure, pas seulement de
  l'app.
- Le SA de l'app n'a besoin que du verbe `impersonate` sur `users` (et
  `groups`) :

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata: { name: freelens-impersonator }
rules:
  - apiGroups: [""]
    resources: ["users", "groups"]
    verbs: ["impersonate"]
```

> **Helm.** `helm.py` shelle sur le binaire `helm`, qui lit le kubeconfig — il
> n'hérite donc pas des en-têtes d'impersonation. Deux options : (a) passer
> `--kube-as-user <user> --kube-as-group <grp>` à chaque invocation `helm`
> (helm ≥ 3.6 supporte l'impersonation), ce qui réplique l'imputabilité ; (b) à
> défaut, **tracer l'acteur applicatif** (cf. §3) et restreindre l'accès à la
> page Helm par groupe. L'option (a) est recommandée.

> **Variante « jeton utilisateur ».** Plus pure encore : transmettre le jeton
> OIDC de l'utilisateur directement à l'API server (si celui-ci est configuré
> avec le même *issuer* OIDC). Supprime le besoin d'impersonation, mais impose
> une intégration côté plan de contrôle Kubernetes — souvent indisponible en
> cluster managé. L'impersonation est le compromis pragmatique.

### Mise en cache

Ne **pas** mettre en cache par-`maxsize=1` (ce serait re-partager). Un petit
cache LRU **clé = identité** est acceptable, ou reconstruire par requête (coût
négligeable). Le chargement de la config de base reste mis en cache.

---

## 3. Journal d'audit (M1)

Journal **distinct** des logs applicatifs, en **JSON structuré**, append-only,
exporté vers un puits immuable (stdout → collecteur/SIEM, ou fichier WORM). Un
événement par **mutation** et par **lecture sensible** (Secret, exec, logs,
download).

```python
# freelens/audit.py
import json, logging, datetime
from flask import request, g

_audit = logging.getLogger("freelens.audit")   # handler dédié, niveau INFO

def audit(action: str, target: dict, result: str, **extra):
    ident = getattr(g, "identity", None)
    _audit.info(json.dumps({
        "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "actor": getattr(ident, "user", "anonymous"),
        "actor_email": getattr(ident, "email", ""),
        "src_ip": request.headers.get("X-Forwarded-For", request.remote_addr),
        "action": action,            # ex: "pod.delete", "secret.read", "pod.exec"
        "target": target,            # {"kind","name","namespace"}
        "result": result,            # "success" | "failure"
        **extra,
    }))
```

Points d'instrumentation (centralisés, donc peu de sites) :

| Événement | Où |
|-----------|----|
| `*.delete`, `deployment.scale`, `deployment.restart` | `callbacks/actions.py`, `callbacks/bulk.py` (juste après/sur échec de l'appel) |
| `helm.install / upgrade / uninstall / rollback` | `callbacks/helm.py` |
| `pod.exec` (ouverture/fermeture de session) | `terminal.py:exec_socket` |
| `secret.read` (YAML d'un Secret), `pod.logs`, `logs.download` | `callbacks/details.py` |

Exigences HDS associées : horodatage fiable (NTP), **intégrité** (puits
append-only / signature), **rétention** définie, accès au journal restreint et
lui-même tracé.

---

## Ordre de mise en œuvre suggéré

1. `secret_key` + en-têtes `SameSite` + garde `before_request` (refus de
   l'anonyme) — **derrière** oauth2-proxy. *Débloque C1.*
2. Étendre la garde à `/ws/exec`. *Ferme le trou exec.*
3. `get_user_clients` + impersonation + ClusterRole `impersonate` ; brancher tous
   les callbacks et `terminal.py` dessus ; retirer le singleton partagé. *C2/M5.*
4. `--kube-as-user` sur les invocations Helm. *Imputabilité Helm.*
5. Module `audit` + instrumentation des points ci-dessus + handler dédié. *M1.*
6. TLS/HSTS au proxy, rate limiting, `sandbox` sur l'iframe terminal. *H2/B3.*

## Critères de sortie (« done »)

- [ ] Aucune route ne répond sans identité authentifiée (testé, y c. WebSocket).
- [ ] Une action de l'utilisateur A apparaît avec `actor=A` dans le journal d'audit
      applicatif **et** dans l'audit log de l'API server.
- [ ] Un utilisateur sans droit RBAC se voit refuser l'action (403) — pas
      d'escalade via un SA partagé.
- [ ] Les flux sont en TLS ; le cookie de session est `Secure; HttpOnly; SameSite`.
- [ ] Le journal d'audit est exporté vers un puits immuable avec rétention définie.
