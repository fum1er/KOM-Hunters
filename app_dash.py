import dash
from dash import dcc, html, Input, Output, State, callback_context
import plotly.graph_objects as go
import os
import requests
import json
import time
import base64
from datetime import datetime

# Pour le géocodage
try:
    from geopy.geocoders import Nominatim
    from geopy.exc import GeocoderTimedOut, GeocoderUnavailable
    GEOPY_AVAILABLE = True
except ImportError:
    GEOPY_AVAILABLE = False
    print("⚠️ geopy non disponible - fonctionnalité de géocodage limitée")

print("🚀 KOM HUNTERS - DÉMARRAGE COMPLET")

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
    print(f"✅ strava_analyzer importé avec succès. Chemin: {strava_analyzer.__file__}")
except ModuleNotFoundError as e:
    print(f"❌ ERREUR CRITIQUE - Module 'strava_analyzer' non trouvé dans sys.path: {sys.path}")
    print(f"❌ Détails de l'erreur: {e}")
    print("❌ Vérifiez que le fichier strava_analyzer.py est présent dans le même répertoire")
    # Ne pas faire sys.exit() sur render.com, juste marquer comme non disponible
    STRAVA_ANALYZER_AVAILABLE = False
except ImportError as e:
    print(f"❌ Erreur d'import de strava_analyzer - dépendances manquantes: {e}")
    print("❌ Vérifiez que toutes les dépendances sont installées:")
    print("   - langchain_openai")
    print("   - polyline") 
    print("   - requests")
    STRAVA_ANALYZER_AVAILABLE = False
except Exception as e:
    print(f"❌ Erreur inattendue lors de l'import de strava_analyzer: {e}")
    STRAVA_ANALYZER_AVAILABLE = False

# Configuration des APIs
MAPBOX_ACCESS_TOKEN = os.getenv('MAPBOX_ACCESS_TOKEN', '')
STRAVA_CLIENT_ID = os.getenv('STRAVA_CLIENT_ID', '')
STRAVA_CLIENT_SECRET = os.getenv('STRAVA_CLIENT_SECRET', '')
WEATHER_API_KEY = os.getenv('OPENWEATHERMAP_API_KEY', '')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')

# Configuration URL dynamique pour render.com
if os.getenv('RENDER'):
    BASE_URL = f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME', 'kom-hunters.onrender.com')}"
else:
    BASE_URL = 'http://localhost:8050'

STRAVA_REDIRECT_URI = f'{BASE_URL}/strava_callback'
STRAVA_SCOPES = 'read,activity:read_all,profile:read_all'

print(f"🌐 BASE_URL: {BASE_URL}")
print(f"🔄 STRAVA_REDIRECT_URI: {STRAVA_REDIRECT_URI}")

# Variables globales pour les tokens - SEULEMENT OAuth, pas de .env
current_strava_access_token = None
current_refresh_token = None
token_expires_at = None
new_token_info_global = "Cliquez sur 'Se connecter avec Strava' pour commencer."

# Configuration pour l'analyse d'activités
ACTIVITIES_PER_LOAD = 10
CYCLING_ACTIVITY_TYPES = ['Ride', 'VirtualRide', 'EBikeRide', 'Gravel', 'MountainBikeRide']
DEFAULT_FC_MAX = 190
DEFAULT_FTP = 250
DEFAULT_WEIGHT = 70
SEARCH_RADIUS_KM = 10
MIN_TAILWIND_EFFECT_MPS_SEARCH = 0.7

print(f"📊 Configuration:")
print(f"  - Mapbox: {'✅' if MAPBOX_ACCESS_TOKEN else '❌'}")
print(f"  - Strava ID: {'✅' if STRAVA_CLIENT_ID else '❌'}")
print(f"  - Strava Secret: {'✅' if STRAVA_CLIENT_SECRET else '❌'}")
print(f"  - Weather: {'✅' if WEATHER_API_KEY else '❌'}")
print(f"  - OpenAI: {'✅' if OPENAI_API_KEY else '❌'}")
print(f"  - Geopy: {'✅' if GEOPY_AVAILABLE else '❌'}")
print(f"  - Strava Analyzer: {'✅' if STRAVA_ANALYZER_AVAILABLE else '❌'}")

# Initialisation de l'app
app = dash.Dash(__name__, external_stylesheets=['https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap'])
app.title = "KOM Hunters - Dashboard"
app.config.suppress_callback_exceptions = True
server = app.server

# --- Fonction pour charger et encoder le logo Strava ---
def get_strava_logo_base64():
    """Charge et encode le logo Strava en base64"""
    logo_path = os.path.join(current_script_directory, 'logo_strava.png')
    try:
        with open(logo_path, 'rb') as f:
            logo_data = f.read()
            logo_base64 = base64.b64encode(logo_data).decode('utf-8')
            return f"data:image/png;base64,{logo_base64}"
    except FileNotFoundError:
        print(f"⚠️ Logo Strava non trouvé à {logo_path}")
        return None
    except Exception as e:
        print(f"⚠️ Impossible de charger le logo Strava: {e}")
        return None

# --- Composant du logo Strava avec statut et bouton de connexion ---
def create_strava_status_component():
    """Crée le composant du logo Strava avec indicateur de statut et bouton de connexion"""
    global current_strava_access_token
    
    logo_src = get_strava_logo_base64()
    is_connected = bool(current_strava_access_token and len(current_strava_access_token.strip()) > 20)
    
    status_color = '#10B981' if is_connected else '#EF4444'  # Vert si connecté, rouge sinon
    status_text = 'Connecté ✓' if is_connected else 'Non connecté'
    
    # URL d'authentification Strava
    auth_url = (
        f"https://www.strava.com/oauth/authorize?"
        f"client_id={STRAVA_CLIENT_ID}"
        f"&redirect_uri={STRAVA_REDIRECT_URI}"
        f"&response_type=code"
        f"&approval_prompt=force"  
        f"&scope={STRAVA_SCOPES}"
    )
    
    # Contenu du composant
    component_children = []
    
    # Logo Strava
    if logo_src:
        component_children.append(
            html.Img(
                src=logo_src,
                style={
                    'height': '40px',
                    'width': 'auto',
                    'marginBottom': '6px'
                }
            )
        )
    else:
        component_children.append(
            html.Div("STRAVA", style={
                'fontSize': '1rem',
                'fontWeight': 'bold',
                'color': '#FC4C02',
                'marginBottom': '6px'
            })
        )
    
    # Indicateur de statut
    component_children.append(
        html.Div([
            html.Div(
                style={
                    'width': '12px',
                    'height': '12px',
                    'borderRadius': '50%',
                    'backgroundColor': status_color,
                    'marginRight': '6px'
                }
            ),
            html.Span(
                status_text,
                style={
                    'fontSize': '0.75rem',
                    'color': '#E2E8F0',
                    'fontWeight': '500'
                }
            )
        ], style={
            'display': 'flex',
            'alignItems': 'center',
            'marginBottom': '8px' if not is_connected else '0'
        })
    )
    
    # Bouton de connexion si pas connecté
    if not is_connected:
        component_children.append(
            html.A(
                html.Div([
                    html.Span("🔗", style={'marginRight': '4px', 'fontSize': '0.9rem'}),
                    html.Span("Se connecter", style={'fontSize': '0.75rem', 'fontWeight': '600'})
                ], style={
                    'display': 'flex',
                    'alignItems': 'center',
                    'justifyContent': 'center'
                }),
                href=auth_url,
                style={
                    'display': 'block',
                    'padding': '6px 12px',
                    'backgroundColor': '#FC4C02',
                    'color': 'white',
                    'textDecoration': 'none',
                    'borderRadius': '6px',
                    'fontSize': '0.75rem',
                    'fontWeight': '600',
                    'transition': 'all 0.3s ease',
                    'boxShadow': '0 2px 8px rgba(252, 76, 2, 0.3)',
                    'border': '1px solid #FC4C02',
                    'cursor': 'pointer'
                }
            )
        )
    else:
        # Si connecté, afficher un petit message de confirmation
        component_children.append(
            html.Div("🎉 Prêt à analyser !", style={
                'fontSize': '0.7rem',
                'color': '#68D391',
                'fontWeight': '500',
                'textAlign': 'center',
                'marginTop': '4px'
            })
        )
    
    return html.Div(
        component_children,
        style={
            'position': 'absolute',
            'top': '15px',
            'right': '20px',
            'display': 'flex',
            'flexDirection': 'column',
            'alignItems': 'center',
            'zIndex': '1000',
            'padding': '10px',
            'backgroundColor': 'rgba(26, 32, 44, 0.85)',
            'borderRadius': '10px',
            'backdropFilter': 'blur(10px)',
            'border': '1px solid rgba(255,255,255,0.1)',
            'boxShadow': '0 4px 12px rgba(0,0,0,0.3)'
        }
    )

# --- NOUVELLE Fonction pour récupérer les activités vélo avec logique améliorée ---
def fetch_cycling_activities_until_target(access_token, target_count=ACTIVITIES_PER_LOAD, max_pages=10):
    """
    Récupère les activités vélo jusqu'à atteindre le nombre cible,
    en continuant à chercher sur plusieurs pages si nécessaire.
    """
    if not access_token:
        return [], "Token Strava manquant"
    
    headers = {'Authorization': f'Bearer {access_token}'}
    url = 'https://www.strava.com/api/v3/athlete/activities'
    
    all_cycling_activities = []
    page = 1
    per_page = 30  # On récupère plus d'activités par page pour être efficace
    
    print(f"🔍 Recherche de {target_count} activités vélo")
    
    try:
        while len(all_cycling_activities) < target_count and page <= max_pages:
            print(f"📄 Page {page}, {per_page} activités par page")
            
            params = {
                'page': page,
                'per_page': per_page
            }
            
            response = requests.get(url, headers=headers, params=params, timeout=15)
            response.raise_for_status()
            
            activities = response.json()
            
            if not activities:  # Plus d'activités disponibles
                print(f"🏁 Plus d'activités disponibles après page {page-1}")
                break
            
            # Filtrer les activités vélo de cette page
            page_cycling_activities = []
            for activity in activities:
                if activity.get('type') in CYCLING_ACTIVITY_TYPES:
                    page_cycling_activities.append(activity)
            
            all_cycling_activities.extend(page_cycling_activities)
            
            print(f"📊 Page {page}: {len(activities)} total, {len(page_cycling_activities)} vélo")
            print(f"📈 Total vélo: {len(all_cycling_activities)}/{target_count}")
            
            # Si on a moins d'activités que demandé sur cette page, on a probablement atteint la fin
            if len(activities) < per_page:
                print(f"🏁 Fin des activités atteinte")
                break
                
            page += 1
            time.sleep(0.2)  # Petit délai pour respecter les limites de l'API
        
        # Limiter au nombre cible si on a plus que demandé
        if len(all_cycling_activities) > target_count:
            all_cycling_activities = all_cycling_activities[:target_count]
        
        print(f"✅ Récupération terminée: {len(all_cycling_activities)} activités vélo")
        return all_cycling_activities, None
        
    except requests.exceptions.HTTPError as e:
        error_msg = f"Erreur HTTP API Strava: {e}"
        if hasattr(e, 'response') and e.response is not None:
            if e.response.status_code == 401:
                error_msg = "Token Strava expiré ou invalide. Veuillez vous reconnecter."
            elif e.response.status_code == 429:
                error_msg = "Limite de taux API Strava atteinte. Veuillez patienter."
        print(f"❌ {error_msg}")
        return [], error_msg
    except Exception as e:
        error_msg = f"Erreur lors de la récupération des activités: {e}"
        print(f"❌ {error_msg}")
        return [], error_msg

def fetch_more_cycling_activities(access_token, existing_activities, additional_count=ACTIVITIES_PER_LOAD):
    """Récupère des activités vélo supplémentaires"""
    if not access_token:
        return [], "Token Strava manquant"
    
    # Calculer à partir de quelle page commencer
    existing_count = len(existing_activities)
    estimated_start_page = max(1, (existing_count // 20) + 1)  # Estimation conservative
    
    print(f"📥 Chargement de {additional_count} activités supplémentaires")
    print(f"📊 {existing_count} existantes, page estimée: {estimated_start_page}")
    
    headers = {'Authorization': f'Bearer {access_token}'}
    url = 'https://www.strava.com/api/v3/athlete/activities'
    
    all_new_activities = []
    page = estimated_start_page
    per_page = 30
    max_pages_to_try = 10
    pages_tried = 0
    
    # Obtenir les IDs des activités existantes pour éviter les doublons
    existing_ids = set(activity['id'] for activity in existing_activities)
    
    try:
        while len(all_new_activities) < additional_count and pages_tried < max_pages_to_try:
            print(f"📄 Page {page} pour plus d'activités")
            
            params = {
                'page': page,
                'per_page': per_page
            }
            
            response = requests.get(url, headers=headers, params=params, timeout=15)
            response.raise_for_status()
            
            activities = response.json()
            
            if not activities:
                print(f"🏁 Plus d'activités disponibles")
                break
            
            # Filtrer les nouvelles activités vélo (pas déjà présentes)
            new_cycling_activities = []
            for activity in activities:
                if (activity.get('type') in CYCLING_ACTIVITY_TYPES and 
                    activity['id'] not in existing_ids):
                    new_cycling_activities.append(activity)
            
            all_new_activities.extend(new_cycling_activities)
            
            print(f"📊 Page {page}: {len(new_cycling_activities)} nouvelles vélo")
            print(f"📈 Total nouvelles: {len(all_new_activities)}/{additional_count}")
            
            if len(activities) < per_page:
                print(f"🏁 Fin atteinte")
                break
                
            page += 1
            pages_tried += 1
            time.sleep(0.2)
        
        # Limiter au nombre demandé
        if len(all_new_activities) > additional_count:
            all_new_activities = all_new_activities[:additional_count]
        
        print(f"✅ Chargement terminé: {len(all_new_activities)} nouvelles activités")
        return all_new_activities, None
        
    except requests.exceptions.HTTPError as e:
        error_msg = f"Erreur HTTP API Strava: {e}"
        if hasattr(e, 'response') and e.response is not None:
            if e.response.status_code == 401:
                error_msg = "Token Strava expiré ou invalide. Veuillez vous reconnecter."
            elif e.response.status_code == 429:
                error_msg = "Limite de taux API Strava atteinte. Veuillez patienter."
        print(f"❌ {error_msg}")
        return [], error_msg
    except Exception as e:
        error_msg = f"Erreur lors de la récupération des activités supplémentaires: {e}"
        print(f"❌ {error_msg}")
        return [], error_msg

# --- Fonctions utilitaires ---
def format_activity_for_dropdown(activity):
    """Formate une activité pour l'affichage dans le dropdown"""
    name = activity.get('name', 'Activité sans nom')
    activity_type = activity.get('type', 'Activité')
    start_date = activity.get('start_date_local', '')
    distance_km = round(activity.get('distance', 0) / 1000, 1) if activity.get('distance') else 0
    
    # Icônes selon le type d'activité
    type_icons = {
        'Ride': '🚴',
        'VirtualRide': '🚴‍💻',
        'EBikeRide': '🚴‍⚡',
        'Gravel': '🚵',
        'MountainBikeRide': '🚵‍♂️'
    }
    icon = type_icons.get(activity_type, '🚴')
    
    # Formater la date
    date_str = ""
    if start_date:
        try:
            date_obj = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            date_str = date_obj.strftime("%d/%m/%Y")
        except:
            date_str = start_date[:10]
    
    return f"{icon} {date_str} - {name} - {distance_km}km"

def get_address_suggestions(query_str, limit=5):
    if not query_str or len(query_str) < 2:
        return [], None 
    if not GEOPY_AVAILABLE:
        return [], "Service de géocodage non disponible"
    
    geolocator = Nominatim(user_agent="kom_hunters_dash_v7")
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
    
    geolocator = Nominatim(user_agent="kom_hunters_dash_v7")
    try:
        location = geolocator.geocode(address_str, timeout=10)
        if location:
            return (location.latitude, location.longitude), None, location.address
        return None, f"Adresse non trouvée ou ambiguë : '{address_str}'.", address_str
    except Exception as e:
        return None, f"Erreur de géocodage: {e}", address_str

# CSS intégré avec tes styles originaux
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
        
        /* Status des tokens */
        .token-status {
            color: #a0aec0;
            font-size: 0.85rem;
            margin-bottom: 0.5rem;
        }
        
        .token-info {
            color: #68d391;
            font-size: 0.8rem;
            white-space: pre-line;
            background: rgba(104, 211, 145, 0.1);
            padding: 0.5rem;
            border-radius: 6px;
            margin-bottom: 1rem;
            border-left: 3px solid #68d391;
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

# Layout principal avec ton design original
def build_main_page_layout():
    global new_token_info_global
    global current_strava_access_token
    
    token_display = "Aucun token récupéré. Cliquez sur 'Se connecter' en haut à droite."
    if current_strava_access_token:
        token_display = f"Token récupéré ✓ ...{current_strava_access_token[-6:]}" if len(current_strava_access_token) > 6 else "Token récupéré ✓"

    return html.Div(style={'fontFamily': 'Inter, sans-serif', 'padding': '0', 'margin': '0', 'height': '100vh', 'display': 'flex', 'flexDirection': 'column'}, children=[
        html.Div(style={'backgroundColor': '#1a202c', 'color': 'white', 'padding': '1rem', 'textAlign': 'center', 'flexShrink': '0', 'position': 'relative'}, children=[
            # Logo Strava avec statut et bouton de connexion
            create_strava_status_component(),
            
            html.H1("KOM Hunters - Dashboard", style={'margin': '0 0 10px 0', 'fontSize': '1.8rem'}),
            html.Div(style={'display': 'flex', 'justifyContent': 'center', 'gap': '20px', 'marginBottom': '15px'}, children=[
                html.A(html.Button("🔍 Recherche de Segments", style={'padding': '10px 15px', 'backgroundColor': '#3182CE', 'color': 'white', 'border': 'none', 'borderRadius': '5px', 'cursor': 'pointer'}), href="/"),
                html.A(html.Button("📊 Analyse d'Activités", style={'padding': '10px 15px', 'backgroundColor': '#38A169', 'color': 'white', 'border': 'none', 'borderRadius': '5px', 'cursor': 'pointer'}), href="/activities")
            ]),
            html.Div(id='token-status-message', children=f"Statut Strava : {token_display}", style={'color': '#A0AEC0', 'marginBottom': '5px', 'fontSize':'0.8em'}),
            html.Div(id='new-token-info-display', children=new_token_info_global, style={'color': '#A0AEC0', 'fontSize':'0.8em', 'whiteSpace': 'pre-line'}),
            html.Div(style={'display': 'flex', 'flexDirection': 'column', 'alignItems': 'center', 'gap': '5px', 'marginTop': '10px'}, children=[ 
                html.Div(style={'position': 'relative', 'width': '400px'}, children=[
                    dcc.Input(
                        id='address-input', type='text', placeholder='Commencez à taper une ville ou une adresse...',
                        debounce=False,
                        style={'padding': '10px', 'fontSize': '1rem', 'borderRadius': '5px', 'border': '1px solid #4A5568', 'width': '100%', 'backgroundColor': '#2D3748', 'color': '#E2E8F0', 'boxSizing': 'border-box'}
                    ),
                    html.Div(id='live-address-suggestions-container')
                ]),
                html.Button('Chercher les Segments !', id='search-button', n_clicks=0, 
                            style={'padding': '10px 15px', 'fontSize': '1rem', 'backgroundColor': '#3182CE', 'color': 'white', 'border': 'none', 'borderRadius': '5px', 'cursor': 'pointer', 'marginTop': '60px'})
            ]),
            html.Div(id='search-status-message', style={'marginTop': '10px', 'minHeight': '20px', 'color': '#A0AEC0'})
        ]),
        
        dcc.Loading(
            id="loading-map-results", type="default",
            children=[html.Div(id='map-results-container')]
        ),
        dcc.Store(id='selected-suggestion-store', data=None)
    ])

# Layout pour l'analyse d'activités
def build_activities_page_layout():
    return html.Div(style={'fontFamily': 'Inter, sans-serif', 'padding': '0', 'margin': '0', 'minHeight': '100vh', 'backgroundColor': '#f7fafc'}, children=[
        html.Div(style={'backgroundColor': '#1a202c', 'color': 'white', 'padding': '1rem', 'textAlign': 'center', 'position': 'relative'}, children=[
            # Logo Strava avec statut et bouton de connexion
            create_strava_status_component(),
            
            html.H1("🏆 KOM Hunters - Analyse d'Activités", style={'margin': '0 0 10px 0', 'fontSize': '1.8rem'}),
            html.Div(style={'display': 'flex', 'justifyContent': 'center', 'gap': '20px', 'marginBottom': '15px'}, children=[
                html.A(html.Button("🔍 Recherche de Segments", style={'padding': '10px 15px', 'backgroundColor': '#3182CE', 'color': 'white', 'border': 'none', 'borderRadius': '5px', 'cursor': 'pointer'}), href="/"),
                html.A(html.Button("📊 Analyse d'Activités", style={'padding': '10px 15px', 'backgroundColor': '#38A169', 'color': 'white', 'border': 'none', 'borderRadius': '5px', 'cursor': 'pointer'}), href="/activities")
            ])
        ]),
        
        html.Div(style={'padding': '20px', 'maxWidth': '1200px', 'margin': '0 auto'}, children=[
            html.Div(style={'backgroundColor': 'white', 'padding': '20px', 'borderRadius': '10px', 'boxShadow': '0 2px 10px rgba(0,0,0,0.1)', 'marginBottom': '20px'}, children=[
                html.H3("🚴 Sélectionnez une activité à analyser", style={'marginBottom': '15px', 'color': '#2d3748'}),
                html.Div(style={'display': 'flex', 'gap': '15px', 'alignItems': 'center', 'marginBottom': '15px'}, children=[
                    html.Button(f"📥 Charger mes {ACTIVITIES_PER_LOAD} dernières sorties vélo", id="load-activities-button", n_clicks=0,
                                style={'padding': '10px 15px', 'backgroundColor': '#3182CE', 'color': 'white', 'border': 'none', 'borderRadius': '5px', 'cursor': 'pointer'}),
                    html.Button("📥 Charger 10 de plus", id="load-more-activities-button", n_clicks=0, disabled=True,
                                style={'padding': '10px 15px', 'backgroundColor': '#4A5568', 'color': 'white', 'border': 'none', 'borderRadius': '5px', 'cursor': 'pointer'}),
                    html.Div(id='activities-load-status', style={'color': '#666'})
                ]),
                dcc.Dropdown(
                    id='activities-dropdown',
                    placeholder="Sélectionnez une activité...",
                    style={'marginBottom': '15px'},
                    disabled=True
                ),
                html.Div(style={'display': 'grid', 'gridTemplateColumns': '1fr 1fr 1fr', 'gap': '15px', 'marginBottom': '15px'}, children=[
                    html.Div([
                        html.Label("💓 FC Max (bpm):", style={'fontWeight': 'bold', 'marginBottom': '5px', 'display': 'block'}),
                        dcc.Input(id='fc-max-input', type='number', value=DEFAULT_FC_MAX, min=120, max=220,
                                  style={'width': '100%', 'padding': '8px', 'border': '1px solid #d1d5db', 'borderRadius': '5px'})
                    ]),
                    html.Div([
                        html.Label("⚡ FTP (watts):", style={'fontWeight': 'bold', 'marginBottom': '5px', 'display': 'block'}),
                        dcc.Input(id='ftp-input', type='number', value=DEFAULT_FTP, min=100, max=500,
                                  style={'width': '100%', 'padding': '8px', 'border': '1px solid #d1d5db', 'borderRadius': '5px'})
                    ]),
                    html.Div([
                        html.Label("⚖️ Poids (kg):", style={'fontWeight': 'bold', 'marginBottom': '5px', 'display': 'block'}),
                        dcc.Input(id='weight-input', type='number', value=DEFAULT_WEIGHT, min=40, max=150,
                                  style={'width': '100%', 'padding': '8px', 'border': '1px solid #d1d5db', 'borderRadius': '5px'})
                    ])
                ]),
                html.Button("🔍 Analyser cette activité", id="analyze-activity-button", n_clicks=0, disabled=True,
                            style={'padding': '12px 20px', 'backgroundColor': '#38A169', 'color': 'white', 'border': 'none', 'borderRadius': '5px', 'cursor': 'pointer', 'fontSize': '1rem', 'fontWeight': 'bold'})
            ]),
            
            dcc.Loading(
                id="loading-analysis",
                type="default",
                children=[
                    html.Div(id='activity-analysis-container', style={'backgroundColor': 'white', 'padding': '20px', 'borderRadius': '10px', 'boxShadow': '0 2px 10px rgba(0,0,0,0.1)', 'minHeight': '200px'})
                ]
            )
        ]),
        
        # Stores pour gérer les données
        dcc.Store(id='activities-store', data=[]),
        dcc.Store(id='current-page-store', data=1)
    ])

# Layout principal
app.layout = html.Div([
    dcc.Location(id='url', refresh=False), 
    html.Div(id='page-content') 
])

print("✅ Layout défini")

# --- Callbacks de Navigation et d'Authentification ---
@app.callback(
    Output('page-content', 'children'),
    Input('url', 'pathname'),
    Input('url', 'search')
)
def display_page_content(pathname, search_query_params):
    global current_strava_access_token 
    global current_refresh_token
    global token_expires_at
    global new_token_info_global
    
    if pathname == '/strava_callback' and search_query_params:
        print(f"🔄 Traitement OAuth - search_query_params = {search_query_params}")
        
        try:
            params = {}
            if search_query_params.startswith('?'):
                query_string = search_query_params[1:]
            else:
                query_string = search_query_params
                
            for param_pair in query_string.split('&'):
                if '=' in param_pair:
                    key, value = param_pair.split('=', 1)
                    params[key] = value
            
            print(f"📊 Paramètres analysés: {params}")
            
            auth_code = params.get('code')
            error = params.get('error')

            if error:
                new_token_info_global = f"❌ Erreur d'autorisation Strava: {error}"
                print(new_token_info_global)
            elif auth_code:
                print(f"🔑 Code d'autorisation Strava reçu: {auth_code[:20]}...")
                if STRAVA_CLIENT_ID and STRAVA_CLIENT_SECRET:
                    token_url = 'https://www.strava.com/oauth/token'
                    
                    payload = {
                        'client_id': STRAVA_CLIENT_ID,
                        'client_secret': STRAVA_CLIENT_SECRET,
                        'code': auth_code,
                        'grant_type': 'authorization_code'
                    }
                    
                    print(f"📤 Payload envoyé à Strava: {payload}")
                    
                    try:
                        response = requests.post(token_url, data=payload, timeout=15)
                        print(f"📨 Réponse Strava - Status: {response.status_code}")
                        print(f"📨 Réponse Strava - Content: {response.text}")
                        
                        response.raise_for_status()
                        token_data = response.json()
                        
                        current_strava_access_token = token_data.get('access_token')
                        refresh_token = token_data.get('refresh_token') 
                        expires_at = token_data.get('expires_at')
                        
                        # IMPORTANT : Stockage SEULEMENT en mémoire, pas dans .env
                        if current_strava_access_token:
                            current_refresh_token = refresh_token
                            token_expires_at = expires_at
                            print(f"✅ Nouveau Strava Access Token stocké en mémoire: ...{current_strava_access_token[-6:]}")
                        
                        new_token_info_global = (
                            f"🎉 CONNEXION RÉUSSIE !\n"
                            f"Token d'Accès: ...{current_strava_access_token[-6:] if current_strava_access_token else 'ERREUR'}\n"
                            f"Refresh Token: ...{refresh_token[-6:] if refresh_token else 'N/A'}\n"
                            f"Expire à (UTC): {datetime.utcfromtimestamp(expires_at).strftime('%Y-%m-%d %H:%M:%S') if expires_at else 'N/A'}\n"
                            f"✅ Vous êtes maintenant connecté à Strava !"
                        )
                        print(f"✅ Tokens Strava récupérés avec succès")
                        
                    except requests.exceptions.RequestException as e:
                        print(f"❌ Erreur lors de l'échange du code OAuth: {e}")
                        if hasattr(e, 'response') and e.response is not None:
                            print(f"📨 Contenu de l'erreur: {e.response.text}")
                            try:
                                error_json = e.response.json()
                                print(f"📨 Erreur JSON détaillée: {error_json}")
                                new_token_info_global = f"❌ Erreur API Strava: {error_json.get('message', 'Erreur inconnue')}"
                            except:
                                new_token_info_global = f"❌ Erreur API Strava: {e.response.status_code} - {e.response.text}"
                        else:
                            new_token_info_global = f"❌ Erreur lors de l'échange du code OAuth: {e}"
                else:
                    new_token_info_global = "❌ Erreur: Client ID ou Client Secret Strava non configurés."
            else:
                new_token_info_global = "❌ Erreur: Aucun code d'autorisation reçu de Strava."
                print("❌ Aucun code d'autorisation dans les paramètres")
                
        except Exception as e:
            print(f"❌ Erreur lors du traitement OAuth: {e}")
            new_token_info_global = f"❌ Erreur lors du traitement OAuth: {e}"
        
        return build_main_page_layout()
    
    elif pathname == '/strava_callback':
        return html.Div([
            html.H2("⏳ Traitement de l'autorisation Strava..."),
            html.P("Vous allez être redirigé(e) sous peu.", id="callback-message"),
            dcc.Interval(id='redirect-interval', interval=2000, n_intervals=0, max_intervals=1),
            dcc.Location(id='redirect-location', refresh=True)
        ])
    
    elif pathname == '/activities':
        return build_activities_page_layout()
    
    return build_main_page_layout()

@app.callback(
    Output('redirect-location', 'pathname'),
    Input('redirect-interval', 'n_intervals'),
    prevent_initial_call=True
)
def redirect_to_main(n_intervals):
    if n_intervals >= 1:
        return '/'
    return dash.no_update

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
    global current_strava_access_token 
    
    print(f"\n=== 🔍 DEBUT RECHERCHE DE SEGMENTS ===")
    print(f"Token disponible: {'✅' if current_strava_access_token else '❌'}")
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

    print(f"\n🔍 Vérification des accès:")
    print(f"Token Strava: {'✅ Présent' if current_strava_access_token else '❌ MANQUANT'}")
    print(f"Clé météo: {'✅ Présente' if WEATHER_API_KEY else '❌ MANQUANTE'}")
    print(f"Analyzer disponible: {'✅ OUI' if STRAVA_ANALYZER_AVAILABLE else '❌ NON'}")
    
    if not current_strava_access_token: 
        print("⛔ Arrêt: Token Strava manquant")
        return html.Div([
            html.H3("🔒 Token Strava manquant", style={'textAlign': 'center', 'color': 'orange', 'padding': '20px'}),
            html.P("Veuillez vous connecter via le bouton ci-dessus", style={'textAlign': 'center'})
        ]), "Erreur: Token Strava non disponible. Veuillez vous connecter via le bouton.", None
        
    if not WEATHER_API_KEY:
        print("⛔ Arrêt: Clé météo manquante")
        return html.Div([
            html.H3("⚙️ Configuration manquante", style={'textAlign': 'center', 'color': 'red', 'padding': '20px'})
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
            current_strava_access_token, WEATHER_API_KEY, 
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
            status_msg = f"😔 Aucun segment avec vent favorable trouvé autour de '{display_address}'. Essayez une autre zone ou revenez plus tard quand les conditions de vent seront différentes."
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
                                name=f"🚴 {segment['name']}",
                                text=[f"<b>🏆 {segment['name']}</b><br>📏 Distance: {segment.get('distance','N/A'):.0f}m<br>📈 Pente: {segment.get('avg_grade','N/A'):.1f}%<br>🧭 Cap: {segment.get('bearing','N/A')}°<br>💨 Effet Vent: +{segment.get('wind_effect_mps','N/A'):.2f} m/s<br><br>🔗 <b>Cliquez sur le segment pour accéder à Strava !</b>" for _ in lats],
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
        
        print(f"=== 🏁 FIN RECHERCHE DE SEGMENTS ===\n")
        
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

# === CALLBACKS POUR L'ANALYSE D'ACTIVITÉS ===
@app.callback(
    [Output('activities-store', 'data'),
     Output('activities-dropdown', 'options'),
     Output('activities-dropdown', 'disabled'),
     Output('activities-load-status', 'children'),
     Output('load-more-activities-button', 'disabled'),
     Output('current-page-store', 'data')],
    [Input('load-activities-button', 'n_clicks'),
     Input('load-more-activities-button', 'n_clicks')],
    [State('activities-store', 'data'),
     State('current-page-store', 'data')],
    prevent_initial_call=True
)
def load_activities(load_clicks, load_more_clicks, current_activities, current_page):
    """Charge les activités vélo avec la nouvelle logique améliorée"""
    global current_strava_access_token
    
    ctx = callback_context
    if not ctx.triggered:
        return [], [], True, "", True, 1
    
    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
    
    # Vérifier le token directement depuis la variable globale
    if not current_strava_access_token:
        return [], [], True, "Token Strava manquant. Veuillez vous connecter.", True, 1
    
    try:
        if trigger_id == 'load-activities-button':
            # Première charge - utiliser la nouvelle fonction
            print("=== 📥 CHARGEMENT INITIAL DES ACTIVITÉS VÉLO ===")
            cycling_activities, error = fetch_cycling_activities_until_target(
                current_strava_access_token, 
                target_count=ACTIVITIES_PER_LOAD
            )
            
            if error:
                return [], [], True, error, True, 1
            
            if not cycling_activities:
                return [], [], True, "Aucune activité vélo trouvée.", True, 1
            
            status_message = f"📊 {len(cycling_activities)} activités vélo chargées"
            can_load_more = len(cycling_activities) >= ACTIVITIES_PER_LOAD
            
        else:  # load-more-activities-button
            # Chargement supplémentaire
            print("=== 📥 CHARGEMENT D'ACTIVITÉS SUPPLÉMENTAIRES ===")
            new_activities, error = fetch_more_cycling_activities(
                current_strava_access_token,
                current_activities,
                additional_count=ACTIVITIES_PER_LOAD
            )
            
            if error:
                return current_activities, [], True, error, True, current_page
            
            # Combiner les activités
            cycling_activities = current_activities + new_activities
            
            if not new_activities:
                status_message = f"📊 {len(cycling_activities)} activités vélo au total (aucune nouvelle activité trouvée)"
                can_load_more = False
            else:
                status_message = f"📊 {len(cycling_activities)} activités vélo au total (+{len(new_activities)} ajoutées)"
                can_load_more = len(new_activities) >= ACTIVITIES_PER_LOAD
        
        # Créer les options pour le dropdown
        options = []
        for activity in cycling_activities:
            label = format_activity_for_dropdown(activity)
            options.append({'label': label, 'value': activity['id']})
        
        return cycling_activities, options, False, status_message, not can_load_more, current_page + 1
        
    except Exception as e:
        error_msg = f"Erreur lors du chargement des activités: {e}"
        print(f"❌ {error_msg}")
        return current_activities, [], True, error_msg, True, current_page

@app.callback(
    Output('analyze-activity-button', 'disabled'),
    Input('activities-dropdown', 'value')
)
def enable_analyze_button(selected_activity):
    """Active le bouton d'analyse quand une activité est sélectionnée"""
    return selected_activity is None

@app.callback(
    Output('activity-analysis-container', 'children'),
    [Input('analyze-activity-button', 'n_clicks')],
    [State('activities-dropdown', 'value'),
     State('activities-store', 'data'),
     State('fc-max-input', 'value'),
     State('ftp-input', 'value'),
     State('weight-input', 'value')],
    prevent_initial_call=True
)
def analyze_selected_activity(n_clicks, selected_activity_id, activities_data, fc_max, ftp, weight):
    """Analyse l'activité sélectionnée avec gestion des KOM"""
    global current_strava_access_token
    
    if n_clicks == 0 or not selected_activity_id:
        return html.Div("Sélectionnez une activité à analyser", style={'textAlign': 'center', 'color': '#666', 'padding': '20px'})
    
    # Vérifications des prérequis
    if not current_strava_access_token:
        return html.Div([
            html.H3("🔒 Token Strava manquant", style={'color': 'red', 'textAlign': 'center'}),
            html.P("Veuillez vous connecter avec Strava en utilisant le bouton de connexion en haut de la page.")
        ])
    
    if not OPENAI_API_KEY:
        return html.Div([
            html.H3("⚙️ Configuration manquante", style={'color': 'red', 'textAlign': 'center'}),
            html.P("La clé API OpenAI n'est pas configurée. Veuillez l'ajouter à votre fichier .env")
        ])
    
    if not STRAVA_ANALYZER_AVAILABLE:
        return html.Div([
            html.H3("🔧 Module d'analyse non disponible", style={'color': 'red', 'textAlign': 'center'}),
            html.P("Le module strava_analyzer n'a pas pu être importé."),
            html.P("Vérifiez que le fichier strava_analyzer.py est présent et que toutes les dépendances sont installées.", style={'fontSize': '0.9em', 'color': '#666'})
        ])
    
    # Trouver l'activité sélectionnée dans les données de base
    selected_activity_basic = None
    for activity in activities_data:
        if activity['id'] == selected_activity_id:
            selected_activity_basic = activity
            break
    
    if not selected_activity_basic:
        return html.Div("Activité non trouvée", style={'textAlign': 'center', 'color': 'red'})
    
    try:
        print(f"\n=== 🔍 DEBUT ANALYSE ACTIVITÉ {selected_activity_id} ===")
        print(f"Activité: {selected_activity_basic.get('name', 'Sans nom')}")
        
        # Récupérer les détails complets de l'activité avec les efforts de segments
        print("📊 Récupération des détails complets de l'activité avec efforts de segments...")
        selected_activity_complete = strava_analyzer.get_activity_details_with_efforts(
            selected_activity_id, current_strava_access_token
        )
        
        if not selected_activity_complete:
            return html.Div([
                html.H3("❌ Erreur de récupération", style={'color': 'red', 'textAlign': 'center'}),
                html.P("Impossible de récupérer les détails complets de l'activité depuis Strava.")
            ])
        
        # Chercher les KOM dans les efforts de segments
        kom_segments = []
        pr_segments = []
        top_segments = []
        
        if selected_activity_complete.get('segment_efforts'):
            for effort in selected_activity_complete['segment_efforts']:
                segment_name = effort.get('segment', {}).get('name', 'Segment inconnu')
                kom_rank = effort.get('kom_rank')
                pr_rank = effort.get('pr_rank')
                
                if kom_rank == 1:
                    kom_segments.append(segment_name)
                if pr_rank == 1:
                    pr_segments.append(segment_name)
                if kom_rank and kom_rank <= 10:
                    top_segments.append((segment_name, kom_rank))
        
        # Afficher d'abord les félicitations pour les KOM/PR si il y en a
        congratulations_content = []
        
        if kom_segments:
            congratulations_content.extend([
                html.Div([
                    html.H2("🏆 BRAVO ! NOUVEAU KOM ! 👑", 
                           style={'color': '#FFD700', 'textAlign': 'center', 'marginBottom': '10px', 
                                  'fontSize': '2em', 'fontWeight': 'bold', 'textShadow': '2px 2px 4px rgba(0,0,0,0.5)'}),
                    html.Div([
                        html.Span("Félicitations ! Tu viens de décrocher le KOM sur ", style={'fontSize': '1.2em'}),
                        html.Span(f"{len(kom_segments)} segment{'s' if len(kom_segments) > 1 else ''} :", 
                                 style={'fontSize': '1.2em', 'fontWeight': 'bold', 'color': '#FFD700'}),
                    ], style={'textAlign': 'center', 'marginBottom': '15px'}),
                    html.Ul([
                        html.Li([
                            html.Span("👑 ", style={'fontSize': '1.5em'}),
                            html.Span(segment_name, style={'fontWeight': 'bold', 'fontSize': '1.1em'})
                        ]) for segment_name in kom_segments
                    ], style={'listStyle': 'none', 'textAlign': 'center', 'fontSize': '1.1em'}),
                    html.P("Tu es maintenant le roi de la montagne sur ce segment ! Un exploit à célébrer !",
                           style={'textAlign': 'center', 'fontStyle': 'italic', 'color': '#4A5568', 'marginTop': '15px'})
                ], style={'backgroundColor': '#FFF8E7', 'padding': '20px', 'borderRadius': '15px', 
                         'border': '3px solid #FFD700', 'marginBottom': '25px', 'boxShadow': '0 4px 15px rgba(255,215,0,0.3)'})
            ])
        
        if pr_segments:
            congratulations_content.append(
                html.Div([
                    html.H3("🥇 Records Personnels établis !", 
                           style={'color': '#38A169', 'textAlign': 'center', 'marginBottom': '10px'}),
                    html.Ul([
                        html.Li([
                            html.Span("🏆 ", style={'fontSize': '1.3em'}),
                            html.Span(segment_name, style={'fontWeight': 'bold'})
                        ]) for segment_name in pr_segments
                    ], style={'listStyle': 'none', 'textAlign': 'center'}),
                    html.P("Tu as battu tes propres records ! Continue comme ça !",
                           style={'textAlign': 'center', 'fontStyle': 'italic', 'color': '#4A5568'})
                ], style={'backgroundColor': '#F0FFF4', 'padding': '15px', 'borderRadius': '10px', 
                         'border': '2px solid #38A169', 'marginBottom': '20px'})
            )
        
        print(f"🏆 KOM trouvés: {len(kom_segments)}, PR trouvés: {len(pr_segments)}")
        print(f"⚙️ FC Max: {fc_max}, FTP: {ftp}, Poids: {weight}")
        
        # Appeler la fonction d'analyse avec les détails complets
        analysis_result = strava_analyzer.generate_activity_report_with_overall_summary(
            activity_id=selected_activity_id,
            access_token_strava=current_strava_access_token,
            openai_api_key=OPENAI_API_KEY,
            user_fc_max=fc_max,
            user_ftp=ftp,
            user_weight_kg=weight,
            weather_api_key=WEATHER_API_KEY,
            notable_rank_threshold=10,
            num_best_segments_to_analyze=2
        )
        
        print(f"=== ✅ ANALYSE TERMINÉE ===\n")
        
        # Construire l'affichage du résultat
        content_children = congratulations_content.copy()  # Commencer par les félicitations
        
        # Titre de l'activité avec informations de base
        activity_info = []
        if selected_activity_complete.get('distance'):
            activity_info.append(f"Distance: {round(selected_activity_complete['distance'] / 1000, 1)}km")
        if selected_activity_complete.get('total_elevation_gain'):
            activity_info.append(f"D+: {selected_activity_complete['total_elevation_gain']}m")
        if selected_activity_complete.get('moving_time'):
            duration_hours = selected_activity_complete['moving_time'] // 3600
            duration_minutes = (selected_activity_complete['moving_time'] % 3600) // 60
            activity_info.append(f"Durée: {duration_hours}h{duration_minutes:02d}min")
        
        content_children.append(
            html.Div([
                html.H2(analysis_result['activity_name'], 
                       style={'color': '#1a202c', 'marginBottom': '5px', 'textAlign': 'center'}),
                html.P(" | ".join(activity_info), 
                       style={'color': '#666', 'textAlign': 'center', 'marginBottom': '20px'})
            ])
        )
        
        # Afficher la description si elle existe
        if selected_activity_complete.get('description'):
            content_children.append(
                html.Div([
                    html.H4("📝 Description de la sortie", style={'color': '#4A5568', 'marginBottom': '10px'}),
                    html.Div(
                        selected_activity_complete['description'],
                        style={
                            'backgroundColor': '#EDF2F7', 
                            'padding': '12px', 
                            'borderRadius': '6px',
                            'marginBottom': '20px',
                            'fontStyle': 'italic',
                            'borderLeft': '3px solid #CBD5E0'
                        }
                    )
                ])
            )
        
        # Résumé global
        if analysis_result['overall_summary']:
            content_children.append(
                html.Div([
                    html.H3("📊 Résumé de la sortie", style={'color': '#2d3748', 'borderBottom': '2px solid #3182CE', 'paddingBottom': '5px'}),
                    html.Div(
                        analysis_result['overall_summary'],
                        style={
                            'backgroundColor': '#f7fafc', 
                            'padding': '15px', 
                            'borderRadius': '8px',
                            'marginBottom': '25px',
                            'lineHeight': '1.6',
                            'whiteSpace': 'pre-wrap'
                        }
                    )
                ])
            )
        
        # Analyses des segments avec classements formatés
        if analysis_result['segment_reports']:
            content_children.append(
                html.H3("🎯 Analyses détaillées des segments les plus performants", 
                    style={'color': '#2d3748', 'borderBottom': '2px solid #38A169', 'paddingBottom': '5px', 'marginBottom': '20px'})
            )
            
            for i, segment_report in enumerate(analysis_result['segment_reports']):
                segment_name = segment_report['segment_name']
                
                # Récupérer les informations de classement depuis les données complètes
                segment_ranking_display = ""
                try:
                    if selected_activity_complete.get('segment_efforts'):
                        for effort in selected_activity_complete['segment_efforts']:
                            if effort.get('segment', {}).get('name') == segment_name:
                                kom_rank = effort.get('kom_rank')
                                pr_rank = effort.get('pr_rank')
                                
                                ranking_parts = []
                                if pr_rank == 1:
                                    ranking_parts.append("🥇 Record Personnel")
                                if kom_rank:
                                    if kom_rank == 1:
                                        ranking_parts.append("👑 KOM!")
                                    elif kom_rank <= 3:
                                        ranking_parts.append(f"🥉 Top {kom_rank}")
                                    elif kom_rank <= 10:
                                        ranking_parts.append(f"🏆 Top {kom_rank}")
                                    else:
                                        ranking_parts.append(f"#{kom_rank}")
                                
                                if ranking_parts:
                                    segment_ranking_display = f" - {' | '.join(ranking_parts)}"
                                break
                except Exception as e:
                    print(f"❌ Erreur lors de la récupération du classement pour {segment_name}: {e}")
                
                segment_header = f"{segment_name}{segment_ranking_display}"
                
                content_children.append(
                    html.Div([
                        html.H4(segment_header, 
                            style={'color': '#38A169', 'marginBottom': '10px'}),
                        html.Div(
                            segment_report['report'],
                            style={
                                'backgroundColor': '#f0fff4',
                                'padding': '15px',
                                'borderRadius': '8px',
                                'marginBottom': '20px',
                                'borderLeft': '4px solid #38A169',
                                'lineHeight': '1.6',
                                'whiteSpace': 'pre-wrap'
                            }
                        )
                    ])
                )
        else:
            content_children.append(
                html.Div([
                    html.Div("😊 Aucun segment notable détecté", style={'fontSize': '1.2em', 'marginBottom': '10px'}),
                    html.P("Cette activité ne contient pas de records personnels ou de top 10 sur des segments.", 
                           style={'fontStyle': 'italic', 'color': '#666'}),
                    html.P("💡 Astuce: Les analyses se concentrent sur vos meilleures performances pour vous aider à progresser !", 
                           style={'color': '#3182CE', 'fontWeight': 'bold'})
                ], style={'textAlign': 'center', 'padding': '30px', 'backgroundColor': '#F7FAFC', 'borderRadius': '8px'})
            )
        
        return html.Div(content_children)
        
    except Exception as e:
        print(f"❌ ERREUR lors de l'analyse: {e}")
        return html.Div([
            html.H3("❌ Erreur lors de l'analyse", style={'color': 'red', 'textAlign': 'center'}),
            html.P(f"Détails: {str(e)}", style={'color': '#666', 'textAlign': 'center'}),
            html.P("Essayez de recharger la page ou vérifiez votre connexion Strava.", 
                   style={'color': '#3182CE', 'textAlign': 'center', 'fontStyle': 'italic'})
        ])

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
                    html.P(f"🚴 Segment sélectionné: {segment_name}", 
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
                    html.P("💡 Conseil: Vous pouvez aussi cliquer sur d'autres segments colorés de la carte", 
                           style={'fontSize': '0.85em', 'color': '#6B7280', 'margin': '8px 0 0 0', 'fontStyle': 'italic'})
                ], style={'textAlign': 'center', 'padding': '10px'})
        
        return dash.no_update
        
    except Exception as e:
        print(f"❌ Erreur lors du traitement du clic sur segment: {e}")
        return dash.no_update

print("✅ Tous les callbacks définis")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8050))
    debug_mode = os.environ.get('RENDER') is None
    
    required_keys = [MAPBOX_ACCESS_TOKEN, STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET, WEATHER_API_KEY]
    if not all(required_keys):
        print("❌ ERREUR CRITIQUE: Une ou plusieurs clés/ID API sont manquants.")
    print(f"\n🚀 LANCEMENT KOM HUNTERS")
    print(f"🌐 Mode: {'Développement' if debug_mode else 'Production'}")
    print(f"🔗 URL: {BASE_URL}")
    print(f"📊 Pages disponibles:")
    print(f"   - {BASE_URL}/ (Recherche segments)")
    print(f"   - {BASE_URL}/activities (Analyse activités)")
    print(f"🔧 Configuration Strava callback: {STRAVA_REDIRECT_URI}")
    
    app.run_server(debug=debug_mode, host='0.0.0.0', port=port)