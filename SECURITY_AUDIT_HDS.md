# Audit de sécurité — Freelens (perspective HDS)

> **Date :** 2026-06-19 · **Périmètre :** application web Dash/Flask exposant un
> cluster Kubernetes (lecture, exec TTY, logs, delete/scale, Helm, CRD).
> **Branche auditée :** `feat/bulk-and-exec`.

## Avertissement de cadrage

La certification **HDS** (référentiel *Hébergeur de Données de Santé*, fondé sur
ISO 27001 + ISO 20000-1 et des exigences spécifiques) certifie un **hébergeur**,
pas une application. Mais une application qui **accède à des données de santé**
doit respecter les exigences associées (RGPD, PGSSI-S, doctrine technique de la
CNIL/ANS) : **authentification** (forte pour les données de santé),
**imputabilité / traçabilité**, **chiffrement des flux**, **journalisation**,
**moindre privilège**. C'est sous cet angle qu'est évalué le code.

Ce document est une **revue technique de sécurité**, pas un audit de
certification formel.

## Verdict

> **Mise à jour (implémentation).** Les fondations manquantes ont été
> implémentées : authentification (mode `proxy` OIDC), imputabilité par
> impersonation Kubernetes, journal d'audit JSON, durcissement (CSRF, en-têtes,
> redaction Secrets, CSP, assets locaux). Voir « Synthèse des correctifs ».
> **Sous réserve d'un déploiement conforme** (`FREELENS_AUTH_MODE=proxy` derrière
> un proxy OIDC + TLS, RBAC par utilisateur, export du journal vers un puits
> immuable, hébergement HDS-certifié — cf. [`deploy/hds/`](./deploy/hds/)), les
> blocages applicatifs sont levés.

**Constat initial** — 🔴 en l'état du code audité, Freelens ne pouvait pas être
utilisé en cadre HDS. Quatre manques rédhibitoires, désormais traités :

1. **Aucune authentification** → ✅ mode `proxy` (OIDC) + garde 401. *(C1)*
2. **Aucune imputabilité** → ✅ impersonation Kubernetes par utilisateur. *(C2)*
3. **Aucun chiffrement en transit** → ⚙️ à assurer au déploiement (TLS/HSTS,
   manifests fournis). *(H2)*
4. **Aucune journalisation d'audit** → ✅ trail JSON structuré. *(M1)*

La conception détaillée est dans [`SECURITY_AUTH_DESIGN.md`](./SECURITY_AUTH_DESIGN.md) ;
le déploiement de référence dans [`deploy/hds/`](./deploy/hds/).

---

## Constats critiques 🔴

> ✅ **C1, C2 et C3 sont corrigés** par la couche auth/impersonation (mode
> `proxy`). Description initiale conservée ci-dessous pour la traçabilité de
> l'audit.

### C1 — Aucune authentification ni autorisation : contrôle total anonyme ✅ *corrigé*
Aucune couche d'auth nulle part (`app.py`, `freelens/terminal.py`, tous les
callbacks). Toute personne atteignant `FREELENS_HOST:PORT` obtient **sans
identification** : un shell interactif dans n'importe quel pod (`/ws/exec`), la
suppression / scale / restart de ressources (`callbacks/actions.py`,
`callbacks/bulk.py`), le déploiement / désinstallation Helm (`callbacks/helm.py`)
et la lecture de toutes les ressources. Le défaut `HOST=127.0.0.1`
(`config.py`) ne protège qu'en local ; tout déploiement réel
(`0.0.0.0`, `gunicorn`, Ingress) ouvre l'accès.

### C2 — Identité unique partagée → aucune imputabilité ✅ *corrigé*
`freelens/k8s/client.py` charge **un seul** kubeconfig / ServiceAccount in-cluster
(`_load_config`, `lru_cache`). **Toutes** les actions de **tous** les utilisateurs
passent par cette identité unique → impossible de savoir **qui** a consulté ou
modifié une donnée. La traçabilité/imputabilité est une exigence centrale
HDS/CNIL pour les données de santé : ce point seul est disqualifiant.

### C3 — Shell root non restreint dans tout pod ✅ *corrigé (auth + impersonation + audit)*
`terminal.py` ouvre `connect_get_namespaced_pod_exec` avec `/bin/bash`, sur
n'importe quel namespace/pod fourni en query string. Accès direct aux données de
santé de n'importe quel conteneur, avec les privilèges du conteneur (souvent
root).

---

## Constats élevés 🟠

### H1 — Valeurs de Secrets exposées en clair via l'onglet YAML ✅ *corrigé*
Le panneau détail masque les valeurs (`registry.py` *« Values are intentionally
never shown »*), mais l'onglet YAML les exposait : `render_yaml` → `get_object` →
`read_namespaced_secret` → `to_yaml(obj)` sérialisait l'objet complet, champ
`data` base64 inclus (le base64 n'est pas un chiffrement).
**Correctif appliqué** : `operations.to_yaml` redacte désormais `data` /
`stringData` des objets `Secret` (les noms de clés restent visibles).

### H2 — Aucun chiffrement en transit (HTTP / `ws://`)
Aucune terminaison TLS. Le terminal n'utilise `wss` que si la page est déjà en
HTTPS. **À traiter par déploiement** : reverse-proxy TLS + HSTS (en-tête HSTS
déjà émis par l'app, cf. H4) + redirection. *Non corrigeable dans le code seul.*

### H3 — Cross-Site WebSocket Hijacking + CSRF ✅ *partiellement corrigé*
- `/ws/exec` ne vérifiait pas l'en-tête `Origin` → CSWSH.
  **Correctif appliqué** : `terminal._origin_allowed` rejette les handshakes
  cross-origin / sans Origin (allow-list via `FREELENS_ALLOWED_ORIGINS`).
- Les callbacks Dash (`POST /_dash-update-component`) n'ont **ni jeton CSRF ni
  `secret_key` Flask**. **Reste à traiter** : ce point disparaît surtout avec
  l'authentification (cf. C1) ; voir `SECURITY_AUTH_DESIGN.md`.

### H4 — Dépendance CDN externe sans SRI ni CSP ✅ *corrigé*
`terminal.py` chargeait xterm.js depuis `cdn.jsdelivr.net` sans intégrité de
sous-ressource ni CSP, imposant un egress Internet (incompatible HDS isolé).
**Correctif appliqué** : assets **vendorisés localement** (`assets/vendor/`),
plus une **CSP stricte** sur la page `/terminal` (`default-src 'none'`, scripts
et styles *self*, sockets same-origin).

---

## Constats moyens 🟡

- **M1 — Pas de journal d'audit.** ✅ *corrigé* : `freelens/audit.py` émet un
  événement JSON (acteur, IP source, action, cible, résultat, horodatage) par
  action sensible (delete/scale/restart, exec open/close, lecture de Secret, logs,
  download, helm). Logger dédié, à exporter vers un puits immuable
  (`FREELENS_AUDIT_FILE` ou stdout).
- **M2 — Fuite d'informations par messages d'erreur bruts.** ✅ *corrigé* :
  les `f"Error: {exc}"` exposant les `ApiException` (URL de l'API server,
  en-têtes) sont remplacés par des messages génériques côté UI, le détail restant
  journalisé côté serveur (`callbacks/details.py`, `callbacks/crd.py`). Les
  messages d'erreur Helm (sortie CLI, faible divulgation) sont conservés pour
  l'usabilité.
- **M3 — Déploiement arbitraire / SSRF via Helm.** `helm.install` accepte un
  `repo_url` et un `chart` arbitraires — sans garde-fou ni autorisation
  (inhérent à Helm, aggravé par l'absence d'auth).
- **M4 — Mode debug Werkzeug activable.** `FREELENS_DEBUG=true` expose le
  débogueur (risque RCE). Défaut `false` ; **à interdire explicitement en prod**.
- **M5 — Privilèges du ServiceAccount non bornés.** Rien ne contraint le RBAC ;
  un SA cluster-admin donne tout. Moindre privilège non appliqué.
- **M6 — Pas de session, timeout, ni verrouillage** (à prévoir avec l'auth).

## Constats faibles / observations 🔵

- **B1** — Logs téléchargeables sans contrôle (`details.py:download_logs`) →
  exfiltration triviale de PHI présents dans les logs.
- **B2** — En-têtes de sécurité HTTP absents. ✅ *corrigé* : `freelens/security.py`
  ajoute `X-Frame-Options: SAMEORIGIN`, `X-Content-Type-Options: nosniff`,
  `Referrer-Policy: no-referrer`, `Strict-Transport-Security`.
- **B3** — Aucune limitation de débit → DoS / exhaustion de l'API server.
- **B4** — Valeurs de ConfigMaps exposées via YAML (config potentiellement
  sensible).

## Points positifs ✅

- **Pas d'injection de commande Helm** : `subprocess.run` avec args en **liste**,
  jamais `shell=True`, `values_yaml` via **stdin** (`helm.py:_run`).
- Confirmation systématique avant action destructrice.
- Valeurs de Secrets masquées dans le panneau détail (intention correcte,
  désormais étendue au YAML).
- `HOST` par défaut en loopback, `DEBUG` par défaut `false`.
- **Aucun secret/kubeconfig commité** dans l'historique git (vérifié).
- Architecture lisible : mutations centralisées (`operations.py`, `helm.py`) —
  bonne base pour greffer auth + audit.

---

## Synthèse des correctifs appliqués dans cette branche

| Réf. | Correctif | Fichiers |
|------|-----------|----------|
| C1 | Authentification (mode `proxy` OIDC) : garde `before_request`, 401 anonyme, `/healthz` public | `freelens/auth.py`, `app.py`, `freelens/config.py` |
| C2 | Imputabilité : impersonation Kubernetes par utilisateur (`Impersonate-User/-Group`), helm `--kube-as-user` | `freelens/k8s/client.py`, `freelens/k8s/helm.py`, callbacks |
| C3 | Exec authentifié + impersonné + audité | `freelens/terminal.py` |
| M1 | Journal d'audit JSON structuré (logger dédié) | `freelens/audit.py` + instrumentation |
| H1 | Redaction des valeurs de Secrets dans le YAML | `freelens/k8s/operations.py` |
| H3 | Contrôle d'`Origin` sur `/ws/exec` (anti-CSWSH) + CSRF/`Origin` sur les requêtes mutantes + `secret_key`/cookie `SameSite` | `freelens/terminal.py`, `freelens/auth.py`, `freelens/config.py` |
| H4 | Assets xterm vendorisés localement + CSP page terminal | `freelens/terminal.py`, `assets/vendor/` |
| B2 | En-têtes de sécurité HTTP globaux + `sandbox` sur l'iframe terminal | `freelens/security.py`, `app.py`, `freelens/ui/components.py` |
| M2 | Messages d'erreur génériques côté UI | `freelens/callbacks/details.py`, `crd.py`, `freelens/k8s/registry.py` |

Déploiement de référence : [`deploy/hds/`](./deploy/hds/) (oauth2-proxy + RBAC
impersonation + TLS, conteneurs durcis).

Tests associés : `tests/test_security.py`, `tests/test_auth.py` (suite complète
verte).

## Feuille de route de remédiation

**Implémenté dans le code :**

1. ✅ **Authentification** devant toute l'app, incluant `/terminal` et `/ws/exec`
   (mode `proxy` OIDC). → C1
2. ✅ **Imputabilité** par impersonation Kubernetes par utilisateur (+ helm
   `--kube-as-user`). → C2
3. ✅ **Journal d'audit** applicatif (acteur + action + cible + horodatage +
   résultat). → M1
4. ✅ **CSRF + `secret_key` Flask + cookie `SameSite`** sur les requêtes mutantes.
   → H3
5. ✅ **Moindre privilège** : SA app limité au verbe `impersonate`, RBAC par
   utilisateur (exemple fourni). → M5
6. ✅ `sandbox` sur l'iframe terminal ; interdiction du debug documentée. → B2, M4

**À assurer au déploiement / exploitation (manifests fournis dans `deploy/hds/`) :**

7. ⚙️ **TLS obligatoire** (reverse-proxy + HSTS + redirection). → H2
8. ⚙️ **Export du journal d'audit** vers un puits immuable avec rétention. → M1
9. ⚙️ **Rate limiting / WAF** au niveau de l'Ingress. → B3
10. ⚙️ **Hébergement HDS-certifié**, MFA au niveau de l'IdP, audit log de l'API
    server activé.

Conception détaillée : [`SECURITY_AUTH_DESIGN.md`](./SECURITY_AUTH_DESIGN.md).
