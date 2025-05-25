import dash
from dash import dcc, html, Input, Output, State, callback_context
import plotly.graph_objects as go
import os
from dotenv import load_dotenv
import time 
import math 
import json 
import requests 
from datetime import datetime
import base64

# Pour le géocodage
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderUnavailable

# --- AJOUT POUR S'ASSURER QUE LE RÉPERTOIRE ACTUEL EST DANS SYS.PATH ---
import sys
current_script_directory = os.path.dirname(os.path.abspath(__file__))
if current_script_directory not in sys.path:
    sys.path.insert(0, current_script_directory)
print(f"--- DEBUG (app_dash): Répertoire du script ajouté à sys.path: {current_script_directory} ---")

# --- IMPORTATION DE VOTRE LIBRAIRIE PERSONNALISÉE ---
try:
    import strava_analyzer 
    print(f"--- DEBUG (app_dash): Module 'strava_analyzer' importé. Chemin: {strava_analyzer.__file__} ---")
except ModuleNotFoundError:
    print(f"--- DEBUG (app_dash): ERREUR CRITIQUE - Module 'strava_analyzer' non trouvé dans sys.path: {sys.path} ---")
    sys.exit("Arrêt: strava_analyzer.py est introuvable.")
except Exception as e:
    print(f"--- DEBUG (app_dash): Erreur inattendue lors de l'import de strava_analyzer: {e} ---")
    sys.exit("Arrêt: Erreur d'import de strava_analyzer.")

# --- Configuration Initiale ---
load_dotenv() 
MAPBOX_ACCESS_TOKEN = os.getenv('MAPBOX_ACCESS_TOKEN')
STRAVA_CLIENT_ID = os.getenv('STRAVA_CLIENT_ID') 
STRAVA_CLIENT_SECRET = os.getenv('STRAVA_CLIENT_SECRET')
# IMPORTANT : On ne charge plus les tokens depuis .env, ils seront récupérés via OAuth uniquement
current_strava_access_token = None  # Sera mis à jour SEULEMENT via OAuth
current_refresh_token = None        # Sera mis à jour SEULEMENT via OAuth
token_expires_at = None            # Sera mis à jour SEULEMENT via OAuth
new_token_info_global = "Cliquez sur 'Se connecter' pour récupérer vos tokens Strava."
WEATHER_API_KEY = os.getenv('OPENWEATHERMAP_API_KEY')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

print(f"--- DEBUG (app_dash): Token Mapbox: {'Présent' if MAPBOX_ACCESS_TOKEN else 'MANQUANT'} ---")
print(f"--- DEBUG (app_dash): Strava Client ID: {'Présent' if STRAVA_CLIENT_ID else 'MANQUANT'} ---")
print(f"--- DEBUG (app_dash): Strava Client Secret: {'Présent' if STRAVA_CLIENT_SECRET else 'MANQUANT'} ---")
print(f"--- DEBUG (app_dash): Token Strava initial: AUCUN (sera récupéré via OAuth) ---")
print(f"--- DEBUG (app_dash): Clé OpenWeatherMap: {'Présente' if WEATHER_API_KEY else 'MANQUANTE'} ---")
print(f"--- DEBUG (app_dash): Clé OpenAI: {'Présente' if OPENAI_API_KEY else 'MANQUANTE'} ---")

# Configuration pour l'analyse d'activités
ACTIVITIES_PER_LOAD = 10  # Nombre d'activités vélo à charger à chaque fois
CYCLING_ACTIVITY_TYPES = ['Ride', 'VirtualRide', 'EBikeRide', 'Gravel', 'MountainBikeRide']  # Types d'activités vélo
DEFAULT_FC_MAX = 190  # FC max par défaut
DEFAULT_FTP = 250     # FTP par défaut en watts
DEFAULT_WEIGHT = 70   # Poids par défaut en kg

INITIAL_LAT = 46.2276  
INITIAL_LNG = 2.2137
INITIAL_ZOOM = 5
SEARCH_RADIUS_KM = 10
SUB_ZONE_RADIUS_KM = 5.0
MIN_TAILWIND_EFFECT_MPS_SEARCH = 0.7
STRAVA_REDIRECT_URI = 'http://localhost:8050/strava_callback' 
STRAVA_SCOPES = 'read,activity:read_all,profile:read_all'

print(f"--- DEBUG (app_dash): Configuration super optimisee ---")
print(f"--- Rayon total: {SEARCH_RADIUS_KM}km | Zones: {SUB_ZONE_RADIUS_KM}km | Seuil: {MIN_TAILWIND_EFFECT_MPS_SEARCH} m/s ---")

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
        print(f"--- ATTENTION: Logo Strava non trouvé à {logo_path} ---")
        return None
    except Exception as e:
        print(f"--- ERREUR: Impossible de charger le logo Strava: {e} ---")
        return None

# --- Composant du logo Strava avec statut et bouton de connexion ---
def create_strava_status_component():
    """Crée le composant du logo Strava avec indicateur de statut et bouton de connexion si nécessaire"""
    global current_strava_access_token
    
    logo_src = get_strava_logo_base64()
    # IMPORTANT : On est connecté SEULEMENT si on a récupéré un token via OAuth dans cette session
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
    
    Args:
        access_token: Token d'accès Strava
        target_count: Nombre d'activités vélo souhaité
        max_pages: Nombre maximum de pages à parcourir
    
    Returns:
        tuple: (cycling_activities, error_message)
    """
    if not access_token:
        return [], "Token Strava manquant"
    
    headers = {'Authorization': f'Bearer {access_token}'}
    url = 'https://www.strava.com/api/v3/athlete/activities'
    
    all_cycling_activities = []
    page = 1
    per_page = 30  # On récupère plus d'activités par page pour être efficace
    
    print(f"--- DEBUG: Recherche de {target_count} activités vélo ---")
    
    try:
        while len(all_cycling_activities) < target_count and page <= max_pages:
            print(f"--- DEBUG: Récupération page {page}, {per_page} activités par page ---")
            
            params = {
                'page': page,
                'per_page': per_page
            }
            
            response = requests.get(url, headers=headers, params=params, timeout=15)
            response.raise_for_status()
            
            activities = response.json()
            
            if not activities:  # Plus d'activités disponibles
                print(f"--- DEBUG: Plus d'activités disponibles après page {page-1} ---")
                break
            
            # Filtrer les activités vélo de cette page
            page_cycling_activities = []
            for activity in activities:
                if activity.get('type') in CYCLING_ACTIVITY_TYPES:
                    page_cycling_activities.append(activity)
            
            all_cycling_activities.extend(page_cycling_activities)
            
            print(f"--- DEBUG: Page {page}: {len(activities)} activités totales, {len(page_cycling_activities)} vélo")
            print(f"--- DEBUG: Total activités vélo accumulées: {len(all_cycling_activities)}/{target_count} ---")
            
            # Si on a moins d'activités que demandé sur cette page, on a probablement atteint la fin
            if len(activities) < per_page:
                print(f"--- DEBUG: Fin des activités atteinte (page {page} avec seulement {len(activities)} activités) ---")
                break
                
            page += 1
            time.sleep(0.2)  # Petit délai pour respecter les limites de l'API
        
        # Limiter au nombre cible si on a plus que demandé
        if len(all_cycling_activities) > target_count:
            all_cycling_activities = all_cycling_activities[:target_count]
        
        print(f"--- DEBUG: Récupération terminée: {len(all_cycling_activities)} activités vélo trouvées ---")
        return all_cycling_activities, None
        
    except requests.exceptions.HTTPError as e:
        error_msg = f"Erreur HTTP API Strava: {e}"
        if hasattr(e, 'response') and e.response is not None:
            if e.response.status_code == 401:
                error_msg = "Token Strava expiré ou invalide. Veuillez vous reconnecter."
            elif e.response.status_code == 429:
                error_msg = "Limite de taux API Strava atteinte. Veuillez patienter."
        print(f"--- ERREUR: {error_msg} ---")
        return [], error_msg
    except Exception as e:
        error_msg = f"Erreur lors de la récupération des activités: {e}"
        print(f"--- ERREUR: {error_msg} ---")
        return [], error_msg

# --- Fonction pour charger plus d'activités ---
def fetch_more_cycling_activities(access_token, existing_activities, additional_count=ACTIVITIES_PER_LOAD):
    """
    Récupère des activités vélo supplémentaires en continuant après les activités existantes.
    
    Args:
        access_token: Token d'accès Strava
        existing_activities: Liste des activités déjà récupérées
        additional_count: Nombre d'activités supplémentaires souhaité
    
    Returns:
        tuple: (new_cycling_activities, error_message)
    """
    if not access_token:
        return [], "Token Strava manquant"
    
    # Calculer à partir de quelle page commencer
    # On assume qu'on récupère ~30 activités par page en moyenne
    existing_count = len(existing_activities)
    estimated_start_page = max(1, (existing_count // 20) + 1)  # Estimation conservative
    
    print(f"--- DEBUG: Chargement de {additional_count} activités supplémentaires ---")
    print(f"--- DEBUG: {existing_count} activités existantes, estimation page de départ: {estimated_start_page} ---")
    
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
            print(f"--- DEBUG: Récupération page {page} pour plus d'activités ---")
            
            params = {
                'page': page,
                'per_page': per_page
            }
            
            response = requests.get(url, headers=headers, params=params, timeout=15)
            response.raise_for_status()
            
            activities = response.json()
            
            if not activities:
                print(f"--- DEBUG: Plus d'activités disponibles après page {page} ---")
                break
            
            # Filtrer les nouvelles activités vélo (pas déjà présentes)
            new_cycling_activities = []
            for activity in activities:
                if (activity.get('type') in CYCLING_ACTIVITY_TYPES and 
                    activity['id'] not in existing_ids):
                    new_cycling_activities.append(activity)
            
            all_new_activities.extend(new_cycling_activities)
            
            print(f"--- DEBUG: Page {page}: {len(new_cycling_activities)} nouvelles activités vélo")
            print(f"--- DEBUG: Total nouvelles activités vélo: {len(all_new_activities)}/{additional_count} ---")
            
            if len(activities) < per_page:
                print(f"--- DEBUG: Fin des activités atteinte ---")
                break
                
            page += 1
            pages_tried += 1
            time.sleep(0.2)
        
        # Limiter au nombre demandé
        if len(all_new_activities) > additional_count:
            all_new_activities = all_new_activities[:additional_count]
        
        print(f"--- DEBUG: Chargement terminé: {len(all_new_activities)} nouvelles activités vélo ---")
        return all_new_activities, None
        
    except requests.exceptions.HTTPError as e:
        error_msg = f"Erreur HTTP API Strava: {e}"
        if hasattr(e, 'response') and e.response is not None:
            if e.response.status_code == 401:
                error_msg = "Token Strava expiré ou invalide. Veuillez vous reconnecter."
            elif e.response.status_code == 429:
                error_msg = "Limite de taux API Strava atteinte. Veuillez patienter."
        print(f"--- ERREUR: {error_msg} ---")
        return [], error_msg
    except Exception as e:
        error_msg = f"Erreur lors de la récupération des activités supplémentaires: {e}"
        print(f"--- ERREUR: {error_msg} ---")
        return [], error_msg

# --- Fonctions Utilitaires pour les Activités (existantes modifiées) ---
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

def format_segment_ranking(effort_data):
    """Formate le classement d'un segment avec des émojis"""
    kom_rank = effort_data.get('kom_rank')
    pr_rank = effort_data.get('pr_rank')
    
    ranking_parts = []
    
    # Record personnel
    if pr_rank == 1:
        ranking_parts.append("🏆 Record Personnel")
    
    # Classement général
    if kom_rank:
        if kom_rank == 1:
            ranking_parts.append("👑 KOM!")
        elif kom_rank <= 3:
            ranking_parts.append(f"🥉 Top {kom_rank}")
        elif kom_rank <= 10:
            ranking_parts.append(f"🏆 Top {kom_rank}")
        else:
            ranking_parts.append(f"#{kom_rank}")
    
    return " | ".join(ranking_parts) if ranking_parts else "Belle performance!"

def get_address_suggestions(query_str, limit=5):
    if not query_str or len(query_str) < 2:
        return [], None 
    geolocator = Nominatim(user_agent="kom_hunters_dash_suggestions_v4")
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
    geolocator = Nominatim(user_agent="kom_hunters_dash_geocode_v4")
    try:
        location = geolocator.geocode(address_str, timeout=10)
        if location:
            return (location.latitude, location.longitude), None, location.address
        return None, f"Adresse non trouvée ou ambiguë : '{address_str}'.", address_str
    except Exception as e:
        return None, f"Erreur de géocodage: {e}", address_str

# --- Initialisation de l'Application Dash ---
app = dash.Dash(__name__, external_stylesheets=['https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap']) 
app.title = "KOM Hunters - Dashboard"
app.config.suppress_callback_exceptions = True

# Utilisation du template HTML externe
try:
    app.index_string = open('templates/index.html', 'r', encoding='utf-8').read()
except FileNotFoundError:
    try:
        app.index_string = open('index.html', 'r', encoding='utf-8').read()
    except FileNotFoundError:
        print("AVERTISSEMENT: Fichier index.html non trouvé, utilisation du template par défaut")
        pass

# === STRUCTURE DES TEMPLATES HTML ===
# - segments_page.html : Template pour la page principale (recherche de segments)
# - activities.html : Template pour la page d'analyse d'activités  
# - templates/index.html : Template de base Dash (meta tags, CSS globaux)
# Les templates contiennent le HTML/CSS, app_dash.py ne contient que la logique Python/callbacks

# --- Fonction pour charger et parser le template HTML de la page principale ---
def load_main_page_template():
    """Charge le template HTML pour la page principale et le convertit en composants Dash"""
    template_path = os.path.join(current_script_directory, 'segments_page.html')
    fallback_path = 'segments_page.html'
    
    try:
        if os.path.exists(template_path):
            with open(template_path, 'r', encoding='utf-8') as f:
                html_content = f.read()
        elif os.path.exists(fallback_path):
            with open(fallback_path, 'r', encoding='utf-8') as f:
                html_content = f.read()
        else:
            print("AVERTISSEMENT: Fichier segments_page.html non trouvé, utilisation du layout par défaut")
            return build_main_page_layout_default()
            
        print("✅ Template segments_page.html chargé avec succès")
        return build_main_page_from_template()
        
    except Exception as e:
        print(f"ERREUR lors du chargement du template principal: {e}")
        return build_main_page_layout_default()

# --- Layout principal (utilisant le template) ---
def build_main_page_from_template():
    """Construit la page principale en utilisant la structure du template HTML"""
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

# --- Layout principal (version par défaut en cas d'erreur) ---
def build_main_page_layout_default():
    """Version par défaut du layout principal si le template ne peut pas être chargé"""
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

# --- Fonction pour charger et parser le template HTML ---
def load_activities_template():
    """Charge le template HTML pour la page d'activités et le convertit en composants Dash"""
    template_path = os.path.join(current_script_directory, 'activities.html')
    fallback_path = 'activities.html'
    
    try:
        if os.path.exists(template_path):
            with open(template_path, 'r', encoding='utf-8') as f:
                html_content = f.read()
        elif os.path.exists(fallback_path):
            with open(fallback_path, 'r', encoding='utf-8') as f:
                html_content = f.read()
        else:
            print("AVERTISSEMENT: Fichier activities.html non trouvé, utilisation du layout par défaut")
            return build_activities_page_layout_default()
            
        print("✅ Template activities.html chargé avec succès")
        return build_activities_page_from_template()
        
    except Exception as e:
        print(f"ERREUR lors du chargement du template: {e}")
        return build_activities_page_layout_default()

# --- Layout pour l'analyse d'activités (utilisant le template) ---
def build_activities_page_from_template():
    """Construit la page d'activités en utilisant la structure du template HTML"""
    global current_strava_access_token
    
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

# --- Layout pour l'analyse d'activités (version par défaut en cas d'erreur) ---
def build_activities_page_layout_default():
    """Version par défaut du layout si le template ne peut pas être chargé"""
    global current_strava_access_token
    
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

# --- Layout de l'Application (Shell) ---
app.layout = html.Div([
    dcc.Location(id='url', refresh=False), 
    html.Div(id='page-content')
])

# --- Callbacks de Navigation et d'Authentification ---
@app.callback(
    Output('page-content', 'children'),
    [Input('url', 'pathname'),
     Input('url', 'search')]
)
def display_page_content(pathname, search_query_params):
    global current_strava_access_token 
    global current_refresh_token
    global token_expires_at
    global new_token_info_global
    
    if pathname == '/strava_callback' and search_query_params:
        print(f"DEBUG display_page_content: Traitement OAuth - search_query_params = {search_query_params}")
        
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
            
            print(f"Parametres analyses: {params}")
            
            auth_code = params.get('code')
            error = params.get('error')

            if error:
                new_token_info_global = f"Erreur d'autorisation Strava: {error}"
                print(new_token_info_global)
            elif auth_code:
                print(f"Code d'autorisation Strava reçu: {auth_code[:20]}...")
                if STRAVA_CLIENT_ID and STRAVA_CLIENT_SECRET:
                    token_url = 'https://www.strava.com/oauth/token'
                    
                    payload = {
                        'client_id': STRAVA_CLIENT_ID,
                        'client_secret': STRAVA_CLIENT_SECRET,
                        'code': auth_code,
                        'grant_type': 'authorization_code'
                    }
                    
                    print(f"Payload envoye à Strava: {payload}")
                    
                    try:
                        response = requests.post(token_url, data=payload, timeout=15)
                        print(f"Reponse Strava - Status: {response.status_code}")
                        print(f"Reponse Strava - Content: {response.text}")
                        
                        response.raise_for_status()
                        token_data = response.json()
                        
                        current_strava_access_token = token_data.get('access_token')
                        refresh_token = token_data.get('refresh_token') 
                        expires_at = token_data.get('expires_at')
                        
                        # IMPORTANT : On stocke SEULEMENT en mémoire, pas dans .env
                        if current_strava_access_token:
                            # Stocker en variables globales pour cette session
                            global current_refresh_token, token_expires_at
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
                        print(f"✅ Tokens Strava récupérés avec succès: {new_token_info_global}")
                        
                    except requests.exceptions.RequestException as e:
                        print(f"Erreur lors de l'échange du code OAuth: {e}")
                        if hasattr(e, 'response') and e.response is not None:
                            print(f"Contenu de l'erreur: {e.response.text}")
                            try:
                                error_json = e.response.json()
                                print(f"Erreur JSON detaillee: {error_json}")
                                new_token_info_global = f"Erreur API Strava: {error_json.get('message', 'Erreur inconnue')}"
                            except:
                                new_token_info_global = f"Erreur API Strava: {e.response.status_code} - {e.response.text}"
                        else:
                            new_token_info_global = f"Erreur lors de l'échange du code OAuth: {e}"
                else:
                    new_token_info_global = "Erreur: Client ID ou Client Secret Strava non configurés."
            else:
                new_token_info_global = "Erreur: Aucun code d'autorisation reçu de Strava."
                print("Aucun code d'autorisation dans les parametres")
                
        except Exception as e:
            print(f"Erreur lors du traitement OAuth: {e}")
            new_token_info_global = f"Erreur lors du traitement OAuth: {e}"
        
        return load_main_page_template()
    
    elif pathname == '/strava_callback':
        return html.Div([
            html.H2("Traitement de l'autorisation Strava..."),
            html.P("Vous allez être redirigé(e) sous peu.", id="callback-message"),
            dcc.Interval(id='redirect-interval', interval=2000, n_intervals=0, max_intervals=1),
            dcc.Location(id='redirect-location', refresh=True)
        ])
    
    elif pathname == '/activities':
        return load_activities_template()
    
    return load_main_page_template()

@app.callback(
    Output('redirect-location', 'pathname'),
    Input('redirect-interval', 'n_intervals'),
    prevent_initial_call=True
)
def redirect_to_main(n_intervals):
    if n_intervals >= 1:
        return '/'
    return dash.no_update

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
    # CORRECTION: Utiliser directement la variable globale au lieu du store
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
            print("=== CHARGEMENT INITIAL DES ACTIVITÉS VÉLO ===")
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
            print("=== CHARGEMENT D'ACTIVITÉS SUPPLÉMENTAIRES ===")
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
        print(f"--- ERREUR: {error_msg} ---")
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
    # CORRECTION: Utiliser directement la variable globale au lieu du store
    global current_strava_access_token
    
    if n_clicks == 0 or not selected_activity_id:
        return html.Div("Sélectionnez une activité à analyser", style={'textAlign': 'center', 'color': '#666', 'padding': '20px'})
    
    # Vérifications des prérequis - utiliser directement la variable globale
    if not current_strava_access_token:
        return html.Div([
            html.H3("Token Strava manquant", style={'color': 'red', 'textAlign': 'center'}),
            html.P("Veuillez vous connecter avec Strava en utilisant le bouton de connexion en haut de la page.")
        ])
    
    if not OPENAI_API_KEY:
        return html.Div([
            html.H3("Configuration manquante", style={'color': 'red', 'textAlign': 'center'}),
            html.P("La clé API OpenAI n'est pas configurée. Veuillez l'ajouter à votre fichier .env")
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
        print(f"\n=== DEBUT ANALYSE ACTIVITÉ {selected_activity_id} ===")
        print(f"Activité: {selected_activity_basic.get('name', 'Sans nom')}")
        
        # NOUVEAU : Récupérer les détails complets de l'activité avec les efforts de segments
        print("Récupération des détails complets de l'activité avec efforts de segments...")
        selected_activity_complete = strava_analyzer.get_activity_details_with_efforts(
            selected_activity_id, current_strava_access_token
        )
        
        if not selected_activity_complete:
            return html.Div([
                html.H3("Erreur de récupération", style={'color': 'red', 'textAlign': 'center'}),
                html.P("Impossible de récupérer les détails complets de l'activité depuis Strava.")
            ])
        
        # NOUVEAU : Chercher les KOM dans les efforts de segments
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
        
        # NOUVEAU : Afficher d'abord les félicitations pour les KOM/PR si il y en a
        congratulations_content = []
        
        if kom_segments:
            congratulations_content.extend([
                html.Div([
                    html.H2("BRAVO ! NOUVEAU KOM !", 
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
                    html.H3("Records Personnels établis !", 
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
        
        print(f"KOM trouvés: {len(kom_segments)}, PR trouvés: {len(pr_segments)}")
        print(f"FC Max: {fc_max}, FTP: {ftp}, Poids: {weight}")
        
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
        
        print(f"=== ANALYSE TERMINÉE ===\n")
        
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
                    html.H4("Description de la sortie", style={'color': '#4A5568', 'marginBottom': '10px'}),
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
                    html.H3("Résumé de la sortie", style={'color': '#2d3748', 'borderBottom': '2px solid #3182CE', 'paddingBottom': '5px'}),
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
                html.H3("Analyses détaillées des segments les plus performants", 
                    style={'color': '#2d3748', 'borderBottom': '2px solid #38A169', 'paddingBottom': '5px', 'marginBottom': '20px'})
            )
            
            for i, segment_report in enumerate(analysis_result['segment_reports']):
                segment_name = segment_report['segment_name']
                
                # NOUVEAU : Récupérer les informations de classement depuis les données complètes
                segment_ranking_display = ""
                try:
                    if selected_activity_complete.get('segment_efforts'):
                        for effort in selected_activity_complete['segment_efforts']:
                            if effort.get('segment', {}).get('name') == segment_name:
                                kom_rank = effort.get('kom_rank')
                                pr_rank = effort.get('pr_rank')
                                
                                ranking_parts = []
                                if pr_rank == 1:
                                    ranking_parts.append("Record Personnel")
                                if kom_rank:
                                    if kom_rank == 1:
                                        ranking_parts.append("KOM!")
                                    elif kom_rank <= 3:
                                        ranking_parts.append(f"Top {kom_rank}")
                                    elif kom_rank <= 10:
                                        ranking_parts.append(f"Top {kom_rank}")
                                    else:
                                        ranking_parts.append(f"#{kom_rank}")
                                
                                if ranking_parts:
                                    segment_ranking_display = f" - {' | '.join(ranking_parts)}"
                                break
                except Exception as e:
                    print(f"Erreur lors de la récupération du classement pour {segment_name}: {e}")
                
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
                    html.Div("Aucun segment notable détecté", style={'fontSize': '1.2em', 'marginBottom': '10px'}),
                    html.P("Cette activité ne contient pas de records personnels ou de top 10 sur des segments.", 
                           style={'fontStyle': 'italic', 'color': '#666'}),
                    html.P("Astuce: Les analyses se concentrent sur vos meilleures performances pour vous aider à progresser !", 
                           style={'color': '#3182CE', 'fontWeight': 'bold'})
                ], style={'textAlign': 'center', 'padding': '30px', 'backgroundColor': '#F7FAFC', 'borderRadius': '8px'})
            )
        
        return html.Div(content_children)
        
    except Exception as e:
        print(f"ERREUR lors de l'analyse: {e}")
        return html.Div([
            html.H3("Erreur lors de l'analyse", style={'color': 'red', 'textAlign': 'center'}),
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
        print(f"Erreur lors du traitement du clic sur segment: {e}")
        return dash.no_update

# --- Callbacks pour la recherche d'adresse et de segments (page principale) ---
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
        print(f"Erreur parsing ID suggestion: {e}, ID: {triggered_id_str}")
        raise dash.exceptions.PreventUpdate
    
    current_suggestions_data, _ = get_address_suggestions(original_address_input, limit=5)
    if current_suggestions_data and 0 <= clicked_index < len(current_suggestions_data):
        selected_suggestion = current_suggestions_data[clicked_index]
        print(f"Suggestion sélectionnée: {selected_suggestion['display_name']}")
        
        hidden_style = {'display': 'none'}
        
        return selected_suggestion['display_name'], selected_suggestion, [], hidden_style
    
    return dash.no_update, dash.no_update, [], {'display': 'none'}

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
    # CORRECTION: Utiliser directement la variable globale au lieu du store
    global current_strava_access_token
    
    print(f"\n=== DEBUT RECHERCHE DE SEGMENTS ===")
    print(f"Nombre de clics: {n_clicks}")
    print(f"Valeur input: '{address_input_value}'")
    print(f"Suggestion stockee: {selected_suggestion_data}")
    print(f"Token global disponible: {'✅ OUI' if current_strava_access_token else '❌ NON'}")
    
    # Utiliser directement la variable globale pour être sûr d'avoir le bon token
    
    search_lat, search_lon = None, None
    display_address = ""
    error_message_search = None

    try:
        if selected_suggestion_data and selected_suggestion_data.get('lat') is not None:
            search_lat = selected_suggestion_data['lat']
            search_lon = selected_suggestion_data['lon']
            display_address = selected_suggestion_data['display_name']
            print(f"Coordonnees depuis suggestion: {search_lat:.4f}, {search_lon:.4f} - '{display_address}'")
        elif address_input_value:
            print(f"Geocodage direct pour: '{address_input_value}'")
            coords, error_msg, addr_disp = geocode_address_directly(address_input_value)
            if coords:
                search_lat, search_lon = coords
                display_address = addr_disp
                print(f"Geocodage reussi: {search_lat:.4f}, {search_lon:.4f} - '{display_address}'")
            else: 
                error_message_search = error_msg
                print(f"Erreur de geocodage: {error_msg}")
        else: 
            error_message_search = "Veuillez entrer une adresse ou sélectionner une suggestion."
            print("Aucune adresse fournie")
    except Exception as e:
        error_message_search = f"Erreur lors de la détermination des coordonnées: {e}"
        print(f"Exception lors du geocodage: {e}")

    if error_message_search:
        print(f"Retour avec erreur: {error_message_search}")
        return html.Div([
            html.H3("Erreur", style={'textAlign': 'center', 'color': 'red', 'padding': '20px'})
        ]), f"Erreur: {error_message_search}", None 

    if search_lat is None or search_lon is None: 
        print("Coordonnees invalides")
        return html.Div([
            html.H3("Coordonnées invalides", style={'textAlign': 'center', 'color': 'red', 'padding': '20px'})
        ]), "Impossible de déterminer les coordonnées pour la recherche.", None

    print(f"\nVerification des acces:")
    print(f"Token Strava: {'Present (' + str(len(current_strava_access_token)) + ' caracteres)' if current_strava_access_token else 'MANQUANT'}")
    print(f"Cle meteo: {'Presente' if WEATHER_API_KEY else 'MANQUANTE'}")
    
    if not current_strava_access_token: 
        print("Arret: Token Strava manquant")
        return html.Div([
            html.H3("Token Strava manquant", style={'textAlign': 'center', 'color': 'orange', 'padding': '20px'}),
            html.P("Veuillez vous connecter via le bouton ci-dessus", style={'textAlign': 'center'})
        ]), "Erreur: Token Strava non disponible. Veuillez vous connecter via le bouton.", None
        
    if not WEATHER_API_KEY:
        print("Arret: Cle meteo manquante")
        return html.Div([
            html.H3("Configuration manquante", style={'textAlign': 'center', 'color': 'red', 'padding': '20px'})
        ]), "Erreur de configuration serveur: Clé API Météo manquante.", None

    try:
        print(f"\nLancement de la recherche de segments avec vent favorable...")
        found_segments, segments_error_msg = strava_analyzer.find_tailwind_segments_live( 
            search_lat, search_lon, SEARCH_RADIUS_KM, 
            current_strava_access_token, WEATHER_API_KEY, 
            MIN_TAILWIND_EFFECT_MPS_SEARCH
        )
        
        if segments_error_msg:
            print(f"Erreur lors de la recherche: {segments_error_msg}")
            return html.Div([
                html.H3("Erreur de recherche", style={'textAlign': 'center', 'color': 'red', 'padding': '20px'}),
                html.P(f"{segments_error_msg}", style={'textAlign': 'center'})
            ]), f"Erreur lors de la recherche de segments: {segments_error_msg}", None
            
        print(f"Recherche terminee: {len(found_segments)} segment(s) trouve(s)")
        
    except Exception as e:
        print(f"Exception lors de la recherche de segments: {e}")
        return html.Div([
            html.H3("Erreur inattendue", style={'textAlign': 'center', 'color': 'red', 'padding': '20px'})
        ]), f"Erreur inattendue lors de la recherche: {e}", None

    # Création de la carte
    try:
        print(f"\nCreation de la carte...")
        fig = go.Figure() 

        status_msg = ""
        if not found_segments:
            status_msg = f"Aucun segment avec vent favorable trouvé autour de '{display_address}'. Essayez une autre zone ou revenez plus tard quand les conditions de vent seront différentes."
            print("Aucun segment avec vent favorable")
            
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
            print(f"Ajout de {len(found_segments)} segment(s) a la carte...")
            
            all_segment_lats = []
            all_segment_lons = []
            
            for i, segment in enumerate(found_segments):
                try:
                    if segment.get("polyline_coords") and len(segment["polyline_coords"]) >= 2: 
                        coords = segment["polyline_coords"]
                        lats = [coord[0] for coord in coords if coord[0] is not None]
                        lons = [coord[1] for coord in coords if coord[1] is not None]
                        
                        if len(lats) >= 2 and len(lons) >= 2:
                            print(f"  Segment {i+1}: '{segment['name']}' - {len(lats)} points valides")
                            
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
                            print(f"    Segment ajoute avec succes et interaction configuree")
                        else:
                            print(f"  Segment {i+1}: '{segment['name']}' - coordonnees invalides")
                    else:
                        print(f"  Segment {i+1}: '{segment.get('name')}' sans coordonnees ou trop court")
                except Exception as segment_error:
                    print(f"  Erreur ajout segment {i+1}: {segment_error}")

            if all_segment_lats and all_segment_lons:
                center_lat = sum(all_segment_lats) / len(all_segment_lats)
                center_lon = sum(all_segment_lons) / len(all_segment_lons)
                
                lat_range = max(all_segment_lats) - min(all_segment_lats)
                lon_range = max(all_segment_lons) - min(all_segment_lons)
                max_range = max(lat_range, lon_range)
                max_range_with_margin = max_range * 1.4
                
                print(f"Centre calcule: ({center_lat:.6f}, {center_lon:.6f})")
                
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
                    
                print(f"Zoom calculé: {zoom_level}")
                    
            else:
                center_lat, center_lon = search_lat, search_lon
                zoom_level = 14
                print("Fallback: utilisation des coordonnees de recherche")

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
        
        print(f"=== FIN RECHERCHE DE SEGMENTS ===\n")
        
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
        print(f"Erreur lors de la creation de la carte: {e}")
        return html.Div([
            html.H3("Erreur d'affichage", style={'textAlign': 'center', 'color': 'red', 'padding': '20px'}),
            html.P(f"Détails: {e}", style={'textAlign': 'center', 'fontSize': '0.9em'})
        ]), f"Erreur lors de l'affichage des résultats: {e}", None
    

# Configuration pour le déploiement
server = app.server

# Détection automatique de l'environnement pour l'URL de callback
import os
if os.getenv('RENDER'):
    BASE_URL = f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}"
else:
    BASE_URL = 'http://localhost:8050'

# Mise à jour de l'URL de callback Strava
STRAVA_REDIRECT_URI = f'{BASE_URL}/strava_callback'

# --- Exécution de l'Application ---
if __name__ == '__main__':
    # Configuration pour développement ET production
    port = int(os.environ.get('PORT', 8050))
    debug_mode = os.environ.get('RENDER') is None  # Debug seulement en local
    
    print("🚀 Lancement de KOM Hunters Dashboard !")
    print("📱 Pages disponibles:")
    if debug_mode:
        print("- http://127.0.0.1:8050/ : 🔍 Recherche de segments avec vent favorable")
        print("- http://127.0.0.1:8050/activities : 📊 Analyse d'activités vélo")
    else:
        print(f"- {BASE_URL}/ : 🔍 Recherche de segments avec vent favorable")
        print(f"- {BASE_URL}/activities : 📊 Analyse d'activités vélo")
    
    app.run(debug=debug_mode, host='0.0.0.0', port=port)