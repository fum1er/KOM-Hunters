import dash
from dash import dcc, html, Input, Output, State, callback_context
import plotly.graph_objects as go
import os
import requests
import json
import time
import base64
from datetime import datetime, timedelta
import secrets
import hashlib

# Import Flask pour les sessions
from flask import session, request

# Pour le géocodage
try:
    from geopy.geocoders import Nominatim
    from geopy.exc import GeocoderTimedOut, GeocoderUnavailable
    GEOPY_AVAILABLE = True
except ImportError:
    GEOPY_AVAILABLE = False
    print("⚠️ geopy non disponible - fonctionnalité de géocodage limitée")

print("🚀 KOM HUNTERS V2 - VERSION PUBLIQUE (SANS AUTHENTIFICATION)")

# --- AJOUT POUR S'ASSURER QUE LE RÉPERTOIRE ACTUEL EST DANS SYS.PATH ---
import sys
current_script_directory = os.path.dirname(os.path.abspath(__file__))
if current_script_directory not in sys.path:
    sys.path.insert(0, current_script_directory)
print(f"✅ Répertoire du script ajouté à sys.path: {current_script_directory}")

# --- IMPORT STRAVA_ANALYZER AVEC GESTION D'ERREUR ROBUSTE ---
STRAVA_ANALYZER_AVAILABLE = False
try:
    import strava_analyzer
    STRAVA_ANALYZER_AVAILABLE = True
    print(f"✅ strava_analyzer importé avec succès")
except Exception as e:
    print(f"❌ Erreur d'import de strava_analyzer: {e}")
    STRAVA_ANALYZER_AVAILABLE = False

# Configuration des APIs
MAPBOX_ACCESS_TOKEN = os.getenv('MAPBOX_ACCESS_TOKEN', '')
STRAVA_CLIENT_ID = os.getenv('STRAVA_CLIENT_ID', '')
STRAVA_CLIENT_SECRET = os.getenv('STRAVA_CLIENT_SECRET', '')
WEATHER_API_KEY = os.getenv('OPENWEATHERMAP_API_KEY', '')
SECRET_KEY = os.getenv('SECRET_KEY', '')

# Configuration pour la recherche
SEARCH_RADIUS_KM = 10
MIN_TAILWIND_EFFECT_MPS_SEARCH = 0.7

print(f"📊 Configuration:")
print(f"  - Mapbox: {'✅' if MAPBOX_ACCESS_TOKEN else '❌'}")
print(f"  - Strava ID: {'✅' if STRAVA_CLIENT_ID else '❌'}")
print(f"  - Strava Secret: {'✅' if STRAVA_CLIENT_SECRET else '❌'}")
print(f"  - Weather: {'✅' if WEATHER_API_KEY else '❌'}")
print(f"  - Secret Key: {'✅' if SECRET_KEY else '❌'}")
print(f"  - Geopy: {'✅' if GEOPY_AVAILABLE else '❌'}")
print(f"  - Strava Analyzer: {'✅' if STRAVA_ANALYZER_AVAILABLE else '❌'}")

# Initialisation de l'app
app = dash.Dash(__name__, external_stylesheets=['https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap'])
app.title = "KOM Hunters V2 - Segments avec Vent Favorable"
app.config.suppress_callback_exceptions = True
server = app.server

# === GESTION DU TOKEN STRAVA POUR L'APPLICATION ===
APP_STRAVA_TOKEN = None
TOKEN_EXPIRES_AT = None

def get_app_strava_token():
    """
    Récupère un token d'accès pour l'application en utilisant le Client Credentials Flow
    Ce token permet d'accéder aux données publiques sans authentification utilisateur
    """
    global APP_STRAVA_TOKEN, TOKEN_EXPIRES_AT
    
    # Vérifier si on a déjà un token valide
    if APP_STRAVA_TOKEN and TOKEN_EXPIRES_AT and time.time() < TOKEN_EXPIRES_AT:
        return APP_STRAVA_TOKEN
    
    print("🔑 Récupération d'un nouveau token d'application Strava...")
    
    if not STRAVA_CLIENT_ID or not STRAVA_CLIENT_SECRET:
        print("❌ Configuration Strava manquante (CLIENT_ID ou CLIENT_SECRET)")
        return None
    
    try:
        # Utiliser le Client Credentials Flow pour obtenir un token d'application
        token_url = 'https://www.strava.com/oauth/token'
        
        payload = {
            'client_id': STRAVA_CLIENT_ID,
            'client_secret': STRAVA_CLIENT_SECRET,
            'grant_type': 'client_credentials'
        }
        
        response = requests.post(token_url, data=payload, timeout=15)
        response.raise_for_status()
        token_data = response.json()
        
        access_token = token_data.get('access_token')
        expires_at = token_data.get('expires_at')
        
        if access_token:
            APP_STRAVA_TOKEN = access_token
            TOKEN_EXPIRES_AT = expires_at
            print(f"✅ Token d'application Strava obtenu: ...{access_token[-6:]}")
            if expires_at:
                expire_date = datetime.utcfromtimestamp(expires_at).strftime('%Y-%m-%d %H:%M:%S')
                print(f"🕒 Token expire le: {expire_date} UTC")
            return access_token
        else:
            print("❌ Aucun token d'accès reçu dans la réponse")
            return None
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Erreur lors de la récupération du token d'application: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"📨 Détails de l'erreur: {e.response.text}")
        return None
    except Exception as e:
        print(f"❌ Erreur inattendue lors de la récupération du token: {e}")
        return None

def get_client_ip():
    """Récupère l'adresse IP du client de manière sécurisée"""
    try:
        if os.getenv('RENDER'):
            forwarded_for = request.headers.get('X-Forwarded-For')
            if forwarded_for:
                return forwarded_for.split(',')[0].strip()
            real_ip = request.headers.get('X-Real-IP')
            if real_ip:
                return real_ip.strip()
        return request.remote_addr or '127.0.0.1'
    except Exception as e:
        print(f"❌ Erreur lors de la récupération de l'IP: {e}")
        return '127.0.0.1'

# --- Fonctions utilitaires pour les suggestions d'adresses ---
def get_address_suggestions(query_str, limit=5):
    if not query_str or len(query_str) < 2:
        return [], None 
    if not GEOPY_AVAILABLE:
        return [], "Service de géocodage non disponible"
    
    geolocator = Nominatim(user_agent="kom_hunters_v2_public")
    try:
        locations = geolocator.geocode(query_str, exactly_one=False, limit=limit, timeout=7)
        if locations:
            if not isinstance(locations, list): locations = [locations]
            return [{"display_name": loc.address, "lat": loc.latitude, "lon": loc.longitude} for loc in locations], None
        return [], "Aucune suggestion trouvée."
    except Exception as e:
        return [], f"Erreur de suggestion d'adresse: {e}"

def geocode_address_directly(address_str):
    if not address_str: return None, "L'adresse fournie est vide.", None
    if not GEOPY_AVAILABLE:
        return None, "Service de géocodage non disponible", None
    
    geolocator = Nominatim(user_agent="kom_hunters_v2_public")
    try:
        location = geolocator.geocode(address_str, timeout=10)
        if location:
            return (location.latitude, location.longitude), None, location.address
        return None, f"Adresse non trouvée ou ambiguë : '{address_str}'.", address_str
    except Exception as e:
        return None, f"Erreur de géocodage: {e}", address_str

# CSS intégré avec design simplifié
app.index_string = '''
<!DOCTYPE html>
<html>
<head>
    {%metas%}
    <title>{%title%}</title>
    {%favicon%}
    {%css%}
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        /* Styles pour les suggestions d'adresse */
        .suggestion-item-hover:hover {
            background-color: #f5f5f5 !important;
            transition: background-color 0.2s ease;
        }
        
        /* Styles globaux pour l'application */
        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', sans-serif;
            margin: 0;
            padding: 0;
            background-color: #f8fafc;
        }
        
        /* Header styles */
        .app-header {
            background: linear-gradient(135deg, #1a202c 0%, #2d3748 100%);
            color: white;
            padding: 1.5rem;
            text-align: center;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        }
        
        .app-title {
            margin: 0 0 1rem 0;
            font-size: 2rem;
            font-weight: 700;
            background: linear-gradient(135deg, #ffffff 0%, #e2e8f0 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }
        
        .app-subtitle {
            margin: 0 0 1.5rem 0;
            font-size: 1.1rem;
            color: #a0aec0;
            font-weight: 400;
        }
        
        .app-description {
            margin: 0 0 1.5rem 0;
            font-size: 0.9rem;
            color: #68d391;
            font-style: italic;
            max-width: 600px;
            margin-left: auto;
            margin-right: auto;
        }
        
        /* Conteneur de recherche */
        .search-container {
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 1rem;
            margin-top: 1.5rem;
        }
        
        .address-input-container {
            position: relative;
            width: 450px;
            max-width: 90vw;
        }
        
        /* Input d'adresse */
        .address-input {
            width: 100%;
            padding: 14px 20px;
            font-size: 1.1rem;
            border: 2px solid #4a5568;
            border-radius: 10px;
            background-color: #2d3748;
            color: #e2e8f0;
            box-sizing: border-box;
            transition: all 0.3s ease;
        }
        
        .address-input:focus {
            outline: none;
            border-color: #3182ce;
            box-shadow: 0 0 0 3px rgba(49, 130, 206, 0.1);
        }
        
        .address-input::placeholder {
            color: #a0aec0;
        }
        
        /* Bouton de recherche */
        .search-button {
            background: linear-gradient(135deg, #3182ce 0%, #2c5aa0 100%);
            color: white;
            border: none;
            padding: 14px 32px;
            font-size: 1.1rem;
            font-weight: 600;
            border-radius: 10px;
            cursor: pointer;
            transition: all 0.3s ease;
            margin-top: 80px;
            box-shadow: 0 4px 12px rgba(49, 130, 206, 0.3);
        }
        
        .search-button:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(49, 130, 206, 0.4);
        }
        
        .search-button:active {
            transform: translateY(0);
        }
        
        /* Message de statut */
        .status-message {
            margin-top: 1rem;
            min-height: 24px;
            color: #a0aec0;
            font-size: 1rem;
            text-align: center;
            padding: 0.5rem;
        }
        
        /* Conteneur de la carte */
        .map-container {
            flex-grow: 1;
            min-height: 0;
            background-color: #f7fafc;
            border-top: 1px solid #e2e8f0;
        }
        
        /* Messages d'erreur */
        .error-message {
            background-color: #fed7d7;
            color: #c53030;
            padding: 1rem;
            border-radius: 8px;
            border-left: 4px solid #e53e3e;
            margin: 1rem;
            text-align: center;
        }
        
        .warning-message {
            background-color: #fefcbf;
            color: #d69e2e;
            padding: 1rem;
            border-radius: 8px;
            border-left: 4px solid #ed8936;
            margin: 1rem;
            text-align: center;
        }
        
        /* Info box */
        .info-box {
            background-color: #e6fffa;
            color: #234e52;
            padding: 1rem;
            border-radius: 8px;
            border-left: 4px solid #38b2ac;
            margin: 1rem auto;
            max-width: 600px;
            text-align: center;
        }
        
        /* Responsive design */
        @media (max-width: 768px) {
            .app-title {
                font-size: 1.5rem;
            }
            
            .app-subtitle {
                font-size: 1rem;
            }
            
            .address-input-container {
                width: 90%;
            }
            
            .search-button {
                margin-top: 60px;
                padding: 12px 24px;
                font-size: 1rem;
            }
            
            .app-header {
                padding: 1rem;
            }
        }
    </style>
</head>
<body>
    {%app_entry%}
    <footer>
        {%config%}
        {%scripts%}
        {%renderer%}
    </footer>
</body>
</html>
'''

# Layout principal simplifié sans authentification
def build_main_page_layout():
    return html.Div(style={'fontFamily': 'Inter, sans-serif', 'padding': '0', 'margin': '0', 'height': '100vh', 'display': 'flex', 'flexDirection': 'column'}, children=[
        html.Div(style={'backgroundColor': '#1a202c', 'color': 'white', 'padding': '1rem', 'textAlign': 'center', 'flexShrink': '0', 'position': 'relative'}, children=[
            html.H1("💨 KOM Hunters V2", style={'margin': '0 0 10px 0', 'fontSize': '2rem'}),
            html.H2("Trouvez les segments avec vent favorable", style={'margin': '0 0 1rem 0', 'fontSize': '1.1rem', 'color': '#a0aec0', 'fontWeight': '400'}),
            html.P("🌍 Aucune connexion requise • Accès aux segments publics • Recherche basée sur les conditions météo actuelles", 
                   style={'margin': '0 0 1.5rem 0', 'fontSize': '0.9rem', 'color': '#68d391', 'fontStyle': 'italic', 'maxWidth': '600px', 'marginLeft': 'auto', 'marginRight': 'auto'}),
            
            html.Div(style={'display': 'flex', 'flexDirection': 'column', 'alignItems': 'center', 'gap': '5px', 'marginTop': '10px'}, children=[ 
                html.Div(style={'position': 'relative', 'width': '400px'}, children=[
                    dcc.Input(
                        id='address-input', type='text', placeholder='Tapez une ville ou une adresse (ex: Paris, Lyon, Annecy)...',
                        debounce=False,
                        style={'padding': '10px', 'fontSize': '1rem', 'borderRadius': '5px', 'border': '1px solid #4A5568', 'width': '100%', 'backgroundColor': '#2D3748', 'color': '#E2E8F0', 'boxSizing': 'border-box'}
                    ),
                    html.Div(id='live-address-suggestions-container')
                ]),
                html.Button('🔍 Chercher les Segments avec Vent Favorable !', id='search-button', n_clicks=0, 
                            style={'padding': '10px 15px', 'fontSize': '1rem', 'backgroundColor': '#3182CE', 'color': 'white', 'border': 'none', 'borderRadius': '5px', 'cursor': 'pointer', 'marginTop': '60px'})
            ]),
            html.Div(id='search-status-message', style={'marginTop': '10px', 'minHeight': '20px', 'color': '#A0AEC0'})
        ]),
        
        html.Div(style={'backgroundColor': '#e6fffa', 'color': '#234e52', 'padding': '1rem', 'borderLeft': '4px solid #38b2ac', 'margin': '1rem auto', 'maxWidth': '600px', 'textAlign': 'center'}, children=[
            html.P("ℹ️ Cette application utilise les données publiques de Strava et les conditions météorologiques actuelles pour identifier les segments où le vent vous aidera !", 
                   style={'margin': '0', 'fontSize': '0.9rem'})
        ]),
        
        dcc.Loading(
            id="loading-map-results", type="default",
            children=[html.Div(id='map-results-container')]
        ),
        dcc.Store(id='selected-suggestion-store', data=None)
    ])

# Layout principal
app.layout = html.Div([
    dcc.Location(id='url', refresh=False), 
    html.Div(id='page-content') 
])

print("✅ Layout défini")

# --- Callback de Navigation ---
@app.callback(
    Output('page-content', 'children'),
    Input('url', 'pathname')
)
def display_page_content(pathname):
    return build_main_page_layout()

# === CALLBACKS POUR LES SUGGESTIONS D'ADRESSES ===
@app.callback(
    [Output('live-address-suggestions-container', 'children'),
     Output('live-address-suggestions-container', 'style')],
    Input('address-input', 'value')
)
def update_live_suggestions(typed_address):
    default_style = {'display': 'none'}
    
    if not typed_address or len(typed_address) < 2:
        return [], default_style
    
    suggestions_data, error = get_address_suggestions(typed_address, limit=5)
    
    if error: 
        error_style = {
            'width': '100%', 'maxHeight': '200px', 'overflowY': 'auto', 
            'backgroundColor': '#ffebee', 'border': '1px solid #f44336',
            'borderRadius': '5px', 'marginTop': '2px',
            'position': 'absolute', 'top': '100%', 'zIndex': '1000', 'textAlign': 'left',
            'left': '0', 'right': '0'
        }
        return [html.P(f"Erreur : {error}", style={'padding': '5px', 'color': 'red'})], error_style
    
    if not suggestions_data: 
        no_results_style = {
            'width': '100%', 'maxHeight': '200px', 'overflowY': 'auto', 
            'backgroundColor': '#fff3e0', 'border': '1px solid #ff9800',
            'borderRadius': '5px', 'marginTop': '2px',
            'position': 'absolute', 'top': '100%', 'zIndex': '1000', 'textAlign': 'left',
            'left': '0', 'right': '0'
        }
        return [html.P("Aucune suggestion trouvée.", style={'padding': '5px', 'color': '#ff9800'})], no_results_style
    
    suggestions_style = {
        'width': '100%', 'maxHeight': '200px', 'overflowY': 'auto', 
        'backgroundColor': 'white', 'border': '1px solid #ccc',
        'borderRadius': '5px', 'marginTop': '2px',
        'position': 'absolute', 'top': '100%', 'zIndex': '1000', 'textAlign': 'left',
        'boxShadow': '0 4px 15px rgba(0,0,0,0.15)',
        'left': '0', 'right': '0'
    }
    
    suggestion_elements = []
    for i, sugg_data in enumerate(suggestions_data):
        suggestion_elements.append(
            html.Div(
                sugg_data['display_name'],
                id={'type': 'suggestion-item', 'index': i}, 
                n_clicks=0, 
                style={
                    'padding': '12px 15px',
                    'cursor': 'pointer', 
                    'borderBottom': '1px solid #eee' if i < len(suggestions_data) - 1 else 'none',
                    'color': '#333',
                    'fontSize': '0.9rem',
                    'lineHeight': '1.4'
                },
                className='suggestion-item-hover'
            )
        )
    
    return suggestion_elements, suggestions_style

@app.callback(
    [Output('address-input', 'value'),
     Output('selected-suggestion-store', 'data'),
     Output('live-address-suggestions-container', 'children', allow_duplicate=True),
     Output('live-address-suggestions-container', 'style', allow_duplicate=True)],
    [Input({'type': 'suggestion-item', 'index': dash.ALL}, 'n_clicks')],
    [State('address-input', 'value')],
    prevent_initial_call=True 
)
def select_suggestion(n_clicks_list, original_address_input):
    ctx = callback_context 
    if not ctx.triggered or not any(n_clicks_list): 
        raise dash.exceptions.PreventUpdate

    triggered_id_str = ctx.triggered[0]['prop_id'].split('.')[0]
    if not triggered_id_str: raise dash.exceptions.PreventUpdate
        
    try:
        clicked_id_dict = json.loads(triggered_id_str.replace("'", "\"")) 
        clicked_index = clicked_id_dict['index']
    except Exception as e:
        print(f"❌ Erreur parsing ID suggestion: {e}, ID: {triggered_id_str}")
        raise dash.exceptions.PreventUpdate
    
    current_suggestions_data, _ = get_address_suggestions(original_address_input, limit=5)
    if current_suggestions_data and 0 <= clicked_index < len(current_suggestions_data):
        selected_suggestion = current_suggestions_data[clicked_index]
        print(f"✅ Suggestion sélectionnée: {selected_suggestion['display_name']}")
        
        hidden_style = {'display': 'none'}
        
        return selected_suggestion['display_name'], selected_suggestion, [], hidden_style
    
    return dash.no_update, dash.no_update, [], {'display': 'none'}

# === CALLBACK POUR LA RECHERCHE DE SEGMENTS ===
@app.callback(
    [Output('map-results-container', 'children'),
     Output('search-status-message', 'children'),
     Output('selected-suggestion-store', 'data', allow_duplicate=True)],
    [Input('search-button', 'n_clicks')],
    [State('address-input', 'value'),
     State('selected-suggestion-store', 'data')],
    prevent_initial_call=True 
)
def search_and_display_segments(n_clicks, address_input_value, selected_suggestion_data):
    print(f"\n=== 🔍 DEBUT RECHERCHE DE SEGMENTS V2 PUBLIQUE ===")
    print(f"IP Client: {get_client_ip()}")
    print(f"STRAVA_ANALYZER_AVAILABLE: {'✅' if STRAVA_ANALYZER_AVAILABLE else '❌'}")
    
    search_lat, search_lon = None, None
    display_address = ""
    error_message_search = None

    try:
        if selected_suggestion_data and selected_suggestion_data.get('lat') is not None:
            search_lat = selected_suggestion_data['lat']
            search_lon = selected_suggestion_data['lon']
            display_address = selected_suggestion_data['display_name']
            print(f"📍 Coordonnées depuis suggestion: {search_lat:.4f}, {search_lon:.4f} - '{display_address}'")
        elif address_input_value:
            print(f"🌐 Géocodage direct pour: '{address_input_value}'")
            coords, error_msg, addr_disp = geocode_address_directly(address_input_value)
            if coords:
                search_lat, search_lon = coords
                display_address = addr_disp
                print(f"✅ Géocodage réussi: {search_lat:.4f}, {search_lon:.4f} - '{display_address}'")
            else: 
                error_message_search = error_msg
                print(f"❌ Erreur de géocodage: {error_msg}")
        else: 
            error_message_search = "Veuillez entrer une adresse ou sélectionner une suggestion."
            print("❌ Aucune adresse fournie")
    except Exception as e:
        error_message_search = f"Erreur lors de la détermination des coordonnées: {e}"
        print(f"❌ Exception lors du géocodage: {e}")

    if error_message_search:
        print(f"🔙 Retour avec erreur: {error_message_search}")
        return html.Div([
            html.H3("❌ Erreur", style={'textAlign': 'center', 'color': 'red', 'padding': '20px'})
        ]), f"Erreur: {error_message_search}", None 

    if search_lat is None or search_lon is None: 
        print("❌ Coordonnées invalides")
        return html.Div([
            html.H3("❌ Coordonnées invalides", style={'textAlign': 'center', 'color': 'red', 'padding': '20px'})
        ]), "Impossible de déterminer les coordonnées pour la recherche.", None

    # Récupérer le token d'application Strava
    app_token = get_app_strava_token()
    
    print(f"\n🔍 Vérification des accès:")
    print(f"Token d'application Strava: {'✅ Présent' if app_token else '❌ MANQUANT'}")
    print(f"Clé météo: {'✅ Présente' if WEATHER_API_KEY else '❌ MANQUANTE'}")
    print(f"Analyzer disponible: {'✅ OUI' if STRAVA_ANALYZER_AVAILABLE else '❌ NON'}")
    
    if not app_token: 
        print("⛔ Arrêt: Token d'application Strava manquant")
        return html.Div([
            html.H3("🔒 Impossible d'accéder à Strava", style={'textAlign': 'center', 'color': 'red', 'padding': '20px'}),
            html.P("Problème de configuration du serveur. Contactez l'administrateur.", style={'textAlign': 'center'}),
            html.P("💡 L'application nécessite des credentials Strava valides pour accéder aux segments publics", style={'textAlign': 'center', 'fontSize': '0.9em', 'color': '#666'})
        ]), "Erreur: Impossible d'obtenir un token d'accès Strava.", None
        
    if not WEATHER_API_KEY:
        print("⛔ Arrêt: Clé météo manquante")
        return html.Div([
            html.H3("⚙️ Configuration manquante", style={'textAlign': 'center', 'color': 'red', 'padding': '20px'}),
            html.P("Clé API météorologique manquante.", style={'textAlign': 'center'})
        ]), "Erreur de configuration serveur: Clé API Météo manquante.", None
    
    if not STRAVA_ANALYZER_AVAILABLE:
        print("⛔ Arrêt: Strava analyzer manquant")
        return html.Div([
            html.H3("🔧 Module d'analyse non disponible", style={'textAlign': 'center', 'color': 'red', 'padding': '20px'}),
            html.P("Le module strava_analyzer n'a pas pu être importé.", style={'textAlign': 'center'}),
            html.P("Vérifiez que le fichier strava_analyzer.py est présent et que toutes les dépendances sont installées.", style={'textAlign': 'center', 'fontSize': '0.9em', 'color': '#666'})
        ]), "Erreur: Module d'analyse non disponible.", None

    try:
        print(f"\n🚀 Lancement de la recherche de segments avec vent favorable...")
        found_segments, segments_error_msg = strava_analyzer.find_tailwind_segments_live( 
            search_lat, search_lon, SEARCH_RADIUS_KM, 
            app_token, WEATHER_API_KEY, 
            MIN_TAILWIND_EFFECT_MPS_SEARCH
        )
        
        if segments_error_msg:
            print(f"❌ Erreur lors de la recherche: {segments_error_msg}")
            return html.Div([
                html.H3("❌ Erreur de recherche", style={'textAlign': 'center', 'color': 'red', 'padding': '20px'}),
                html.P(f"{segments_error_msg}", style={'textAlign': 'center'})
            ]), f"Erreur lors de la recherche de segments: {segments_error_msg}", None
            
        print(f"✅ Recherche terminée: {len(found_segments)} segment(s) trouvé(s)")
        
    except Exception as e:
        print(f"❌ Exception lors de la recherche de segments: {e}")
        return html.Div([
            html.H3("❌ Erreur inattendue", style={'textAlign': 'center', 'color': 'red', 'padding': '20px'}),
            html.P(f"Détails: {str(e)}", style={'textAlign': 'center', 'fontSize': '0.9em'})
        ]), f"Erreur inattendue lors de la recherche: {e}", None

    # Création de la carte
    try:
        print(f"\n🗺️ Création de la carte...")
        fig = go.Figure() 

        status_msg = ""
        if not found_segments:
            status_msg = html.Div([
                html.P(f"😔 Aucun segment avec vent favorable trouvé autour de '{display_address}'.", 
                       style={'margin': '0', 'fontWeight': 'bold', 'color': '#D69E2E'}),
                html.P("💡 Essayez une autre zone ou revenez plus tard quand les conditions de vent seront différentes.", 
                       style={'margin': '5px 0 0 0', 'fontSize': '0.9em', 'fontStyle': 'italic', 'color': '#6B7280'})
            ])
            print("😔 Aucun segment avec vent favorable")
            
            fig.add_trace(go.Scattermapbox(
                lat=[search_lat], lon=[search_lon], mode='markers',
                marker=go.scattermapbox.Marker(size=12, color='blue', symbol='circle'),
                text=[f"Recherche: {display_address}"], hoverinfo='text', name='Point de recherche'
            ))
            center_lat, center_lon = search_lat, search_lon
            zoom_level = 11
        else:
            status_msg = html.Div([
                html.P(f"🎉 Excellent ! {len(found_segments)} segment(s) avec vent favorable trouvé(s) autour de '{display_address}' !", 
                       style={'margin': '0', 'fontWeight': 'bold', 'color': '#10B981'}),
                html.P("💡 Conseil: Cliquez sur un segment coloré de la carte pour accéder directement à sa page Strava.", 
                       style={'margin': '5px 0 0 0', 'fontSize': '0.9em', 'fontStyle': 'italic', 'color': '#6B7280'})
            ])
            print(f"🏁 Ajout de {len(found_segments)} segment(s) à la carte...")
            
            all_segment_lats = []
            all_segment_lons = []
            
            for i, segment in enumerate(found_segments):
                try:
                    if segment.get("polyline_coords") and len(segment["polyline_coords"]) >= 2: 
                        coords = segment["polyline_coords"]
                        lats = [coord[0] for coord in coords if coord[0] is not None]
                        lons = [coord[1] for coord in coords if coord[1] is not None]
                        
                        if len(lats) >= 2 and len(lons) >= 2:
                            print(f"  ✅ Segment {i+1}: '{segment['name']}' - {len(lats)} points valides")
                            
                            all_segment_lats.extend(lats)
                            all_segment_lons.extend(lons)
                            
                            colors = ['rgba(255, 0, 0, 0.9)', 'rgba(0, 255, 0, 0.9)', 'rgba(255, 165, 0, 0.9)', 'rgba(128, 0, 128, 0.9)', 'rgba(255, 192, 203, 0.9)']
                            color = colors[i % len(colors)]
                            
                            fig.add_trace(go.Scattermapbox(
                                lat=lats, 
                                lon=lons, 
                                mode='lines+markers',
                                line=dict(width=5, color=color),
                                marker=dict(size=8, color=color, symbol='circle'),
                                name=f"💨 {segment['name']}",
                                text=[f"<b>💨 {segment['name']}</b><br>📏 Distance: {segment.get('distance','N/A'):.0f}m<br>📈 Pente: {segment.get('avg_grade','N/A'):.1f}%<br>🧭 Cap: {segment.get('bearing','N/A')}°<br>💨 Effet Vent: +{segment.get('wind_effect_mps','N/A'):.2f} m/s<br><br>🔗 <b>Cliquez sur le segment pour accéder à Strava !</b>" for _ in lats],
                                hoverinfo='text',
                                hovertemplate='%{text}<extra></extra>',
                                customdata=[{
                                    'segment_id': segment['id'], 
                                    'strava_url': segment['strava_link'],
                                    'segment_name': segment['name']
                                }] * len(lats)
                            ))
                            print(f"    ✅ Segment ajouté avec succès et interaction configurée")
                        else:
                            print(f"  ⚠️ Segment {i+1}: '{segment['name']}' - coordonnées invalides")
                    else:
                        print(f"  ⚠️ Segment {i+1}: '{segment.get('name')}' sans coordonnées ou trop court")
                except Exception as segment_error:
                    print(f"  ❌ Erreur ajout segment {i+1}: {segment_error}")

            if all_segment_lats and all_segment_lons:
                center_lat = sum(all_segment_lats) / len(all_segment_lats)
                center_lon = sum(all_segment_lons) / len(all_segment_lons)
                
                lat_range = max(all_segment_lats) - min(all_segment_lats)
                lon_range = max(all_segment_lons) - min(all_segment_lons)
                max_range = max(lat_range, lon_range)
                max_range_with_margin = max_range * 1.4
                
                print(f"📍 Centre calculé: ({center_lat:.6f}, {center_lon:.6f})")
                
                if max_range_with_margin < 0.002:
                    zoom_level = 15
                elif max_range_with_margin < 0.005:
                    zoom_level = 14
                elif max_range_with_margin < 0.01:
                    zoom_level = 13
                elif max_range_with_margin < 0.02:
                    zoom_level = 12
                elif max_range_with_margin < 0.05:
                    zoom_level = 11
                elif max_range_with_margin < 0.1:
                    zoom_level = 10
                else:
                    zoom_level = 9
                    
                print(f"🔍 Zoom calculé: {zoom_level}")
                    
            else:
                center_lat, center_lon = search_lat, search_lon
                zoom_level = 14
                print("🔄 Fallback: utilisation des coordonnées de recherche")

        fig.update_layout(
            mapbox_style="streets", 
            mapbox_accesstoken=MAPBOX_ACCESS_TOKEN,
            mapbox_zoom=zoom_level, 
            mapbox_center_lat=center_lat, 
            mapbox_center_lon=center_lon,
            margin={"r":0,"t":0,"l":0,"b":0}, 
            showlegend=False,
            height=600,
            uirevision=f'map_results_{search_lat}_{search_lon}'
        )
        
        print(f"=== 🏁 FIN RECHERCHE DE SEGMENTS V2 PUBLIQUE ===\n")
        
        map_component = dcc.Graph(
            id='segments-map',
            figure=fig,
            style={'height': '600px', 'width': '100%'},
            config={
                'displayModeBar': True, 
                'displaylogo': False,
                'modeBarButtonsToRemove': ['pan2d', 'select2d', 'lasso2d', 'autoScale2d'],
                'scrollZoom': True,
                'doubleClick': 'reset+autosize'
            }
        )
        
        return map_component, status_msg, None
        
    except Exception as e:
        print(f"❌ Erreur lors de la création de la carte: {e}")
        return html.Div([
            html.H3("❌ Erreur d'affichage", style={'textAlign': 'center', 'color': 'red', 'padding': '20px'}),
            html.P(f"Détails: {e}", style={'textAlign': 'center', 'fontSize': '0.9em'})
        ]), f"Erreur lors de l'affichage des résultats: {e}", None

# === CALLBACK POUR L'INTERACTION STRAVA (segments) ===
@app.callback(
    Output('search-status-message', 'children', allow_duplicate=True),
    Input('segments-map', 'clickData'),
    prevent_initial_call=True
)
def handle_segment_click(click_data):
    """Gère les clics sur les segments de la carte pour ouvrir Strava"""
    if not click_data or 'points' not in click_data or not click_data['points']:
        return dash.no_update
    
    try:
        point_data = click_data['points'][0]
        if 'customdata' in point_data and isinstance(point_data['customdata'], dict):
            segment_name = point_data['customdata'].get('segment_name', 'ce segment')
            strava_url = point_data['customdata'].get('strava_url')
            
            if strava_url:
                return html.Div([
                    html.P(f"💨 Segment sélectionné: {segment_name}", 
                           style={'fontWeight': 'bold', 'color': '#10B981', 'margin': '5px 0'}),
                    html.A(
                        [
                            html.Span("🔗 ", style={'fontSize': '1.2em'}),
                            html.Span("CLIQUEZ ICI POUR VOIR CE SEGMENT SUR STRAVA", 
                                    style={'textDecoration': 'underline', 'fontWeight': 'bold'})
                        ],
                        href=strava_url,
                        target="_blank",
                        style={
                            'display': 'inline-block',
                            'padding': '10px 15px',
                            'backgroundColor': '#FC4C02',
                            'color': 'white',
                            'borderRadius': '8px',
                            'textDecoration': 'none',
                            'fontSize': '1.1em',
                            'fontWeight': 'bold',
                            'transition': 'all 0.3s ease',
                            'border': '2px solid #FC4C02'
                        }
                    ),
                    html.P(f"🌍 Accès libre aux segments publics - Aucune connexion requise", 
                           style={'fontSize': '0.75em', 'color': '#6B7280', 'margin': '8px 0 0 0', 'fontStyle': 'italic'})
                ], style={'textAlign': 'center', 'padding': '10px'})
        
        return dash.no_update
        
    except Exception as e:
        print(f"❌ Erreur lors du traitement du clic sur segment: {e}")
        return dash.no_update

print("✅ Tous les callbacks définis")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8050))
    debug_mode = os.environ.get('RENDER') is None
    
    # Configuration URL dynamique pour render.com ou développement local
    if os.getenv('RENDER'):
        BASE_URL = f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME', 'kom-hunters-v2.onrender.com')}"
    else:
        BASE_URL = 'http://localhost:8050'
    
    required_keys = [MAPBOX_ACCESS_TOKEN, STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET, WEATHER_API_KEY, SECRET_KEY]
    missing_keys = []
    if not MAPBOX_ACCESS_TOKEN: missing_keys.append("MAPBOX_ACCESS_TOKEN")
    if not STRAVA_CLIENT_ID: missing_keys.append("STRAVA_CLIENT_ID") 
    if not STRAVA_CLIENT_SECRET: missing_keys.append("STRAVA_CLIENT_SECRET")
    if not WEATHER_API_KEY: missing_keys.append("OPENWEATHERMAP_API_KEY")
    if not SECRET_KEY: missing_keys.append("SECRET_KEY")
    
    if missing_keys:
        print(f"❌ ERREUR CRITIQUE: Variables d'environnement manquantes: {', '.join(missing_keys)}")
        print("⚠️ L'application ne fonctionnera pas correctement sans ces clés.")
    
    # Test du token d'application au démarrage
    startup_token = get_app_strava_token()
    if startup_token:
        print(f"✅ Token d'application Strava testé avec succès au démarrage")
    else:
        print(f"❌ ATTENTION: Impossible d'obtenir un token d'application Strava au démarrage")
        print(f"   Vérifiez vos STRAVA_CLIENT_ID et STRAVA_CLIENT_SECRET")
    
    print(f"\n🚀 LANCEMENT KOM HUNTERS V2 PUBLIQUE")
    print(f"🌐 Mode: {'Développement' if debug_mode else 'Production'}")
    print(f"🔗 URL: {BASE_URL}")
    print(f"🔓 AUCUNE AUTHENTIFICATION UTILISATEUR REQUISE")
    print(f"🌍 Accès aux segments publics uniquement")
    print(f"📊 Fonctionnalité: Recherche de segments avec vent favorable")
    print(f"💨 Utilise les conditions météorologiques en temps réel")
    
    app.run_server(debug=debug_mode, host='0.0.0.0', port=port)