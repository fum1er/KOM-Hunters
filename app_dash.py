import dash
from dash import dcc, html, Input, Output, State, callback_context
import plotly.graph_objects as go
import os
import requests
import json
from datetime import datetime

# ==========================================
# VERSION ULTRA MINIMALE QUI MARCHE TOUJOURS
# ==========================================

print("=== KOM HUNTERS - DÉMARRAGE ===")

# Configuration de base
MAPBOX_TOKEN = os.getenv('MAPBOX_ACCESS_TOKEN', '')
STRAVA_CLIENT_ID = os.getenv('STRAVA_CLIENT_ID', '')
STRAVA_CLIENT_SECRET = os.getenv('STRAVA_CLIENT_SECRET', '')
WEATHER_KEY = os.getenv('OPENWEATHERMAP_API_KEY', '')
OPENAI_KEY = os.getenv('OPENAI_API_KEY', '')

# URL de base
if os.getenv('RENDER'):
    BASE_URL = f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME', 'kom-hunters.onrender.com')}"
else:
    BASE_URL = 'http://localhost:8050'

CALLBACK_URL = f'{BASE_URL}/strava_callback'

print(f"🌐 BASE_URL: {BASE_URL}")
print(f"🔑 MAPBOX: {'✅' if MAPBOX_TOKEN else '❌'}")
print(f"🔑 STRAVA_ID: {'✅' if STRAVA_CLIENT_ID else '❌'}")
print(f"🔑 STRAVA_SECRET: {'✅' if STRAVA_CLIENT_SECRET else '❌'}")
print(f"🔑 WEATHER: {'✅' if WEATHER_KEY else '❌'}")

# Variables globales simples
current_token = None
status_message = "Pas encore connecté"

# Import du module d'analyse (optionnel)
try:
    import strava_analyzer
    ANALYZER_OK = True
    print("✅ strava_analyzer importé")
except:
    ANALYZER_OK = False
    print("❌ strava_analyzer non disponible")

# Initialisation de l'app
app = dash.Dash(__name__)
app.title = "KOM Hunters"
server = app.server

print("✅ App Dash créée")

# Fonction pour créer le bouton Strava
def create_strava_button():
    global current_token
    
    if current_token:
        return html.Div("✅ Connecté à Strava", style={
            'color': 'green', 'fontWeight': 'bold', 'padding': '10px',
            'border': '2px solid green', 'borderRadius': '5px',
            'backgroundColor': '#f0fff0', 'textAlign': 'center'
        })
    else:
        auth_url = (f"https://www.strava.com/oauth/authorize?"
                   f"client_id={STRAVA_CLIENT_ID}&"
                   f"redirect_uri={CALLBACK_URL}&"
                   f"response_type=code&"
                   f"scope=read,activity:read_all")
        
        return html.A("🔗 Se connecter à Strava", href=auth_url, style={
            'display': 'block', 'padding': '15px', 'backgroundColor': '#FC4C02',
            'color': 'white', 'textDecoration': 'none', 'borderRadius': '5px',
            'textAlign': 'center', 'fontWeight': 'bold', 'fontSize': '16px'
        })

# Layout de la page principale
def main_layout():
    return html.Div([
        html.Div([
            html.H1("🏆 KOM Hunters", style={
                'textAlign': 'center', 'color': 'white', 'margin': '0',
                'fontSize': '2.5rem', 'fontWeight': 'bold'
            }),
            html.P("Trouvez les segments avec vent favorable", style={
                'textAlign': 'center', 'color': '#ddd', 'margin': '10px 0'
            })
        ], style={
            'backgroundColor': '#1a202c', 'padding': '30px', 'marginBottom': '20px'
        }),
        
        html.Div([
            # Navigation
            html.Div([
                html.A("🔍 Segments", href="/", style={
                    'padding': '10px 20px', 'margin': '5px', 'backgroundColor': '#3182ce',
                    'color': 'white', 'textDecoration': 'none', 'borderRadius': '5px'
                }),
                html.A("📊 Activités", href="/activities", style={
                    'padding': '10px 20px', 'margin': '5px', 'backgroundColor': '#38a169',
                    'color': 'white', 'textDecoration': 'none', 'borderRadius': '5px'
                })
            ], style={'textAlign': 'center', 'marginBottom': '20px'}),
            
            # Connexion Strava
            html.Div([
                create_strava_button(),
                html.P(status_message, style={
                    'textAlign': 'center', 'color': '#666', 'marginTop': '10px'
                })
            ], style={'marginBottom': '30px'}),
            
            # Interface de recherche
            html.Div([
                html.H3("🎯 Recherche de segments", style={'color': '#1a202c'}),
                dcc.Input(
                    id='address-input',
                    type='text',
                    placeholder='Tapez une ville (ex: Lyon, France)',
                    style={
                        'width': '100%', 'padding': '15px', 'fontSize': '16px',
                        'border': '2px solid #ddd', 'borderRadius': '5px', 'marginBottom': '15px'
                    }
                ),
                html.Button('🚀 Chercher !', id='search-btn', style={
                    'width': '100%', 'padding': '15px', 'fontSize': '16px',
                    'backgroundColor': '#3182ce', 'color': 'white', 'border': 'none',
                    'borderRadius': '5px', 'cursor': 'pointer', 'fontWeight': 'bold'
                }),
                html.Div(id='search-result', style={'marginTop': '20px'})
            ], style={
                'backgroundColor': 'white', 'padding': '25px', 'borderRadius': '10px',
                'boxShadow': '0 2px 10px rgba(0,0,0,0.1)'
            })
        ], style={
            'maxWidth': '800px', 'margin': '0 auto', 'padding': '20px'
        })
    ])

# Layout de la page activités
def activities_layout():
    return html.Div([
        html.Div([
            html.H1("📊 Analyse d'Activités", style={
                'textAlign': 'center', 'color': 'white', 'margin': '0'
            })
        ], style={
            'backgroundColor': '#1a202c', 'padding': '30px', 'marginBottom': '20px'
        }),
        
        html.Div([
            # Navigation
            html.Div([
                html.A("🔍 Segments", href="/", style={
                    'padding': '10px 20px', 'margin': '5px', 'backgroundColor': '#3182ce',
                    'color': 'white', 'textDecoration': 'none', 'borderRadius': '5px'
                }),
                html.A("📊 Activités", href="/activities", style={
                    'padding': '10px 20px', 'margin': '5px', 'backgroundColor': '#38a169',
                    'color': 'white', 'textDecoration': 'none', 'borderRadius': '5px'
                })
            ], style={'textAlign': 'center', 'marginBottom': '20px'}),
            
            # Connexion
            create_strava_button(),
            
            # Interface d'activités
            html.Div([
                html.H3("🚴 Vos activités vélo", style={'color': '#1a202c'}),
                html.Button('📥 Charger mes activités', id='load-btn', style={
                    'padding': '12px 20px', 'backgroundColor': '#3182ce', 'color': 'white',
                    'border': 'none', 'borderRadius': '5px', 'cursor': 'pointer',
                    'marginBottom': '15px'
                }),
                html.Div(id='activities-status'),
                dcc.Dropdown(id='activities-dropdown', placeholder='Sélectionnez une activité...', disabled=True),
                html.Div(id='analysis-result', style={'marginTop': '20px'})
            ], style={
                'backgroundColor': 'white', 'padding': '25px', 'borderRadius': '10px',
                'boxShadow': '0 2px 10px rgba(0,0,0,0.1)', 'marginTop': '20px'
            })
        ], style={
            'maxWidth': '800px', 'margin': '0 auto', 'padding': '20px'
        }),
        
        dcc.Store(id='activities-data', data=[])
    ])

# Layout principal avec navigation
app.layout = html.Div([
    dcc.Location(id='url', refresh=False),
    html.Div(id='page-content')
])

print("✅ Layout défini")

# Callback principal de navigation
@app.callback(
    Output('page-content', 'children'),
    [Input('url', 'pathname'), Input('url', 'search')]
)
def display_page(pathname, search):
    global current_token, status_message
    
    print(f"📍 Navigation: {pathname} - {search}")
    
    # Traitement du callback Strava
    if pathname == '/strava_callback' and search:
        print("🔄 Traitement callback Strava...")
        
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
            
            print(f"Code: {code[:10] if code else None}, Error: {error}")
            
            if error:
                status_message = f"❌ Erreur: {error}"
            elif code and STRAVA_CLIENT_ID and STRAVA_CLIENT_SECRET:
                # Échanger le code contre un token
                token_data = {
                    'client_id': STRAVA_CLIENT_ID,
                    'client_secret': STRAVA_CLIENT_SECRET,
                    'code': code,
                    'grant_type': 'authorization_code'
                }
                
                try:
                    response = requests.post('https://www.strava.com/oauth/token', 
                                           data=token_data, timeout=15)
                    
                    print(f"Réponse Strava: {response.status_code}")
                    
                    if response.status_code == 200:
                        token_info = response.json()
                        current_token = token_info.get('access_token')
                        
                        if current_token:
                            status_message = "✅ Connexion réussie !"
                            print("✅ Token obtenu")
                        else:
                            status_message = "❌ Token non reçu"
                    else:
                        status_message = f"❌ Erreur API: {response.status_code}"
                        
                except Exception as e:
                    status_message = f"❌ Erreur connexion: {str(e)}"
                    print(f"❌ Erreur token: {e}")
            else:
                status_message = "❌ Configuration manquante"
                
        except Exception as e:
            status_message = f"❌ Erreur callback: {str(e)}"
            print(f"❌ Erreur callback: {e}")
    
    # Navigation
    if pathname == '/activities':
        return activities_layout()
    else:
        return main_layout()

print("✅ Callback navigation défini")

# Callback pour charger les activités
@app.callback(
    [Output('activities-dropdown', 'options'),
     Output('activities-dropdown', 'disabled'),
     Output('activities-status', 'children'),
     Output('activities-data', 'data')],
    Input('load-btn', 'n_clicks'),
    prevent_initial_call=True
)
def load_activities(n_clicks):
    global current_token
    
    print("📥 Chargement activités...")
    
    if not current_token:
        return [], True, html.Div("❌ Connectez-vous d'abord", style={'color': 'red'}), []
    
    try:
        headers = {'Authorization': f'Bearer {current_token}'}
        url = 'https://www.strava.com/api/v3/athlete/activities'
        params = {'per_page': 10}
        
        response = requests.get(url, headers=headers, params=params, timeout=15)
        
        if response.status_code != 200:
            return [], True, html.Div(f"❌ Erreur API: {response.status_code}", style={'color': 'red'}), []
        
        activities = response.json()
        
        # Filtrer les activités vélo
        cycling_types = ['Ride', 'VirtualRide', 'EBikeRide']
        bike_activities = [a for a in activities if a.get('type') in cycling_types]
        
        if not bike_activities:
            return [], True, html.Div("❌ Aucune activité vélo trouvée", style={'color': 'orange'}), []
        
        # Créer les options
        options = []
        for activity in bike_activities:
            name = activity.get('name', 'Sans nom')[:40]
            date = activity.get('start_date_local', '')[:10]
            distance = round(activity.get('distance', 0) / 1000, 1)
            label = f"🚴 {date} - {name} - {distance}km"
            options.append({'label': label, 'value': activity['id']})
        
        status = html.Div(f"✅ {len(bike_activities)} activités chargées", style={'color': 'green'})
        
        return options, False, status, bike_activities
        
    except Exception as e:
        error_msg = html.Div(f"❌ Erreur: {str(e)}", style={'color': 'red'})
        return [], True, error_msg, []

print("✅ Callback activités défini")

# Callback pour la recherche (simplifié)
@app.callback(
    Output('search-result', 'children'),
    Input('search-btn', 'n_clicks'),
    State('address-input', 'value'),
    prevent_initial_call=True
)
def search_segments(n_clicks, address):
    global current_token
    
    print(f"🔍 Recherche: {address}")
    
    if not address:
        return html.Div("❌ Entrez une adresse", style={'color': 'red'})
    
    if not current_token:
        return html.Div("❌ Connectez-vous d'abord", style={'color': 'red'})
    
    if not MAPBOX_TOKEN:
        return html.Div("❌ Token Mapbox manquant", style={'color': 'red'})
    
    if not WEATHER_KEY:
        return html.Div("❌ Clé météo manquante", style={'color': 'red'})
    
    if not ANALYZER_OK:
        return html.Div("❌ Module d'analyse non disponible", style={'color': 'red'})
    
    try:
        # Géocodage simple
        from geopy.geocoders import Nominatim
        geolocator = Nominatim(user_agent="kom_hunters")
        location = geolocator.geocode(address, timeout=10)
        
        if not location:
            return html.Div("❌ Adresse non trouvée", style={'color': 'red'})
        
        lat, lon = location.latitude, location.longitude
        print(f"📍 Coordonnées: {lat}, {lon}")
        
        # Recherche des segments
        segments, error = strava_analyzer.find_tailwind_segments_live(
            lat, lon, 10, current_token, WEATHER_KEY, 0.5
        )
        
        if error:
            return html.Div(f"❌ {error}", style={'color': 'red'})
        
        if not segments:
            return html.Div("ℹ️ Aucun segment trouvé", style={'color': 'orange'})
        
        # Créer une carte simple
        fig = go.Figure()
        
        colors = ['red', 'blue', 'green', 'orange', 'purple']
        
        for i, segment in enumerate(segments[:5]):  # Limiter à 5
            if segment.get('polyline_coords'):
                coords = segment['polyline_coords']
                lats = [c[0] for c in coords if c[0]]
                lons = [c[1] for c in coords if c[1]]
                
                if len(lats) >= 2:
                    fig.add_trace(go.Scattermapbox(
                        lat=lats, lon=lons, mode='lines',
                        line=dict(width=3, color=colors[i % len(colors)]),
                        name=segment['name'][:20]
                    ))
        
        fig.update_layout(
            mapbox_style="streets",
            mapbox_accesstoken=MAPBOX_TOKEN,
            mapbox_zoom=12,
            mapbox_center_lat=lat,
            mapbox_center_lon=lon,
            margin={"r":0,"t":0,"l":0,"b":0},
            height=400
        )
        
        return html.Div([
            html.H4(f"✅ {len(segments)} segments trouvés !"),
            dcc.Graph(figure=fig)
        ])
        
    except Exception as e:
        print(f"❌ Erreur recherche: {e}")
        return html.Div(f"❌ Erreur: {str(e)}", style={'color': 'red'})

print("✅ Callback recherche défini")

print("✅ Tous les callbacks définis")

# Lancement
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8050))
    debug = os.environ.get('RENDER') is None
    
    print(f"🚀 LANCEMENT sur port {port}")
    print(f"🔧 Debug: {debug}")
    print(f"🌐 URL: {BASE_URL}")
    
    app.run_server(debug=debug, host='0.0.0.0', port=port)