import random
import uuid
from flask import Flask, render_template, request
from flask_socketio import SocketIO, join_room, emit

app = Flask(__name__, static_folder='statics')
app.config['SECRET_KEY'] = 'cle-secrete-loup-garou'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

MOT_DE_PASSE_ADMIN = "Rico-272"
parties = {}

def log_render(message):
    """Force l'affichage immédiat dans les logs de Render."""
    print(f"[LOUP-GAROU] {message}", flush=True)

def diffuser_liste_parties():
    liste = [
        {
            "id": pid,
            "nom": p["nom"],
            "nb": len(p["joueurs"]),
            "max": p["max_joueurs"],
            "admin": p["mode_admin"]
        }
        for pid, p in parties.items() if p["phase"] == "lobby"
    ]
    socketio.emit('liste_parties', liste)

def diffuser_etat_partie(pid):
    if pid not in parties:
        return
    p = parties[pid]
    joueurs_info = [
        {"sid": sid, "pseudo": j["pseudo"], "vivant": j["vivant"]}
        for sid, j in p["joueurs"].items()
    ]
    socketio.emit('etat_partie', {
        "nom": p["nom"],
        "phase": p["phase"],
        "joueurs": joueurs_info,
        "max_joueurs": p["max_joueurs"]
    }, room=pid)

@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('connect')
def handle_connect():
    log_render(f"🚨 Nouvelle connexion client (SID: {request.sid})")
    diffuser_liste_parties()

@socketio.on('disconnect')
def handle_disconnect():
    log_render(f"🚨 Déconnexion client (SID: {request.sid})")

@socketio.on('demander_parties')
def handle_get_parties():
    diffuser_liste_parties()

@socketio.on('verifier_admin')
def handle_admin(data):
    mdp = data.get('mdp', '')
    if mdp == MOT_DE_PASSE_ADMIN:
        log_render(f"🚨 Mode ADMIN activé par SID: {request.sid}")
        emit('admin_valide', {'succes': True})
    else:
        log_render(f"🚨 Tentative admin échouée par SID: {request.sid}")
        emit('admin_valide', {'succes': False})

@socketio.on('creer_partie')
def handle_create(data):
    pseudo = data.get('pseudo', 'Joueur')
    nom_partie = data.get('nom_partie', '').strip()
    roles_config = data.get('roles', {})
    is_admin = data.get('is_admin', False)

    # Construction de la liste des rôles selon les quantités choisies
    liste_roles = []
    for role, qte in roles_config.items():
        liste_roles.extend([role] * int(qte))

    total_joueurs = len(liste_roles)

    # Vérification des limites (5 min, 20 max sauf si Admin)
    if not is_admin and (total_joueurs < 5 or total_joueurs > 20):
        emit('erreur_creation', {'message': 'Le nombre total de rôles doit être entre 5 et 20 !'})
        return
    if is_admin and total_joueurs < 1:
        emit('erreur_creation', {'message': 'Ajoute au moins 1 rôle en mode admin !'})
        return

    pid = str(uuid.uuid4())[:6].upper()
    nom_final = nom_partie if nom_partie else f"Village #{pid}"

    parties[pid] = {
        "nom": nom_final,
        "phase": "lobby",
        "roles_prevus": liste_roles,
        "max_joueurs": total_joueurs,
        "mode_admin": is_admin,
        "joueurs": {}
    }

    log_render(f"🚨 PARTIE CRÉÉE | ID: {pid} | Nom: '{nom_final}' | Créateur: {pseudo} | Places: {total_joueurs} | Admin: {is_admin} | Rôles: {roles_config}")
    rejoindre(pid, pseudo)
    diffuser_liste_parties()

@socketio.on('rejoindre_partie')
def handle_join(data):
    pid = data['pid']
    pseudo = data['pseudo']
    if pid in parties and parties[pid]['phase'] == 'lobby':
        if len(parties[pid]['joueurs']) >= parties[pid]['max_joueurs']:
            emit('erreur_creation', {'message': 'Cette partie est déjà complète !'})
            return
        rejoindre(pid, pseudo)
        diffuser_liste_parties()

def rejoindre(pid, pseudo):
    join_room(pid)
    parties[pid]['joueurs'][request.sid] = {
        "pseudo": pseudo,
        "role": None,
        "vivant": True,
        "vote": None
    }
    log_render(f"🚨 JOUEUR REJOINT | {pseudo} (SID: {request.sid}) a rejoint {pid}")
    emit('partie_rejointe', {"pid": pid, "nom": parties[pid]["nom"]})
    socketio.emit('nouveau_message', {"auteur": "Système", "texte": f"{pseudo} a rejoint le village."}, room=pid)
    diffuser_etat_partie(pid)

@socketio.on('envoyer_message')
def handle_message(data):
    pid = data['pid']
    if pid in parties and request.sid in parties[pid]['joueurs']:
        joueur = parties[pid]['joueurs'][request.sid]
        if not joueur['vivant']:
            return
        emit('nouveau_message', {"auteur": joueur['pseudo'], "texte": data['texte']}, room=pid)

@socketio.on('lancer_partie')
def handle_start(data):
    pid = data['pid']
    p = parties.get(pid)
    if not p:
        return

    nb_connectes = len(p['joueurs'])
    nb_requis = p['max_joueurs']

    if nb_connectes != nb_requis:
        emit('nouveau_message', {
            "auteur": "Système",
            "texte": f"⚠️ Impossible de lancer : il faut exactement {nb_requis} joueurs ({nb_connectes}/{nb_requis} présents)."
        })
        return

    sids = list(p['joueurs'].keys())
    roles = list(p['roles_prevus'])
    random.shuffle(sids)
    random.shuffle(roles)

    for sid, role in zip(sids, roles):
        p['joueurs'][sid]['role'] = role
        emit('ton_role', {"role": role}, room=sid)

    p['phase'] = 'nuit'
    log_render(f"🚨 PARTIE LANCÉE | ID: {pid} avec {nb_connectes} joueurs.")
    socketio.emit('nouveau_message', {"auteur": "Système", "texte": "🌙 La nuit tombe. Les Loups choisissent une cible (cliquez sur un joueur)."}, room=pid)
    diffuser_liste_parties()
    diffuser_etat_partie(pid)

@socketio.on('voter_joueur')
def handle_vote(data):
    pid = data['pid']
    cible_sid = data['cible_sid']
    p = parties.get(pid)
    if not p or request.sid not in p['joueurs']:
        return

    votant = p['joueurs'][request.sid]
    cible = p['joueurs'].get(cible_sid)

    if not votant['vivant'] or not cible or not cible['vivant']:
        return

    if p['phase'] == 'nuit' and votant['role'] != 'Loup-Garou':
        emit('nouveau_message', {"auteur": "Système", "texte": "Tu dors, tu ne peux pas voter la nuit !"}, room=request.sid)
        return

    votant['vote'] = cible_sid
    emit('nouveau_message', {"auteur": "Système", "texte": f"Tu as voté contre {cible['pseudo']}."}, room=request.sid)
    verifier_fin_tour(pid)

def verifier_fin_tour(pid):
    p = parties[pid]
    vivants = [j for j in p['joueurs'].values() if j['vivant']]
    votants_attendus = [j for j in vivants if j['role'] == 'Loup-Garou'] if p['phase'] == 'nuit' else vivants

    if not votants_attendus:
        return

    if all(j['vote'] is not None for j in votants_attendus):
        votes = [j['vote'] for j in votants_attendus]
        victime_sid = max(set(votes), key=votes.count)
        victime = p['joueurs'][victime_sid]
        victime['vivant'] = False

        for j in p['joueurs'].values():
            j['vote'] = None

        if p['phase'] == 'nuit':
            p['phase'] = 'jour'
            socketio.emit('nouveau_message', {"auteur": "Système", "texte": f"☀️ Le jour se lève ! {victime['pseudo']} ({victime['role']}) a été dévoré. Votez pour éliminer un suspect !"}, room=pid)
        else:
            p['phase'] = 'nuit'
            socketio.emit('nouveau_message', {"auteur": "Système", "texte": f"🔥 Le village a éliminé {victime['pseudo']} ({victime['role']}). 🌙 La nuit tombe..."}, room=pid)

        diffuser_etat_partie(pid)

if __name__ == '__main__':
    socketio.run(app, debug=True)
