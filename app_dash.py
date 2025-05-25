import dash
from dash import dcc, html, Input, Output, State, callback_context
import plotly.graph_objects as go
import os
import time 
import math 
import json 
import requests 
from datetime import datetime

# Configuration de base - ROBUSTE même si variables manquantes
print("🚀 DÉMARRAGE KOM HUNTERS")

# Chargement optionnel de dotenv (ne crash pas si absent)
try:
    from dotenv import load_dotenv
    load_dotenv()
    print("✅ .env chargé")
except ImportError:
    print("⚠️ dotenv non disponible, utilisation des variables d'environnement système")

# Pour le géocodage
try:
    from geopy.geocoders import Nominatim
    from geopy.exc import GeocoderTimedOut, GeocoderUnavailable
    GEOPY_AVAILABLE = True
    print("✅ Geopy disponible")
except ImportError:
    GEOPY_AVAILABLE = False
    print("❌ Geopy non disponible")

# Import strava_analyzer avec gestion d'erreur
STRAVA_ANALYZER_AVAILABLE = False
try:
    import sys
    current_directory = os.path.dirname(os.path.abspath(__file__))
    if current_directory not in sys.path:
        sys.path.insert(0, current_directory)
    
    import strava_analyzer
    STRAVA_ANALYZER_AVAILABLE = True
    print("✅ strava_analyzer importé")
except Exception as e:
    print(f"❌ strava_analyzer non disponible: {e}")

# Configuration des APIs avec valeurs par défaut
MAPBOX_ACCESS_TOKEN = os.getenv('MAPBOX_ACCESS_TOKEN', '')
STRAVA_CLIENT_ID = os.getenv('STRAVA_CLIENT_ID', '')
STRAVA_CLIENT_SECRET = os.getenv('STRAVA_CLIENT_SECRET', '') 
WEATHER_API_KEY = os.getenv('OPENWEATHERMAP_API_KEY', '')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')

# Configuration des URLs - ultra-robuste
if os.getenv('RENDER'):
    BASE_URL = f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME', 'kom-hunters.onrender.com')}"
    print(f"🌐 Mode PRODUCTION - {BASE_URL}")
elif os.getenv('RAILWAY_STATIC_URL'):
    BASE_URL = os.getenv('RAILWAY_STATIC_URL')
    print(f"🌐 Mode RAILWAY - {BASE_URL}")
else:
    BASE_URL = 'http://localhost:8050'
    print(f"🌐 Mode DÉVELOPPEMENT - {BASE_URL}")

STRAVA_REDIRECT_URI = f'{BASE_URL}/strava_callback'

# Variables globales pour les tokens (simple, en mémoire)
current_strava_access_token = None
token_info_message = "Connectez-vous avec Strava pour commencer"

# Configuration de l'app
ACTIVITIES_PER_LOAD = 10
CYCLING_ACTIVITY_TYPES = ['Ride', 'VirtualRide', 'EBikeRide', 'Gravel', 'MountainBikeRide']
DEFAULT_FC_MAX = 190
DEFAULT_FTP = 250
DEFAULT_WEIGHT = 70
SEARCH_RADIUS_KM = 10
MIN_TAILWIND_EFFECT_MPS = 0.7

print(f"📊 Configuration:")
print(f"  - Mapbox: {'✅' if MAPBOX_ACCESS_TOKEN else '❌'}")
print(f"  - Strava ID: {'✅' if STRAVA_CLIENT_ID else '❌'}")
print(f"  - Strava Secret: {'✅' if STRAVA_CLIENT_SECRET else '❌'}")
print(f"  - Weather: {'✅' if WEATHER_API_KEY else '❌'}")
print(f"  - OpenAI: {'✅' if OPENAI_API_KEY else '❌'}")

# Fonctions utilitaires ULTRA-ROBUSTES
def safe_geocode(address_str):
    """Géocodage sécurisé"""
    if not GEOPY_AVAILABLE or not address_str:
        return None, "Service de géocodage non disponible"
    
    try:
        geolocator = Nominatim(user_agent="kom_hunters_v6")
        location = geolocator.geocode(address_str, timeout=10)
        if location:
            return (location.latitude, location.longitude), None
        return None, "Adresse non trouvée"
    except Exception as e:
        return None, f"Erreur géocodage: {e}"

def safe_strava_request(url, headers, params=None):
    """Requête Strava sécurisée"""
    try:
        response = requests.get(url, headers=headers, params=params, timeout=15)
        response.raise_for_status()
        return response.json(), None
    except requests.exceptions.HTTPError as e:
        if hasattr(e, 'response') and e.response.status_code == 401:
            return None, "Token expiré, reconnectez-vous"
        return None, f"Erreur API: {e}"
    except Exception as e:
        return None, f"Erreur réseau: {e}"

def get_strava_activities(token, page=1):
    """Récupère les activités Strava"""
    if not token:
        return [], "Token manquant"
    
    headers = {'Authorization': f'Bearer {token}'}
    url = 'https://www.strava.com/api/v3/athlete/activities'
    params = {'page': page, 'per_page': ACTIVITIES_PER_LOAD}
    
    activities, error = safe_strava_request(url, headers, params)
    if error:
        return [], error
    
    # Filtrer les activités vélo
    cycling_activities = [a for a in activities if a.get('type') in CYCLING_ACTIVITY_TYPES]
    return cycling_activities, None

def format_activity(activity):
    """Formate une activité pour le dropdown"""
    name = activity.get('name', 'Sans nom')[:50]
    date = activity.get('start_date_local', '')[:10]
    distance = round(activity.get('distance', 0) / 1000, 1)
    activity_type = activity.get('type', 'Ride')
    
    icons = {'Ride': '🚴', 'VirtualRide': '🚴‍💻', 'EBikeRide': '🚴‍⚡', 'Gravel': '🚵', 'MountainBikeRide': '🚵‍♂️'}
    icon = icons.get(activity_type, '🚴')
    
    return f"{icon} {date} - {name} - {distance}km"

# Initialisation de l'app Dash
app = dash.Dash(__name__)
app.title = "KOM Hunters"
app.config.suppress_callback_exceptions = True

# Serveur pour le déploiement
server = app.server

# Styles CSS intégrés
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
        body { 
            font-family: 'Inter', sans-serif; 
            margin: 0; 
            background: #f8fafc; 
        }
        .suggestion-hover:hover { 
            background-color: #f3f4f6 !important; 
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

def create_header():
    """Crée l'en-tête de l'application"""
    global current_strava_access_token, token_info_message
    
    # Statut de connexion
    if current_strava_access_token:
        connect_button = html.Div("✅ Connecté à Strava", style={
            'color': '#10B981', 'fontWeight': 'bold', 'padding': '8px 16px',
            'backgroundColor': '#F0FDF4', 'borderRadius': '6px', 'border': '1px solid #10B981'
        })
    else:
        auth_url = (f"https://www.strava.com/oauth/authorize?"
                   f"client_id={STRAVA_CLIENT_ID}&redirect_uri={STRAVA_REDIRECT_URI}"
                   f"&response_type=code&scope=read,activity:read_all")
        
        connect_button = html.A("🔗 Se connecter avec Strava", href=auth_url, style={
            'display': 'inline-block', 'padding': '10px 20px', 'backgroundColor': '#FC4C02',
            'color': 'white', 'textDecoration': 'none', 'borderRadius': '6px', 'fontWeight': 'bold'
        })
    
    return html.Div([
        html.H1("🏆 KOM Hunters", style={
            'textAlign': 'center', 'color': 'white', 'margin': '0 0 20px 0', 'fontSize': '2rem'
        }),
        html.Div([
            html.A("🔍 Segments", href="/", style={
                'padding': '8px 16px', 'margin': '0 10px', 'backgroundColor': '#3B82F6',
                'color': 'white', 'textDecoration': 'none', 'borderRadius': '4px'
            }),
            html.A("📊 Activités", href="/activities", style={
                'padding': '8px 16px', 'margin': '0 10px', 'backgroundColor': '#10B981',
                'color': 'white', 'textDecoration': 'none', 'borderRadius': '4px'
            })
        ], style={'textAlign': 'center', 'marginBottom': '20px'}),
        html.Div(connect_button, style={'textAlign': 'center', 'marginBottom': '15px'}),
        html.Div(token_info_message, style={
            'textAlign': 'center', 'color': '#D1D5DB', 'fontSize': '0.9rem'
        })
    ], style={
        'backgroundColor': '#1F2937', 'padding': '20px', 'color': 'white'
    })

def create_segments_page():
    """Page de recherche de segments"""
    return html.Div([
        create_header(),
        html.Div([
            html.Div([
                html.H3("🎯 Recherche de segments avec vent favorable", style={
                    'color': '#1F2937', 'marginBottom': '20px'
                }),
                html.Div([
                    dcc.Input(
                        id='address-input',
                        type='text',
                        placeholder='Tapez une ville (ex: Lyon, France)...',
                        style={
                            'width': '100%', 'padding': '12px', 'fontSize': '1rem',
                            'border': '2px solid #D1D5DB', 'borderRadius': '6px',
                            'marginBottom': '15px'
                        }
                    ),
                    html.Div(id='address-suggestions'),
                    html.Button('🚀 Chercher les segments', id='search-button', n_clicks=0, style={
                        'width': '100%', 'padding': '12px', 'fontSize': '1rem',
                        'backgroundColor': '#3B82F6', 'color': 'white', 'border': 'none',
                        'borderRadius': '6px', 'cursor': 'pointer', 'fontWeight': 'bold'
                    })
                ], style={'marginBottom': '20px'}),
                html.Div(id='search-status', style={'minHeight': '20px'})
            ], style={
                'backgroundColor': 'white', 'padding': '20px', 'borderRadius': '8px',
                'boxShadow': '0 2px 4px rgba(0,0,0,0.1)', 'marginBottom': '20px'
            }),
            dcc.Loading(html.Div(id='map-container'))
        ], style={'padding': '20px', 'maxWidth': '1200px', 'margin': '0 auto'}),
        dcc.Store(id='selected-address')
    ])

def create_activities_page():
    """Page d'analyse d'activités"""
    return html.Div([
        create_header(),
        html.Div([
            html.Div([
                html.H3("📊 Analyse de vos activités vélo", style={
                    'color': '#1F2937', 'marginBottom': '20px'
                }),
                html.Div([
                    html.Button('📥 Charger mes activités', id='load-activities', n_clicks=0, style={
                        'padding': '10px 20px', 'backgroundColor': '#3B82F6', 'color': 'white',
                        'border': 'none', 'borderRadius': '6px', 'cursor': 'pointer',
                        'marginRight': '10px', 'fontWeight': 'bold'
                    }),
                    html.Div(id='load-status', style={'display': 'inline-block', 'color': '#6B7280'})
                ], style={'marginBottom': '15px'}),
                dcc.Dropdown(
                    id='activities-dropdown', placeholder='Sélectionnez une activité...',
                    disabled=True, style={'marginBottom': '15px'}
                ),
                html.Div([
                    html.Div([
                        html.Label('💓 FC Max:', style={'fontWeight': 'bold', 'marginBottom': '5px'}),
                        dcc.Input(id='fc-max', type='number', value=DEFAULT_FC_MAX, min=120, max=220,
                                 style={'width': '100%', 'padding': '8px', 'border': '1px solid #D1D5DB', 'borderRadius': '4px'})
                    ], style={'flex': '1', 'marginRight': '10px'}),
                    html.Div([
                        html.Label('⚡ FTP:', style={'fontWeight': 'bold', 'marginBottom': '5px'}),
                        dcc.Input(id='ftp', type='number', value=DEFAULT_FTP, min=100, max=500,
                                 style={'width': '100%', 'padding': '8px', 'border': '1px solid #D1D5DB', 'borderRadius': '4px'})
                    ], style={'flex': '1', 'marginRight': '10px'}),
                    html.Div([
                        html.Label('⚖️ Poids:', style={'fontWeight': 'bold', 'marginBottom': '5px'}),
                        dcc.Input(id='weight', type='number', value=DEFAULT_WEIGHT, min=40, max=150,
                                 style={'width': '100%', 'padding': '8px', 'border': '1px solid #D1D5DB', 'borderRadius': '4px'})
                    ], style={'flex': '1'})
                ], style={'display': 'flex', 'marginBottom': '15px'}),
                html.Button('🔬 Analyser', id='analyze-button', n_clicks=0, disabled=True, style={
                    'width': '100%', 'padding': '12px', 'backgroundColor': '#10B981', 'color': 'white',
                    'border': 'none', 'borderRadius': '6px', 'cursor': 'pointer', 'fontWeight': 'bold'
                })
            ], style={
                'backgroundColor': 'white', 'padding': '20px', 'borderRadius': '8px',
                'boxShadow': '0 2px 4px rgba(0,0,0,0.1)', 'marginBottom': '20px'
            }),
            dcc.Loading(html.Div(id='analysis-results', style={
                'backgroundColor': 'white', 'padding': '20px', 'borderRadius': '8px',
                'boxShadow': '0 2px 4px rgba(0,0,0,0.1)', 'minHeight': '200px'
            }))
        ], style={'padding': '20px', 'maxWidth': '1200px', 'margin': '0 auto'}),
        dcc.Store(id='activities-data', data=[])
    ])

# Layout principal
app.layout = html.Div([
    dcc.Location(id='url', refresh=False), 
    html.Div(id='page-content')
])

# Callback de navigation principal
@app.callback(
    Output('page-content', 'children'),
    [Input('url', 'pathname'), Input('url', 'search')]
)
def display_page(pathname, search):
    global current_strava_access_token, token_info_message
    
    print(f"📍 Navigation: {pathname} {search or ''}")
    
    # Traitement du callback OAuth Strava
    if pathname == '/strava_callback' and search:
        try:
            # Parser les paramètres
            params = {}
            query = search[1:] if search.startswith('?') else search
            for pair in query.split('&'):
                if '=' in pair:
                    key, value = pair.split('=', 1)
                    params[key] = value
            
            code = params.get('code')
            error = params.get('error')
            
            if error:
                token_info_message = f"❌ Erreur Strava: {error}"
            elif code and STRAVA_CLIENT_ID and STRAVA_CLIENT_SECRET:
                # Échanger le code contre un token
                try:
                    response = requests.post('https://www.strava.com/oauth/token', data={
                        'client_id': STRAVA_CLIENT_ID,
                        'client_secret': STRAVA_CLIENT_SECRET,
                        'code': code,
                        'grant_type': 'authorization_code'
                    }, timeout=15)
                    
                    if response.status_code == 200:
                        token_data = response.json()
                        current_strava_access_token = token_data.get('access_token')
                        if current_strava_access_token:
                            token_info_message = "✅ Connexion Strava réussie !"
                            print("✅ Token Strava obtenu")
                        else:
                            token_info_message = "❌ Token non reçu"
                    else:
                        token_info_message = f"❌ Erreur API Strava: {response.status_code}"
                        
                except Exception as e:
                    token_info_message = f"❌ Erreur connexion: {e}"
            else:
                token_info_message = "❌ Configuration Strava manquante"
                
        except Exception as e:
            token_info_message = f"❌ Erreur OAuth: {e}"
            print(f"❌ Erreur OAuth: {e}")
    
    # Navigation vers les pages
    if pathname == '/activities':
        return create_activities_page()
    else:
        return create_segments_page()

# Callback pour charger les activités
@app.callback(
    [Output('activities-dropdown', 'options'),
     Output('activities-dropdown', 'disabled'),
     Output('load-status', 'children'),
     Output('activities-data', 'data')],
    Input('load-activities', 'n_clicks'),
    prevent_initial_call=True
)
def load_activities(n_clicks):
    global current_strava_access_token
    
    if not current_strava_access_token:
        return [], True, "❌ Connectez-vous d'abord", []
    
    activities, error = get_strava_activities(current_strava_access_token)
    
    if error:
        return [], True, f"❌ {error}", []
    
    if not activities:
        return [], True, "❌ Aucune activité vélo trouvée", []
    
    options = [{'label': format_activity(act), 'value': act['id']} for act in activities]
    return options, False, f"✅ {len(activities)} activités chargées", activities

# Callback pour activer le bouton d'analyse
@app.callback(
    Output('analyze-button', 'disabled'),
    Input('activities-dropdown', 'value')
)
def enable_analyze(selected):
    return selected is None

# Callback pour l'analyse d'activité
@app.callback(
    Output('analysis-results', 'children'),
    [Input('analyze-button', 'n_clicks')],
    [State('activities-dropdown', 'value'),
     State('activities-data', 'data'),
     State('fc-max', 'value'),
     State('ftp', 'value'),
     State('weight', 'value')],
    prevent_initial_call=True
)
def analyze_activity(n_clicks, activity_id, activities_data, fc_max, ftp, weight):
    global current_strava_access_token
    
    if not n_clicks or not activity_id:
        return "Sélectionnez une activité"
    
    if not current_strava_access_token:
        return html.Div("❌ Token Strava manquant", style={'color': 'red'})
    
    if not STRAVA_ANALYZER_AVAILABLE:
        return html.Div("❌ Module d'analyse non disponible", style={'color': 'red'})
    
    if not OPENAI_API_KEY:
        return html.Div("❌ Configuration OpenAI manquante", style={'color': 'red'})
    
    # Trouver l'activité
    activity = None
    for act in activities_data:
        if act['id'] == activity_id:
            activity = act
            break
    
    if not activity:
        return html.Div("❌ Activité non trouvée", style={'color': 'red'})
    
    try:
        print(f"🔬 Analyse activité: {activity.get('name', 'Sans nom')}")
        
        # Appel au module d'analyse
        result = strava_analyzer.generate_activity_report_with_overall_summary(
            activity_id=activity_id,
            access_token_strava=current_strava_access_token,
            openai_api_key=OPENAI_API_KEY,
            user_fc_max=fc_max,
            user_ftp=ftp,
            user_weight_kg=weight,
            weather_api_key=WEATHER_API_KEY,
            notable_rank_threshold=10,
            num_best_segments_to_analyze=2
        )
        
        content = []
        
        # Titre
        content.append(html.H2(result['activity_name'], style={
            'color': '#1F2937', 'textAlign': 'center', 'marginBottom': '20px'
        }))
        
        # Résumé global
        if result.get('overall_summary'):
            content.append(html.Div([
                html.H3("📋 Résumé", style={'color': '#3B82F6', 'marginBottom': '10px'}),
                html.Div(result['overall_summary'], style={
                    'backgroundColor': '#F8FAFC', 'padding': '15px', 'borderRadius': '6px',
                    'borderLeft': '4px solid #3B82F6', 'whiteSpace': 'pre-wrap', 'lineHeight': '1.6'
                })
            ], style={'marginBottom': '25px'}))
        
        # Analyses de segments
        if result.get('segment_reports'):
            content.append(html.H3("🎯 Analyses détaillées", style={
                'color': '#10B981', 'marginBottom': '15px'
            }))
            
            for report in result['segment_reports']:
                content.append(html.Div([
                    html.H4(report['segment_name'], style={'color': '#10B981', 'marginBottom': '8px'}),
                    html.Div(report['report'], style={
                        'backgroundColor': '#F0FDF4', 'padding': '15px', 'borderRadius': '6px',
                        'borderLeft': '4px solid #10B981', 'whiteSpace': 'pre-wrap', 'lineHeight': '1.6'
                    })
                ], style={'marginBottom': '20px'}))
        else:
            content.append(html.Div([
                html.P("ℹ️ Pas de segments remarquables dans cette activité", style={
                    'textAlign': 'center', 'color': '#6B7280', 'fontStyle': 'italic'
                })
            ]))
        
        return html.Div(content)
        
    except Exception as e:
        print(f"❌ Erreur analyse: {e}")
        return html.Div([
            html.H3("❌ Erreur d'analyse", style={'color': 'red'}),
            html.P(f"Détails: {str(e)}", style={'color': '#6B7280'})
        ])

# Callback pour la recherche de segments (simplifié)
@app.callback(
    [Output('map-container', 'children'),
     Output('search-status', 'children')],
    Input('search-button', 'n_clicks'),
    State('address-input', 'value'),
    prevent_initial_call=True
)
def search_segments(n_clicks, address):
    global current_strava_access_token
    
    if not address:
        return html.Div(), "❌ Entrez une adresse"
    
    if not current_strava_access_token:
        return html.Div(), "❌ Connectez-vous d'abord à Strava"
    
    if not WEATHER_API_KEY:
        return html.Div(), "❌ Configuration météo manquante"
    
    if not MAPBOX_ACCESS_TOKEN:
        return html.Div(), "❌ Configuration carte manquante"
    
    # Géocodage
    coords, error = safe_geocode(address)
    if error:
        return html.Div(), f"❌ {error}"
    
    lat, lon = coords
    
    try:
        if not STRAVA_ANALYZER_AVAILABLE:
            return html.Div("❌ Module d'analyse non disponible"), "❌ Erreur de configuration"
        
        # Recherche des segments
        segments, error = strava_analyzer.find_tailwind_segments_live(
            lat, lon, SEARCH_RADIUS_KM, current_strava_access_token, 
            WEATHER_API_KEY, MIN_TAILWIND_EFFECT_MPS
        )
        
        if error:
            return html.Div(), f"❌ {error}"
        
        if not segments:
            return html.Div([
                html.P(f"ℹ️ Aucun segment avec vent favorable autour de '{address}'", style={
                    'textAlign': 'center', 'color': '#6B7280', 'padding': '40px'
                })
            ]), "Essayez une autre zone"
        
        # Création de la carte
        fig = go.Figure()
        
        colors = ['red', 'blue', 'green', 'orange', 'purple', 'pink']
        
        for i, segment in enumerate(segments[:10]):  # Limiter à 10 pour les performances
            if segment.get('polyline_coords'):
                coords = segment['polyline_coords']
                lats = [c[0] for c in coords if c[0]]
                lons = [c[1] for c in coords if c[1]]
                
                if len(lats) >= 2:
                    fig.add_trace(go.Scattermapbox(
                        lat=lats, lon=lons, mode='lines+markers',
                        line=dict(width=4, color=colors[i % len(colors)]),
                        marker=dict(size=6, color=colors[i % len(colors)]),
                        name=segment['name'][:30],
                        text=f"<b>{segment['name']}</b><br>Distance: {segment.get('distance', 0):.0f}m<br>Pente: {segment.get('avg_grade', 0):.1f}%"
                    ))
        
        # Centre de la carte
        all_lats = [c[0] for s in segments for c in s.get('polyline_coords', []) if c[0]]
        all_lons = [c[1] for s in segments for c in s.get('polyline_coords', []) if c[1]]
        
        if all_lats and all_lons:
            center_lat = sum(all_lats) / len(all_lats)
            center_lon = sum(all_lons) / len(all_lons)
        else:
            center_lat, center_lon = lat, lon
        
        fig.update_layout(
            mapbox_style="streets",
            mapbox_accesstoken=MAPBOX_ACCESS_TOKEN,
            mapbox_zoom=12,
            mapbox_center_lat=center_lat,
            mapbox_center_lon=center_lon,
            margin={"r":0,"t":0,"l":0,"b":0},
            height=500
        )
        
        map_component = dcc.Graph(figure=fig, style={'height': '500px'})
        
        return map_component, f"✅ {len(segments)} segments trouvés !"
        
    except Exception as e:
        print(f"❌ Erreur recherche: {e}")
        return html.Div(), f"❌ Erreur: {e}"

print("✅ Application initialisée avec succès")

# Exécution
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8050))
    debug = os.environ.get('RENDER') is None
    
    print(f"🚀 Démarrage sur le port {port}")
    print(f"🔧 Mode debug: {debug}")
    print(f"🌐 URL: {BASE_URL}")
    
    try:
        app.run_server(debug=debug, host='0.0.0.0', port=port)
    except Exception as e:
        print(f"❌ ERREUR CRITIQUE au démarrage: {e}")
        raise