let socket = null;
let monPseudo = "";
let partieActuelle = "";
let estAdmin = false;

if (typeof io !== 'undefined') {
    socket = io();
    configurerSocket();
}

function afficherEcran(id) {
    document.querySelectorAll('.ecran').forEach(e => e.classList.remove('actif'));
    document.getElementById(id).classList.add('actif');
}

// 1. Pseudo
function validerPseudo() {
    monPseudo = document.getElementById('input-pseudo').value.trim();
    if (!monPseudo) return alert("Entre un pseudo !");
    afficherEcran('ecran-home');
    if (socket) socket.emit('demander_parties');
}

// 2. Mode Admin & Compteur de rôles
function activerAdmin() {
    const mdp = document.getElementById('input-mdp-admin').value;
    if (socket) socket.emit('verifier_admin', { mdp: mdp });
}

function getRolesSelectionnes() {
    return {
        "Loup-Garou": parseInt(document.getElementById('role-loup').value) || 0,
        "Villageois": parseInt(document.getElementById('role-villageois').value) || 0,
        "Voyante": parseInt(document.getElementById('role-voyante').value) || 0,
        "Sorcière": parseInt(document.getElementById('role-sorciere').value) || 0,
        "Chasseur": parseInt(document.getElementById('role-chasseur').value) || 0
    };
}

function majCompteur() {
    const roles = getRolesSelectionnes();
    const total = Object.values(roles).reduce((a, b) => a + b, 0);
    const compteurEl = document.getElementById('compteur-joueurs');
    compteurEl.innerText = total;

    if (!estAdmin && (total < 5 || total > 20)) {
        compteurEl.style.color = "#e94560";
    } else {
        compteurEl.style.color = "#4ecca3";
    }
}

// 3. Création & Rejoindre partie
function creerPartie() {
    if (!socket) return alert("Connexion au serveur perdue.");
    const roles = getRolesSelectionnes();
    const total = Object.values(roles).reduce((a, b) => a + b, 0);

    if (!estAdmin && (total < 5 || total > 20)) {
        return alert("En mode normal, le total des rôles doit être compris entre 5 et 20 joueurs !");
    }
    if (estAdmin && total < 1) {
        return alert("Sélectionne au moins 1 rôle !");
    }

    const nom = document.getElementById('input-nom-partie').value.trim();
    socket.emit('creer_partie', {
        pseudo: monPseudo,
        nom_partie: nom,
        roles: roles,
        is_admin: estAdmin
    });
}

function rejoindrePartie(pid) {
    if (socket) socket.emit('rejoindre_partie', { pseudo: monPseudo, pid: pid });
}

// 4. Jeu
function lancerPartie() {
    if (socket) socket.emit('lancer_partie', { pid: partieActuelle });
}

function envoyerMessage() {
    const input = document.getElementById('input-msg');
    const texte = input.value.trim();
    if (!texte || !socket) return;
    socket.emit('envoyer_message', { pid: partieActuelle, texte: texte });
    input.value = "";
}

function configurerSocket() {
    socket.on('admin_valide', (data) => {
        if (data.succes) {
            estAdmin = true;
            document.getElementById('badge-admin').style.display = "inline-block";
            document.getElementById('limite-max').innerText = "∞";
            document.getElementById('input-mdp-admin').value = "";
            majCompteur();
            alert("Mode Admin activé : limites de joueurs supprimées !");
        } else {
            alert("Mot de passe admin incorrect !");
        }
    });

    socket.on('erreur_creation', (data) => alert(data.message));

    socket.on('liste_parties', (parties) => {
        const ul = document.getElementById('liste-parties');
        if (parties.length === 0) {
            ul.innerHTML = '<li class="texte-gris">Aucune partie disponible...</li>';
            return;
        }
        ul.innerHTML = parties.map(p => `
            <li class="salon-item">
                <span>${p.nom} (${p.nb}/${p.max}) ${p.admin ? '🔧' : ''}</span>
                <button onclick="rejoindrePartie('${p.id}')">Rejoindre</button>
            </li>
        `).join('');
    });

    socket.on('partie_rejointe', (data) => {
        partieActuelle = data.pid;
        document.getElementById('titre-salon').innerText = `${data.nom} (Code: ${data.pid})`;
        afficherEcran('ecran-jeu');
    });

    socket.on('ton_role', (data) => {
        document.getElementById('mon-role').innerText = `Ton rôle : ${data.role}`;
        document.getElementById('btn-lancer').style.display = 'none';
    });

    socket.on('etat_partie', (data) => {
        document.getElementById('compteur-salon').innerText = `Joueurs : ${data.joueurs.length} / ${data.max_joueurs}`;
        const conteneur = document.getElementById('cercle-joueurs');
        conteneur.innerHTML = "";
        const total = data.joueurs.length;
        const rayon = 200;
        const centre = 225;

        data.joueurs.forEach((j, index) => {
            const angle = (index / total) * (2 * Math.PI) - (Math.PI / 2);
            const x = centre + rayon * Math.cos(angle);
            const y = centre + rayon * Math.sin(angle);

            const pion = document.createElement('div');
            pion.className = 'joueur-pion' + (j.vivant ? '' : ' mort');
            pion.style.left = `${x}px`;
            pion.style.top = `${y}px`;
            
            pion.innerHTML = `
                <div class="avatar">${j.vivant ? '🧑' : '🪦'}</div>
                <div>${j.pseudo}</div>
            `;

            if (j.vivant && data.phase !== 'lobby') {
                pion.onclick = () => socket.emit('voter_joueur', { pid: partieActuelle, cible_sid: j.sid });
            }

            conteneur.appendChild(pion);
        });
    });

    socket.on('nouveau_message', (data) => {
        const box = document.getElementById('chat-messages');
        const div = document.createElement('div');
        if (data.auteur === "Système") {
            div.className = "msg-systeme";
            div.innerText = data.texte;
        } else {
            div.innerHTML = `<strong>${data.auteur} :</strong> ${data.texte}`;
        }
        box.appendChild(div);
        box.scrollTop = box.scrollHeight;
    });
}
