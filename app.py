import random
import uuid
from flask import Flask, render_template, request
from flask_socketio import SocketIO, join_room, emit

app = Flask(__name__, static_folder='statics')
app.config['SECRET_KEY'] = 'cle-secrete-loup-garou'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Structure : { "id_partie": { "nom": "...", "phase": "lobby", "joueurs": { sid: {pseudo, role, vivant, vote} } } }
parties = {}

def diffuser_liste_parties():
    """Envoie la liste des parties en attente à tous les joueurs sur le Home."""
    liste = [
        {"id": pid, "nom": p["nom"], "nb": len(p["joueurs"])}
        for pid, p in parties.items() if p["phase"] == "lobby"
    ]
    socketio.emit('liste_parties', liste)

def diffuser_etat_partie(pid):
    """Met à jour le cercle des joueurs pour tous les membres du salon."""
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
        "joueurs": joueurs_info
    }, room=pid)

@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('connect')
def handle_connect():
    diffuser_liste_parties()

@socketio.on('creer_partie')
def handle_create(data):
    pid = str(uuid.uuid4())[:6].upper()
    parties[pid] = {
        "nom": data.get('nom_partie') or f"Partie #{pid}",
        "phase": "lobby",
        "joueurs": {}
    }
    rejoindre(pid, data['pseudo'])
    diffuser_liste_parties()

@socketio.on('rejoindre_partie')
def handle_join(data):
    pid = data['pid']
    if pid in parties and parties[pid]['phase'] == 'lobby':
        rejoindre(pid, data['pseudo'])
        diffuser_liste_parties()

def rejoindre(pid, pseudo):
    join_room(pid)
    parties[pid]['joueurs'][request.sid] = {
        "pseudo": pseudo,
        "role": None,
        "vivant": True,
        "vote": None
    }
    emit('partie_rejointe', {"pid": pid, "nom": parties[pid]["nom"]})
    socketio.emit('nouveau_message', {"auteur": "Système", "texte": f"{pseudo} a rejoint le village."}, room=pid)
    diffuser_etat_partie(pid)

@socketio.on('envoyer_message')
def handle_message(data):
    pid = data['pid']
    if pid in parties and request.sid in parties[pid]['joueurs']:
        joueur = parties[pid]['joueurs'][request.sid]
        if not joueur['vivant']:
            return # Les morts ne parlent pas !
        emit('nouveau_message', {"auteur": joueur['pseudo'], "texte": data['texte']}, room=pid)

@socketio.on('lancer_partie')
def handle_start(data):
    pid = data['pid']
    p = parties.get(pid)
    if not p or len(p['joueurs']) < 3:
        emit('nouveau_message', {"auteur": "Système", "texte": "Il faut au moins 3 joueurs pour lancer !"})
        return

    sids = list(p['joueurs'].keys())
    random.shuffle(sids)
    roles = ['Loup-Garou'] + ['Villageois'] * (len(sids) - 1)

    for sid, role in zip(sids, roles):
        p['joueurs'][sid]['role'] = role
        emit('ton_role', {"role": role}, room=sid)

    p['phase'] = 'nuit'
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

    # Logique simple de vote (Nuit = Loups uniquement, Jour = Tout le monde)
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

    # Si tout le monde a voté
    if all(j['vote'] is not None for j in votants_attendus):
        votes = [j['vote'] for j in votants_attendus]
        victime_sid = max(set(votes), key=votes.count) # Joueur le plus voté
        victime = p['joueurs'][victime_sid]
        victime['vivant'] = False

        # Réinitialiser les votes
        for j in p['joueurs'].values():
            j['vote'] = None

        if p['phase'] == 'nuit':
            p['phase'] = 'jour'
            socketio.emit('nouveau_message', {"auteur": "Système", "texte": f"☀️ Le jour se lève ! {victime['pseudo']} ({victime['role']}) a été dévoré cette nuit. Débattez et cliquez sur un joueur pour voter !"}, room=pid)
        else:
            p['phase'] = 'nuit'
            socketio.emit('nouveau_message', {"auteur": "Système", "texte": f"🔥 Le village a éliminé {victime['pseudo']} ({victime['role']}). 🌙 La nuit tombe..."}, room=pid)

        diffuser_etat_partie(pid)

if __name__ == '__main__':
    socketio.run(app, debug=True)
import random
from flask import Flask, render_template, request
from flask_socketio import SocketIO, join_room, emit

app = Flask(__name__, static_folder='statics')
app.config['SECRET_KEY'] = 'cle-secrete-loup-garou'

# Mode 'threading' : 100% compatible Python 3.14 sans dépendances externes
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')


# Stockage des parties en mémoire : { "code_salon": { "joueurs": {}, "phase": "lobby" } }
parties = {}

@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('rejoindre_salon')
def handle_join(data):
    salon = data['salon']
    pseudo = data['pseudo']
    
    if salon not in parties:
        parties[salon] = {'joueurs': {}, 'phase': 'lobby'}
        
    join_room(salon)
    parties[salon]['joueurs'][request.sid] = {
        'pseudo': pseudo,
        'role': None,
        'vivant': True
    }
    
    # Envoie la liste mise à jour à tout le salon
    liste_pseudos = [j['pseudo'] for j in parties[salon]['joueurs'].values()]
    emit('mise_a_jour_salon', {'joueurs': liste_pseudos}, room=salon)

@socketio.on('lancer_partie')
def handle_start(data):
    salon = data['salon']
    joueurs = parties[salon]['joueurs']
    sids = list(joueurs.keys())
    
    if len(sids) < 3:
        emit('erreur', {'message': 'Il faut au moins 3 joueurs.'}, room=request.sid)
        return

    # Attribution des rôles (1 Loup pour 3-4 joueurs, etc.)
    random.shuffle(sids)
    roles = ['Loup-Garou'] + ['Villageois'] * (len(sids) - 1)
    
    for sid, role in zip(sids, roles):
        joueurs[sid]['role'] = role
        # Envoi privé du rôle à chaque joueur uniquement
        emit('ton_role', {'role': role}, room=sid)
        
    parties[salon]['phase'] = 'nuit'
    emit('changement_phase', {'phase': 'Nuit - Les Loups se réveillent'}, room=salon)

if __name__ == '__main__':
    socketio.run(app, debug=True)

