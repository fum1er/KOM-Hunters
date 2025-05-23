from flask import Flask, redirect, request, jsonify # Ajoute jsonify pour afficher le résultat proprement
import os
import requests # Assure-toi d'avoir fait pip install requests
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

STRAVA_CLIENT_ID = os.getenv('STRAVA_CLIENT_ID')
STRAVA_CLIENT_SECRET = os.getenv('STRAVA_CLIENT_SECRET') # Récupère ton Client Secret
STRAVA_REDIRECT_URI = 'http://localhost:5000/strava_callback'

@app.route('/')
def home():
    return '<a href="/login_strava">Se connecter avec Strava pour KOM Hunters</a>'

@app.route('/login_strava')
def login_strava():
    scope = 'read,activity:read_all' 
    auth_url = (
        f"https://www.strava.com/oauth/authorize?"
        f"client_id={STRAVA_CLIENT_ID}"
        f"&redirect_uri={STRAVA_REDIRECT_URI}"
        f"&response_type=code"
        f"&approval_prompt=auto"
        f"&scope={scope}"
    )
    return redirect(auth_url)

@app.route('/strava_callback')
def strava_callback():
    error = request.args.get('error')
    code = request.args.get('code') # Le code d'autorisation que tu as vu
    
    if error:
        return f"Erreur lors de l'autorisation Strava : {error}"
    
    if code:
        # Étape 3 : Échanger le code contre un token d'accès
        token_url = 'https://www.strava.com/oauth/token'
        payload = {
            'client_id': STRAVA_CLIENT_ID,
            'client_secret': STRAVA_CLIENT_SECRET, # TRÈS IMPORTANT : Ton Client Secret
            'code': code,
            'grant_type': 'authorization_code' # Indique que tu échanges un code d'autorisation
        }
        
        print(f"Tentative d'échange du code contre un token avec le code: {code[:20]}...") # Affiche une partie du code pour vérif

        try:
            response = requests.post(token_url, data=payload)
            response.raise_for_status() # Lèvera une exception pour les codes d'erreur HTTP
            
            token_data = response.json()
            
            # À ce stade, tu as les tokens !
            # Pour l'instant, on va juste les afficher.
            # Plus tard, tu les stockeras de manière sécurisée (session, base de données)
            # et tu redirigeras l'utilisateur vers une page de ton application.
            
            print("Tokens reçus avec succès !")
            # Tu peux décommenter la ligne suivante pour voir toutes les données du token
            # print(token_data)
            
            access_token = token_data.get('access_token')
            refresh_token = token_data.get('refresh_token')
            expires_at = token_data.get('expires_at')
            athlete_info = token_data.get('athlete')

            # Pour ce test, on retourne les infos du token, mais dans une vraie app,
            # tu stockerais ces tokens et redirigerais l'utilisateur.
            return (
                f"<h1>Tokens reçus avec succès !</h1>"
                f"<p><b>Access Token:</b> {access_token}</p>"
                f"<p><b>Refresh Token:</b> {refresh_token}</p>"
                f"<p><b>Expires At (timestamp UTC):</b> {expires_at}</p>"
                f"<p><b>Athlete ID:</b> {athlete_info.get('id') if athlete_info else 'N/A'}</p>"
                f"<p><b>Athlete Prénom:</b> {athlete_info.get('firstname') if athlete_info else 'N/A'}</p>"
                f"<p>Tu peux maintenant utiliser cet Access Token (qui a le scope 'activity:read_all') "
                f"pour faire des appels à l'API Strava au nom de l'utilisateur {athlete_info.get('firstname') if athlete_info else ''} !</p>"
            )

        except requests.exceptions.HTTPError as http_err:
            return f"Erreur HTTP lors de l'échange du code : {http_err}<br>Réponse : {response.text}"
        except requests.exceptions.RequestException as req_err:
            return f"Erreur de requête lors de l'échange du code : {req_err}"
        except Exception as e:
            return f"Une autre erreur lors de l'échange du code : {e}"
            
    return "Code d'autorisation non trouvé dans le callback."

if __name__ == '__main__':
    app.run(debug=True, port=5000)