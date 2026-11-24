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

