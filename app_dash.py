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
    print(f"--- DEBUG (app_dash): Module 'strava_analyzer' importé avec succès ---")
except ModuleNotFoundError:
    print(f"--- DEBUG (app_dash): ERREUR CRITIQUE - Module 'strava_analyzer' non trouvé ---")
    sys.exit("Arrêt: strava_analyzer.py est introuvable.")
except Exception as e:
    print(f"--- DEBUG (app_dash): Erreur lors de l'import de strava_analyzer: {e} ---")
    sys.exit("Arrêt: Erreur d'import de strava_analyzer.")

# --- Configuration Initiale ---
load_dotenv() 

# Configuration des APIs
MAPBOX_ACCESS_TOKEN = os.getenv('MAPBOX_ACCESS_TOKEN')
STRAVA_CLIENT_ID = os.getenv('STRAVA_CLIENT_ID') 
STRAVA_CLIENT_SECRET = os.getenv('STRAVA_CLIENT_SECRET')
WEATHER_API_KEY = os.getenv('OPENWEATHERMAP_API_KEY')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

# Configuration dynamique de l'URL de callback
if os.getenv('RENDER'):
    # En production sur Render
    BASE_URL = f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME', 'kom-hunters.onrender.com')}"
elif os.getenv('RAILWAY_STATIC_URL'):
    # Sur Railway
    BASE_URL = os.getenv('RAILWAY_STATIC_URL')
elif os.getenv('HEROKU_APP_NAME'):
    # Sur Heroku
    BASE_URL = f"https://{os.getenv('HEROKU_APP_NAME')}.herokuapp.com"
else:
    # En développement local
    BASE_URL = 'http://localhost:8050'

STRAVA_REDIRECT_URI = f'{BASE_URL}/strava_callback'
STRAVA_SCOPES = 'read,activity:read_all,profile:read_all'

print(f"--- DEBUG (app_dash): Configuration URLs ---")
print(f"BASE_URL: {BASE_URL}")
print(f"STRAVA_REDIRECT_URI: {STRAVA_REDIRECT_URI}")
print(f"--- DEBUG (app_dash): Token Mapbox: {'Présent' if MAPBOX_ACCESS_TOKEN else 'MANQUANT'} ---")
print(f"--- DEBUG (app_dash): Strava Client ID: {'Présent' if STRAVA_CLIENT_ID else 'MANQUANT'} ---")
print(f"--- DEBUG (app_dash): Strava Client Secret: {'Présent' if STRAVA_CLIENT_SECRET else 'MANQUANT'} ---")
print(f"--- DEBUG (app_dash): Clé OpenWeatherMap: {'Présente' if WEATHER_API_KEY else 'MANQUANTE'} ---")
print(f"--- DEBUG (app_dash): Clé OpenAI: {'Présente' if OPENAI_API_KEY else 'MANQUANTE'} ---")

# Variables globales pour gérer les tokens par session
# NOTE: En production, vous devriez utiliser Redis ou une base de données
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

# Configuration pour la recherche de segments
SEARCH_RADIUS_KM = 10
MIN_TAILWIND_EFFECT_MPS_SEARCH = 0.7

# --- Fonctions Utilitaires ---
def fetch_strava_activities(access_token, page=1, per_page=ACTIVITIES_PER_LOAD):
    """Récupère les activités depuis l'API Strava"""
    if not access_token:
        return [], "Token Strava manquant"
    
    headers = {'Authorization': f'Bearer {access_token}'}
    url = 'https://www.strava.com/api/v3/athlete/activities'
    params = {
        'page': page,
        'per_page': per_page
    }
    
    try:
        print(f"--- DEBUG: Récupération activités page {page}, {per_page} par page ---")
        response = requests.get(url, headers=headers, params=params, timeout=15)
        response.raise_for_status()
        
        activities = response.json()
        
        # Filtrer seulement les activités de vélo
        cycling_activities = []
        for activity in activities:
            if activity.get('type') in CYCLING_ACTIVITY_TYPES:
                cycling_activities.append(activity)
        
        print(f"--- DEBUG: {len(activities)} activités récupérées, {len(cycling_activities)} activités vélo ---")
        return cycling_activities, None
        
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
    geolocator = Nominatim(user_agent="kom_hunters_dash_v5")
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
    geolocator = Nominatim(user_agent="kom_hunters_dash_v5")
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

# Configuration du serveur pour le déploiement
server = app.server

# Template HTML sécurisé
template_path = os.path.join(os.path.dirname(__file__), 'templates', 'index.html')
try:
    with open(template_path, 'r', encoding='utf-8') as f:
        app.index_string = f.read()
        print("✅ Template HTML externe chargé")
except FileNotFoundError:
    print("⚠️ Template index.html non trouvé, utilisation du template par défaut")

# --- Fonction pour créer le bouton de connexion Strava ---
def create_strava_connect_button():
    """Crée le bouton de connexion Strava"""
    global current_strava_access_token
    
    is_connected = bool(current_strava_access_token and len(current_strava_access_token.strip()) > 20)
    
    if is_connected:
        return html.Div([
            html.Div("✅ Connecté à Strava", style={
                'color': '#10B981',
                'fontWeight': 'bold',
                'fontSize': '0.9rem',
                'padding': '8px 16px',
                'backgroundColor': 'rgba(16, 185, 129, 0.1)',
                'border': '2px solid #10B981',
                'borderRadius': '8px'
            })
        ])
    else:
        auth_url = (
            f"https://www.strava.com/oauth/authorize?"
            f"client_id={STRAVA_CLIENT_ID}"
            f"&redirect_uri={STRAVA_REDIRECT_URI}"
            f"&response_type=code"
            f"&approval_prompt=force"
            f"&scope={STRAVA_SCOPES}"
        )
        
        return html.A(
            html.Button([
                html.Span("🔗 ", style={'marginRight': '8px'}),
                "Se connecter avec Strava"
            ], style={
                'padding': '12px 20px',
                'backgroundColor': '#FC4C02',
                'color': 'white',
                'border': 'none',
                'borderRadius': '8px',
                'fontSize': '1rem',
                'fontWeight': '600',
                'cursor': 'pointer',
                'transition': 'all 0.3s ease',
                'boxShadow': '0 4px 12px rgba(252, 76, 2, 0.3)'
            }),
            href=auth_url,
            style={'textDecoration': 'none'}
        )

# --- Layout pour la page principale ---
def build_main_page_layout():
    global new_token_info_global
    
    return html.Div(style={
        'fontFamily': 'Inter, sans-serif', 
        'padding': '0', 
        'margin': '0', 
        'height': '100vh', 
        'display': 'flex', 
        'flexDirection': 'column'
    }, children=[
        # Header
        html.Div(style={
            'backgroundColor': '#1a202c', 
            'color': 'white', 
            'padding': '1.5rem', 
            'textAlign': 'center', 
            'flexShrink': '0',
            'boxShadow': '0 4px 6px rgba(0, 0, 0, 0.1)'
        }, children=[
            html.H1("🏆 KOM Hunters", style={
                'margin': '0 0 15px 0', 
                'fontSize': '2.2rem', 
                'fontWeight': '700',
                'background': 'linear-gradient(135deg, #ffffff 0%, #e2e8f0 100%)',
                'WebkitBackgroundClip': 'text',
                'WebkitTextFillColor': 'transparent'
            }),
            
            # Navigation
            html.Div(style={
                'display': 'flex', 
                'justifyContent': 'center', 
                'gap': '20px', 
                'marginBottom': '20px'
            }, children=[
                html.A(html.Button("🔍 Recherche de Segments", style={
                    'padding': '10px 15px', 
                    'backgroundColor': '#3182CE', 
                    'color': 'white', 
                    'border': 'none', 
                    'borderRadius': '6px', 
                    'cursor': 'pointer',
                    'fontWeight': '500'
                }), href="/"),
                html.A(html.Button("📊 Analyse d'Activités", style={
                    'padding': '10px 15px', 
                    'backgroundColor': '#38A169', 
                    'color': 'white', 
                    'border': 'none', 
                    'borderRadius': '6px', 
                    'cursor': 'pointer',
                    'fontWeight': '500'
                }), href="/activities")
            ]),
            
            # Connexion Strava
            html.Div(style={'marginBottom': '20px'}, children=[
                create_strava_connect_button()
            ]),
            
            # Statut
            html.Div(id='new-token-info-display', children=new_token_info_global, style={
                'color': '#A0AEC0', 
                'fontSize': '0.85rem', 
                'whiteSpace': 'pre-line',
                'marginBottom': '20px'
            }),
            
            # Interface de recherche
            html.Div(style={
                'display': 'flex', 
                'flexDirection': 'column', 
                'alignItems': 'center', 
                'gap': '15px'
            }, children=[ 
                html.Div(style={'position': 'relative', 'width': '500px', 'maxWidth': '90vw'}, children=[
                    dcc.Input(
                        id='address-input', 
                        type='text', 
                        placeholder='Tapez une ville ou une adresse (ex: Lyon, France)...',
                        debounce=False,
                        style={
                            'padding': '12px 16px', 
                            'fontSize': '1rem', 
                            'borderRadius': '8px', 
                            'border': '2px solid #4A5568', 
                            'width': '100%', 
                            'backgroundColor': '#2D3748', 
                            'color': '#E2E8F0', 
                            'boxSizing': 'border-box',
                            'transition': 'all 0.3s ease'
                        }
                    ),
                    html.Div(id='live-address-suggestions-container')
                ]),
                html.Button('🚀 Chercher les Segments !', id='search-button', n_clicks=0, style={
                    'padding': '12px 24px', 
                    'fontSize': '1.1rem', 
                    'backgroundColor': '#3182CE', 
                    'color': 'white', 
                    'border': 'none', 
                    'borderRadius': '8px', 
                    'cursor': 'pointer',
                    'fontWeight': '600',
                    'boxShadow': '0 4px 12px rgba(49, 130, 206, 0.3)',
                    'transition': 'all 0.3s ease'
                })
            ]),
            
            # Message de statut
            html.Div(id='search-status-message', style={
                'marginTop': '15px', 
                'minHeight': '24px', 
                'color': '#A0AEC0',
                'fontSize': '1rem'
            })
        ]),
        
        # Conteneur de résultats
        dcc.Loading(
            id="loading-map-results", 
            type="default",
            children=[html.Div(id='map-results-container', style={
                'flexGrow': '1',
                'minHeight': '0'
            })]
        ),
        
        # Stores
        dcc.Store(id='selected-suggestion-store', data=None)
    ])

# --- Layout pour l'analyse d'activités ---
def build_activities_page_layout():
    return html.Div(style={
        'fontFamily': 'Inter, sans-serif', 
        'padding': '0', 
        'margin': '0', 
        'minHeight': '100vh', 
        'backgroundColor': '#f7fafc'
    }, children=[
        # Header
        html.Div(style={
            'backgroundColor': '#1a202c', 
            'color': 'white', 
            'padding': '1.5rem', 
            'textAlign': 'center'
        }, children=[
            html.H1("📊 KOM Hunters - Analyse d'Activités", style={
                'margin': '0 0 15px 0', 
                'fontSize': '2rem', 
                'fontWeight': '700'
            }),
            
            # Navigation
            html.Div(style={
                'display': 'flex', 
                'justifyContent': 'center', 
                'gap': '20px', 
                'marginBottom': '15px'
            }, children=[
                html.A(html.Button("🔍 Recherche de Segments", style={
                    'padding': '10px 15px', 
                    'backgroundColor': '#3182CE', 
                    'color': 'white', 
                    'border': 'none', 
                    'borderRadius': '6px', 
                    'cursor': 'pointer'
                }), href="/"),
                html.A(html.Button("📊 Analyse d'Activités", style={
                    'padding': '10px 15px', 
                    'backgroundColor': '#38A169', 
                    'color': 'white', 
                    'border': 'none', 
                    'borderRadius': '6px', 
                    'cursor': 'pointer'
                }), href="/activities")
            ]),
            
            # Connexion Strava
            create_strava_connect_button()
        ]),
        
        # Contenu principal
        html.Div(style={'padding': '20px', 'maxWidth': '1200px', 'margin': '0 auto'}, children=[
            html.Div(style={
                'backgroundColor': 'white', 
                'padding': '25px', 
                'borderRadius': '12px', 
                'boxShadow': '0 4px 6px rgba(0, 0, 0, 0.1)', 
                'marginBottom': '20px'
            }, children=[
                html.H3("🚴 Analysez vos performances", style={
                    'marginBottom': '20px', 
                    'color': '#2d3748',
                    'fontSize': '1.5rem'
                }),
                
                # Boutons de chargement
                html.Div(style={
                    'display': 'flex', 
                    'gap': '15px', 
                    'alignItems': 'center', 
                    'marginBottom': '20px',
                    'flexWrap': 'wrap'
                }, children=[
                    html.Button(f"📥 Charger mes {ACTIVITIES_PER_LOAD} dernières sorties vélo", 
                               id="load-activities-button", 
                               n_clicks=0,
                               style={
                                   'padding': '12px 18px', 
                                   'backgroundColor': '#3182CE', 
                                   'color': 'white', 
                                   'border': 'none', 
                                   'borderRadius': '6px', 
                                   'cursor': 'pointer',
                                   'fontWeight': '500'
                               }),
                    html.Button("📥 Charger 10 de plus", 
                               id="load-more-activities-button", 
                               n_clicks=0, 
                               disabled=True,
                               style={
                                   'padding': '12px 18px', 
                                   'backgroundColor': '#4A5568', 
                                   'color': 'white', 
                                   'border': 'none', 
                                   'borderRadius': '6px', 
                                   'cursor': 'pointer'
                               }),
                    html.Div(id='activities-load-status', style={'color': '#666', 'fontWeight': '500'})
                ]),
                
                # Dropdown des activités
                dcc.Dropdown(
                    id='activities-dropdown',
                    placeholder="Sélectionnez une activité à analyser...",
                    style={'marginBottom': '20px'},
                    disabled=True
                ),
                
                # Paramètres utilisateur
                html.Div(style={
                    'display': 'grid', 
                    'gridTemplateColumns': 'repeat(auto-fit, minmax(200px, 1fr))', 
                    'gap': '20px', 
                    'marginBottom': '20px'
                }, children=[
                    html.Div([
                        html.Label("💓 FC Max (bpm):", style={
                            'fontWeight': 'bold', 
                            'marginBottom': '8px', 
                            'display': 'block',
                            'color': '#4a5568'
                        }),
                        dcc.Input(
                            id='fc-max-input', 
                            type='number', 
                            value=DEFAULT_FC_MAX, 
                            min=120, 
                            max=220,
                            style={
                                'width': '100%', 
                                'padding': '10px', 
                                'border': '2px solid #d1d5db', 
                                'borderRadius': '6px',
                                'fontSize': '1rem'
                            }
                        )
                    ]),
                    html.Div([
                        html.Label("⚡ FTP (watts):", style={
                            'fontWeight': 'bold', 
                            'marginBottom': '8px', 
                            'display': 'block',
                            'color': '#4a5568'
                        }),
                        dcc.Input(
                            id='ftp-input', 
                            type='number', 
                            value=DEFAULT_FTP, 
                            min=100, 
                            max=500,
                            style={
                                'width': '100%', 
                                'padding': '10px', 
                                'border': '2px solid #d1d5db', 
                                'borderRadius': '6px',
                                'fontSize': '1rem'
                            }
                        )
                    ]),
                    html.Div([
                        html.Label("⚖️ Poids (kg):", style={
                            'fontWeight': 'bold', 
                            'marginBottom': '8px', 
                            'display': 'block',
                            'color': '#4a5568'
                        }),
                        dcc.Input(
                            id='weight-input', 
                            type='number', 
                            value=DEFAULT_WEIGHT, 
                            min=40, 
                            max=150,
                            style={
                                'width': '100%', 
                                'padding': '10px', 
                                'border': '2px solid #d1d5db', 
                                'borderRadius': '6px',
                                'fontSize': '1rem'
                            }
                        )
                    ])
                ]),
                
                # Bouton d'analyse
                html.Button("🔬 Analyser cette activité", 
                           id="analyze-activity-button", 
                           n_clicks=0, 
                           disabled=True,
                           style={
                               'padding': '15px 25px', 
                               'backgroundColor': '#38A169', 
                               'color': 'white', 
                               'border': 'none', 
                               'borderRadius': '8px', 
                               'cursor': 'pointer', 
                               'fontSize': '1.1rem', 
                               'fontWeight': 'bold',
                               'boxShadow': '0 4px 12px rgba(56, 161, 105, 0.3)'
                           })
            ]),
            
            # Conteneur de résultats
            dcc.Loading(
                id="loading-analysis",
                type="default",
                children=[
                    html.Div(id='activity-analysis-container', style={
                        'backgroundColor': 'white', 
                        'padding': '25px', 
                        'borderRadius': '12px', 
                        'boxShadow': '0 4px 6px rgba(0, 0, 0, 0.1)', 
                        'minHeight': '200px'
                    })
                ]
            )
        ]),
        
        # Stores
        dcc.Store(id='activities-store', data=[]),
        dcc.Store(id='current-page-store', data=1)
    ])

# --- Layout de l'Application ---
app.layout = html.Div([
    dcc.Location(id='url', refresh=False), 
    html.Div(id='page-content')
])

# --- Callbacks de Navigation ---
@app.callback(
    Output('page-content', 'children'),
    [Input('url', 'pathname'), Input('url', 'search')]
)
def display_page_content(pathname, search_query_params):
    global current_strava_access_token, current_refresh_token, token_expires_at, new_token_info_global
    
    # Traitement du callback OAuth Strava
    if pathname == '/strava_callback' and search_query_params:
        print(f"DEBUG: Traitement OAuth - {search_query_params}")
        
        try:
            # Parser les paramètres de l'URL
            params = {}
            if search_query_params.startswith('?'):
                query_string = search_query_params[1:]
            else:
                query_string = search_query_params
                
            for param_pair in query_string.split('&'):
                if '=' in param_pair:
                    key, value = param_pair.split('=', 1)
                    params[key] = value
            
            auth_code = params.get('code')
            error = params.get('error')

            if error:
                new_token_info_global = f"❌ Erreur d'autorisation Strava: {error}"
                print(new_token_info_global)
            elif auth_code:
                print(f"✅ Code d'autorisation reçu: {auth_code[:20]}...")
                
                if STRAVA_CLIENT_ID and STRAVA_CLIENT_SECRET:
                    # Échanger le code contre un token
                    token_url = 'https://www.strava.com/oauth/token'
                    payload = {
                        'client_id': STRAVA_CLIENT_ID,
                        'client_secret': STRAVA_CLIENT_SECRET,
                        'code': auth_code,
                        'grant_type': 'authorization_code'
                    }
                    
                    try:
                        response = requests.post(token_url, data=payload, timeout=15)
                        response.raise_for_status()
                        token_data = response.json()
                        
                        current_strava_access_token = token_data.get('access_token')
                        current_refresh_token = token_data.get('refresh_token')
                        token_expires_at = token_data.get('expires_at')
                        
                        if current_strava_access_token:
                            new_token_info_global = (
                                f"🎉 CONNEXION RÉUSSIE !\n"
                                f"✅ Vous êtes maintenant connecté à Strava\n"
                                f"Token valide jusqu'au: {datetime.fromtimestamp(token_expires_at).strftime('%d/%m/%Y %H:%M') if token_expires_at else 'N/A'}"
                            )
                            print(f"✅ Token Strava obtenu avec succès")
                        else:
                            new_token_info_global = "❌ Erreur lors de la récupération du token"
                            
                    except requests.exceptions.RequestException as e:
                        error_msg = f"Erreur API Strava: {e}"
                        if hasattr(e, 'response') and e.response is not None:
                            try:
                                error_json = e.response.json()
                                error_msg = f"Erreur API Strava: {error_json.get('message', 'Erreur inconnue')}"
                            except:
                                error_msg = f"Erreur API Strava: {e.response.status_code}"
                        new_token_info_global = error_msg
                        print(f"❌ {error_msg}")
                        
                else:
                    new_token_info_global = "❌ Configuration Strava manquante (Client ID/Secret)"
            else:
                new_token_info_global = "❌ Aucun code d'autorisation reçu"
                
        except Exception as e:
            new_token_info_global = f"❌ Erreur lors du traitement OAuth: {e}"
            print(f"❌ Erreur OAuth: {e}")
        
        return build_main_page_layout()
    
    # Redirection après callback
    elif pathname == '/strava_callback':
        return html.Div([
            html.H2("🔄 Traitement de l'autorisation Strava..."),
            html.P("Redirection en cours..."),
            dcc.Interval(id='redirect-interval', interval=2000, n_intervals=0, max_intervals=1),
            dcc.Location(id='redirect-location', refresh=True)
        ])
    
    # Page d'analyse d'activités
    elif pathname == '/activities':
        return build_activities_page_layout()
    
    # Page principale par défaut
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

# === CALLBACKS POUR LES ACTIVITÉS ===
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
    global current_strava_access_token
    
    ctx = callback_context
    if not ctx.triggered:
        return [], [], True, "", True, 1
    
    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
    
    if not current_strava_access_token:
        return [], [], True, "❌ Token Strava manquant. Connectez-vous d'abord.", True, 1
    
    # Déterminer la page à charger
    if trigger_id == 'load-activities-button':
        page_to_load = 1
        activities_to_keep = []
    else:
        page_to_load = current_page + 1
        activities_to_keep = current_activities
    
    # Récupérer les nouvelles activités
    new_activities, error = fetch_strava_activities(current_strava_access_token, page=page_to_load)
    
    if error:
        return current_activities, [], True, f"❌ {error}", True, current_page
    
    # Combiner les activités
    all_activities = activities_to_keep + new_activities
    
    if not all_activities:
        return [], [], True, "❌ Aucune activité vélo trouvée.", True, 1
    
    # Créer les options pour le dropdown
    options = []
    for activity in all_activities:
        label = format_activity_for_dropdown(activity)
        options.append({'label': label, 'value': activity['id']})
    
    # Message de statut
    if trigger_id == 'load-activities-button':
        status_message = f"✅ {len(all_activities)} activités vélo chargées"
    else:
        status_message = f"✅ {len(all_activities)} activités au total (+{len(new_activities)} ajoutées)"
    
    can_load_more = len(new_activities) >= ACTIVITIES_PER_LOAD
    
    return all_activities, options, False, status_message, not can_load_more, page_to_load

@app.callback(
    Output('analyze-activity-button', 'disabled'),
    Input('activities-dropdown', 'value')
)
def enable_analyze_button(selected_activity):
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
    global current_strava_access_token
    
    if n_clicks == 0 or not selected_activity_id:
        return html.Div("Sélectionnez une activité à analyser", style={
            'textAlign': 'center', 
            'color': '#666', 
            'padding': '40px',
            'fontSize': '1.1rem'
        })
    
    if not current_strava_access_token:
        return html.Div([
            html.H3("❌ Token Strava manquant", style={'color': 'red', 'textAlign': 'center'}),
            html.P("Veuillez vous connecter avec Strava.")
        ])
    
    if not OPENAI_API_KEY:
        return html.Div([
            html.H3("❌ Configuration manquante", style={'color': 'red', 'textAlign': 'center'}),
            html.P("La clé API OpenAI n'est pas configurée.")
        ])
    
    # Trouver l'activité sélectionnée
    selected_activity = None
    for activity in activities_data:
        if activity['id'] == selected_activity_id:
            selected_activity = activity
            break
    
    if not selected_activity:
        return html.Div("❌ Activité non trouvée", style={'textAlign': 'center', 'color': 'red'})
    
    try:
        print(f"\n=== ANALYSE ACTIVITÉ {selected_activity_id} ===")
        
        # Appel à l'analyseur
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
        
        content_children = []
        
        # Titre de l'activité
        content_children.append(
            html.H2(analysis_result['activity_name'], style={
                'color': '#1a202c', 
                'marginBottom': '20px', 
                'textAlign': 'center',
                'fontSize': '1.8rem'
            })
        )
        
        # Résumé global
        if analysis_result['overall_summary']:
            content_children.append(
                html.Div([
                    html.H3("📋 Résumé de la sortie", style={
                        'color': '#2d3748', 
                        'borderBottom': '2px solid #3182CE', 
                        'paddingBottom': '8px',
                        'marginBottom': '15px'
                    }),
                    html.Div(analysis_result['overall_summary'], style={
                        'backgroundColor': '#f7fafc', 
                        'padding': '20px', 
                        'borderRadius': '8px',
                        'marginBottom': '25px',
                        'lineHeight': '1.6',
                        'whiteSpace': 'pre-wrap'
                    })
                ])
            )
        
        # Analyses des segments
        if analysis_result['segment_reports']:
            content_children.append(
                html.H3("🎯 Analyses détaillées des segments", style={
                    'color': '#2d3748', 
                    'borderBottom': '2px solid #38A169', 
                    'paddingBottom': '8px', 
                    'marginBottom': '20px'
                })
            )
            
            for segment_report in analysis_result['segment_reports']:
                content_children.append(
                    html.Div([
                        html.H4(segment_report['segment_name'], style={
                            'color': '#38A169', 
                            'marginBottom': '12px',
                            'fontSize': '1.3rem'
                        }),
                        html.Div(segment_report['report'], style={
                            'backgroundColor': '#f0fff4',
                            'padding': '18px',
                            'borderRadius': '8px',
                            'marginBottom': '20px',
                            'borderLeft': '4px solid #38A169',
                            'lineHeight': '1.6',
                            'whiteSpace': 'pre-wrap'
                        })
                    ])
                )
        else:
            content_children.append(
                html.Div([
                    html.H3("ℹ️ Aucun segment notable", style={'color': '#666', 'textAlign': 'center'}),
                    html.P("Cette activité ne contient pas de performances remarquables sur des segments.", 
                           style={'fontStyle': 'italic', 'color': '#666', 'textAlign': 'center'}),
                    html.P("💡 Les analyses se concentrent sur vos meilleures performances !", 
                           style={'color': '#3182CE', 'fontWeight': 'bold', 'textAlign': 'center'})
                ], style={'padding': '40px', 'backgroundColor': '#F7FAFC', 'borderRadius': '8px'})
            )
        
        return html.Div(content_children)
        
    except Exception as e:
        print(f"❌ ERREUR analyse: {e}")
        return html.Div([
            html.H3("❌ Erreur lors de l'analyse", style={'color': 'red', 'textAlign': 'center'}),
            html.P(f"Détails: {str(e)}", style={'color': '#666', 'textAlign': 'center'}),
            html.P("Essayez de recharger ou vérifiez votre connexion.", 
                   style={'color': '#3182CE', 'textAlign': 'center', 'fontStyle': 'italic'})
        ])

# === CALLBACKS POUR LA RECHERCHE D'ADRESSES ===
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
            'borderRadius': '8px', 'marginTop': '4px',
            'position': 'absolute', 'top': '100%', 'zIndex': '1000', 'textAlign': 'left',
            'left': '0', 'right': '0', 'boxShadow': '0 4px 15px rgba(0,0,0,0.15)'
        }
        return [html.P(f"Erreur : {error}", style={'padding': '12px', 'color': 'red', 'margin': '0'})], error_style
    
    if not suggestions_data: 
        return [], default_style
    
    suggestions_style = {
        'width': '100%', 'maxHeight': '200px', 'overflowY': 'auto', 
        'backgroundColor': 'white', 'border': '1px solid #d1d5db',
        'borderRadius': '8px', 'marginTop': '4px',
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
                    'padding': '12px 16px',
                    'cursor': 'pointer', 
                    'borderBottom': '1px solid #f0f0f0' if i < len(suggestions_data) - 1 else 'none',
                    'color': '#333',
                    'fontSize': '0.95rem',
                    'lineHeight': '1.4',
                    'transition': 'background-color 0.2s ease'
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
    if not triggered_id_str: 
        raise dash.exceptions.PreventUpdate
        
    try:
        clicked_id_dict = json.loads(triggered_id_str.replace("'", "\"")) 
        clicked_index = clicked_id_dict['index']
    except Exception as e:
        print(f"Erreur parsing ID suggestion: {e}")
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
    
    print(f"\n=== RECHERCHE DE SEGMENTS ===")
    print(f"Token disponible: {'✅' if current_strava_access_token else '❌'}")
    
    # Déterminer les coordonnées
    search_lat, search_lon = None, None
    display_address = ""
    
    try:
        if selected_suggestion_data and selected_suggestion_data.get('lat') is not None:
            search_lat = selected_suggestion_data['lat']
            search_lon = selected_suggestion_data['lon']
            display_address = selected_suggestion_data['display_name']
        elif address_input_value:
            coords, error_msg, addr_disp = geocode_address_directly(address_input_value)
            if coords:
                search_lat, search_lon = coords
                display_address = addr_disp
            else: 
                return html.Div("❌ Adresse non trouvée"), f"Erreur: {error_msg}", None
        else: 
            return html.Div("❌ Veuillez entrer une adresse"), "Veuillez entrer une adresse", None
    except Exception as e:
        return html.Div("❌ Erreur de géocodage"), f"Erreur: {e}", None

    if not search_lat or not search_lon:
        return html.Div("❌ Coordonnées invalides"), "Coordonnées invalides", None

    # Vérifications des prérequis
    if not current_strava_access_token: 
        return html.Div([
            html.H3("❌ Token Strava manquant", style={'textAlign': 'center', 'color': 'orange'}),
            html.P("Connectez-vous d'abord avec Strava", style={'textAlign': 'center'})
        ]), "Token Strava manquant", None
        
    if not WEATHER_API_KEY:
        return html.Div("❌ Clé météo manquante"), "Configuration serveur manquante", None

    # Recherche des segments
    try:
        print(f"🔍 Recherche segments autour de: {display_address}")
        found_segments, error_msg = strava_analyzer.find_tailwind_segments_live( 
            search_lat, search_lon, SEARCH_RADIUS_KM, 
            current_strava_access_token, WEATHER_API_KEY, 
            MIN_TAILWIND_EFFECT_MPS_SEARCH
        )
        
        if error_msg:
            return html.Div(f"❌ {error_msg}"), f"Erreur: {error_msg}", None
            
        print(f"✅ {len(found_segments)} segments trouvés")
        
    except Exception as e:
        return html.Div("❌ Erreur de recherche"), f"Erreur: {e}", None

    # Création de la carte
    try:
        fig = go.Figure()

        if not found_segments:
            status_msg = html.Div([
                html.P(f"ℹ️ Aucun segment avec vent favorable trouvé autour de '{display_address}'", 
                       style={'color': '#666', 'fontWeight': 'bold'}),
                html.P("💡 Essayez une autre zone ou revenez plus tard quand le vent aura changé.", 
                       style={'color': '#666', 'fontStyle': 'italic'})
            ])
            
            fig.add_trace(go.Scattermapbox(
                lat=[search_lat], lon=[search_lon], mode='markers',
                marker=go.scattermapbox.Marker(size=15, color='blue', symbol='circle'),
                text=[f"📍 {display_address}"], hoverinfo='text', name='Recherche'
            ))
            center_lat, center_lon = search_lat, search_lon
            zoom_level = 12
        else:
            status_msg = html.Div([
                html.P(f"🎉 Excellent ! {len(found_segments)} segment(s) avec vent favorable trouvé(s) !", 
                       style={'margin': '0', 'fontWeight': 'bold', 'color': '#10B981', 'fontSize': '1.1rem'}),
                html.P("💡 Cliquez sur un segment coloré pour accéder à sa page Strava", 
                       style={'margin': '8px 0 0 0', 'fontSize': '0.9rem', 'fontStyle': 'italic', 'color': '#6B7280'})
            ])
            
            all_lats, all_lons = [], []
            colors = ['rgba(255, 0, 0, 0.9)', 'rgba(0, 255, 0, 0.9)', 'rgba(255, 165, 0, 0.9)', 
                     'rgba(128, 0, 128, 0.9)', 'rgba(255, 192, 203, 0.9)', 'rgba(0, 255, 255, 0.9)']
            
            for i, segment in enumerate(found_segments[:20]):  # Limiter à 20 segments pour les performances
                coords = segment.get("polyline_coords", [])
                if len(coords) >= 2:
                    lats = [coord[0] for coord in coords if coord[0] is not None]
                    lons = [coord[1] for coord in coords if coord[1] is not None]
                    
                    if len(lats) >= 2:
                        all_lats.extend(lats)
                        all_lons.extend(lons)
                        
                        color = colors[i % len(colors)]
                        
                        fig.add_trace(go.Scattermapbox(
                            lat=lats, lon=lons, mode='lines+markers',
                            line=dict(width=4, color=color),
                            marker=dict(size=6, color=color, symbol='circle'),
                            name=f"🚴 {segment['name'][:30]}{'...' if len(segment['name']) > 30 else ''}",
                            text=[f"<b>🏆 {segment['name']}</b><br>"
                                  f"📏 {segment.get('distance', 0):.0f}m<br>"
                                  f"📈 {segment.get('avg_grade', 0):.1f}%<br>"
                                  f"💨 +{segment.get('wind_effect_mps', 0):.2f} m/s<br>"
                                  f"🔗 Cliquez pour voir sur Strava !" for _ in lats],
                            hoverinfo='text',
                            hovertemplate='%{text}<extra></extra>',
                            customdata=[{
                                'segment_id': segment['id'], 
                                'strava_url': segment['strava_link'],
                                'segment_name': segment['name']
                            }] * len(lats)
                        ))

            if all_lats and all_lons:
                center_lat = sum(all_lats) / len(all_lats)
                center_lon = sum(all_lons) / len(all_lons)
                
                # Calcul automatique du zoom
                lat_range = max(all_lats) - min(all_lats)
                lon_range = max(all_lons) - min(all_lons)
                max_range = max(lat_range, lon_range) * 1.2
                
                if max_range < 0.01:
                    zoom_level = 14
                elif max_range < 0.02:
                    zoom_level = 13
                elif max_range < 0.05:
                    zoom_level = 12
                elif max_range < 0.1:
                    zoom_level = 11
                else:
                    zoom_level = 10
            else:
                center_lat, center_lon = search_lat, search_lon
                zoom_level = 12

        # Configuration de la carte
        fig.update_layout(
            mapbox_style="streets", 
            mapbox_accesstoken=MAPBOX_ACCESS_TOKEN,
            mapbox_zoom=zoom_level, 
            mapbox_center_lat=center_lat, 
            mapbox_center_lon=center_lon,
            margin={"r":0,"t":0,"l":0,"b":0}, 
            showlegend=False,
            height=600,
            uirevision=f'map_{search_lat}_{search_lon}'
        )
        
        map_component = dcc.Graph(
            id='segments-map',
            figure=fig,
            style={'height': '600px', 'width': '100%'},
            config={
                'displayModeBar': True, 
                'displaylogo': False,
                'modeBarButtonsToRemove': ['pan2d', 'select2d', 'lasso2d'],
                'scrollZoom': True,
                'doubleClick': 'reset+autosize'
            }
        )
        
        return map_component, status_msg, None
        
    except Exception as e:
        print(f"❌ Erreur carte: {e}")
        return html.Div("❌ Erreur d'affichage"), f"Erreur affichage: {e}", None

# === CALLBACK POUR LES CLICS SUR LA CARTE ===
@app.callback(
    Output('search-status-message', 'children', allow_duplicate=True),
    Input('segments-map', 'clickData'),
    prevent_initial_call=True
)
def handle_segment_click(click_data):
    if not click_data or 'points' not in click_data or not click_data['points']:
        return dash.no_update
    
    try:
        point_data = click_data['points'][0]
        if 'customdata' in point_data and isinstance(point_data['customdata'], dict):
            segment_name = point_data['customdata'].get('segment_name', 'ce segment')
            strava_url = point_data['customdata'].get('strava_url')
            
            if strava_url:
                return html.Div([
                    html.P(f"🚴 Segment: {segment_name}", 
                           style={'fontWeight': 'bold', 'color': '#10B981', 'margin': '8px 0'}),
                    html.A("🔗 VOIR SUR STRAVA", 
                           href=strava_url, target="_blank",
                           style={
                               'display': 'inline-block', 'padding': '12px 20px',
                               'backgroundColor': '#FC4C02', 'color': 'white',
                               'borderRadius': '8px', 'textDecoration': 'none',
                               'fontSize': '1rem', 'fontWeight': 'bold',
                               'boxShadow': '0 4px 12px rgba(252, 76, 2, 0.3)'
                           }),
                    html.P("💡 Cliquez sur d'autres segments colorés de la carte", 
                           style={'fontSize': '0.85rem', 'color': '#6B7280', 'margin': '8px 0 0 0', 'fontStyle': 'italic'})
                ], style={'textAlign': 'center', 'padding': '15px'})
        
        return dash.no_update
        
    except Exception as e:
        print(f"Erreur clic segment: {e}")
        return dash.no_update

# --- CSS pour les suggestions (à ajouter au style) ---
app.index_string = app.index_string.replace(
    '</head>', 
    '''
    <style>
    .suggestion-item-hover:hover {
        background-color: #f5f5f5 !important;
    }
    </style>
    </head>'''
)

# --- Exécution de l'Application ---
if __name__ == '__main__':
    # Vérifications des variables d'environnement critiques
    required_vars = [MAPBOX_ACCESS_TOKEN, STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET, WEATHER_API_KEY]
    missing_vars = [var for var in ['MAPBOX_ACCESS_TOKEN', 'STRAVA_CLIENT_ID', 'STRAVA_CLIENT_SECRET', 'OPENWEATHERMAP_API_KEY'] 
                   if not globals()[var]]
    
    if missing_vars:
        print(f"❌ VARIABLES MANQUANTES: {', '.join(missing_vars)}")
        print("➡️ Ajoutez-les dans l'onglet Environment de Render")
    
    if not OPENAI_API_KEY:
        print("⚠️ OPENAI_API_KEY manquant - l'analyse d'activités ne sera pas disponible")
    
    # Configuration pour développement ET production
    port = int(os.environ.get('PORT', 8050))
    debug_mode = os.environ.get('RENDER') is None
    
    print(f"\n🚀 LANCEMENT KOM HUNTERS")
    print(f"🌐 Mode: {'Développement' if debug_mode else 'Production'}")
    print(f"🔗 URL: {BASE_URL}")
    print(f"📊 Pages disponibles:")
    print(f"   - {BASE_URL}/ (Recherche segments)")
    print(f"   - {BASE_URL}/activities (Analyse activités)")
    print(f"🔧 Configuration Strava callback: {STRAVA_REDIRECT_URI}")
    
    app.run_server(debug=debug_mode, host='0.0.0.0', port=port)