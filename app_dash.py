import dash
from dash import dcc, html, Input, Output, State, callback_context
import plotly.graph_objects as go
import os
import requests
import json
from datetime import datetime

print("🚀 KOM HUNTERS - DÉMARRAGE CORRECT")

# Configuration
MAPBOX_TOKEN = os.getenv('MAPBOX_ACCESS_TOKEN', '')
STRAVA_CLIENT_ID = os.getenv('STRAVA_CLIENT_ID', '')
STRAVA_CLIENT_SECRET = os.getenv('STRAVA_CLIENT_SECRET', '')
WEATHER_KEY = os.getenv('OPENWEATHERMAP_API_KEY', '')
OPENAI_KEY = os.getenv('OPENAI_API_KEY', '')

# URL automatique
if os.getenv('RENDER'):
    BASE_URL = f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME', 'kom-hunters.onrender.com')}"
else:
    BASE_URL = 'http://localhost:8050'

STRAVA_CALLBACK = f'{BASE_URL}/strava_callback'

print(f"🌐 URL de base: {BASE_URL}")
print(f"🔄 Callback Strava: {STRAVA_CALLBACK}")

# Variables globales
current_token = None
user_message = "Connectez-vous avec Strava pour commencer"

# Import optionnel de strava_analyzer
ANALYZER_AVAILABLE = False
try:
    import sys
    import strava_analyzer
    ANALYZER_AVAILABLE = True
    print("✅ strava_analyzer disponible")
except:
    print("❌ strava_analyzer non disponible")

# Import optionnel de geopy
GEOPY_AVAILABLE = False
try:
    from geopy.geocoders import Nominatim
    GEOPY_AVAILABLE = True
    print("✅ geopy disponible")
except:
    print("❌ geopy non disponible")

# Initialisation Dash
app = dash.Dash(__name__)
app.title = "KOM Hunters"
server = app.server  # IMPORTANT pour Gunicorn

print("✅ App Dash initialisée")

# CSS intégré
app.index_string = '''
<!DOCTYPE html>
<html>
<head>
    {%metas%}
    <title>{%title%}</title>
    {%favicon%}
    {%css%}
    <style>
        body { 
            font-family: 'Arial', sans-serif; 
            margin: 0; 
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
        }
        .container { 
            max-width: 1200px; 
            margin: 0 auto; 
            padding: 20px; 
        }
        .header {
            background: rgba(255,255,255,0.1);
            backdrop-filter: blur(10px);
            border-radius: 15px;
            padding: 30px;
            text-align: center;
            margin-bottom: 30px;
            border: 1px solid rgba(255,255,255,0.2);
        }
        .card {
            background: rgba(255,255,255,0.95);
            border-radius: 15px;
            padding: 25px;
            margin-bottom: 25px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.1);
            backdrop-filter: blur(10px);
        }
        .btn {
            padding: 12px 25px;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-weight: bold;
            text-decoration: none;
            display: inline-block;
            transition: all 0.3s ease;
            text-align: center;
        }
        .btn-primary { background: #667eea; color: white; }
        .btn-success { background: #48bb78; color: white; }
        .btn-strava { background: #FC4C02; color: white; }
        .btn:hover { transform: translateY(-2px); box-shadow: 0 4px 15px rgba(0,0,0,0.2); }
        .status-connected { color: #48bb78; font-weight: bold; }
        .status-error { color: #e53e3e; font-weight: bold; }
        input, select { 
            width: 100%; 
            padding: 12px; 
            border: 2px solid #e2e8f0; 
            border-radius: 8px; 
            font-size: 16px; 
            margin-bottom: 15px;
            box-sizing: border-box;
        }
        input:focus, select:focus { 
            outline: none; 
            border-color: #667eea; 
            box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1); 
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

# Fonction pour créer le statut Strava
def get_strava_status():
    global current_token, user_message
    
    if current_token:
        return html.Div([
            html.Span("✅ Connecté à Strava", className="status-connected"),
            html.P(user_message, style={'margin': '10px 0', 'color': '#666'})
        ])
    else:
        auth_url = (f"https://www.strava.com/oauth/authorize?"
                   f"client_id={STRAVA_CLIENT_ID}&"
                   f"redirect_uri={STRAVA_CALLBACK}&"
                   f"response_type=code&"
                   f"scope=read,activity:read_all")
        
        return html.Div([
            html.A("🔗 Se connecter avec Strava", 
                   href=auth_url if STRAVA_CLIENT_ID else "#",
                   className="btn btn-strava",
                   style={'fontSize': '18px', 'padding': '15px 30px'}),
            html.P(user_message, style={'margin': '15px 0', 'color': '#666'})
        ])

# Layout principal avec le vrai design
def create_main_layout():
    return html.Div(className="container", children=[
        # Header magnifique
        html.Div(className="header", children=[
            html.H1("🏆 KOM Hunters", style={
                'color': 'white', 'fontSize': '3rem', 'margin': '0 0 10px 0',
                'textShadow': '2px 2px 4px rgba(0,0,0,0.3)'
            }),
            html.P("Trouvez les segments avec vent favorable et analysez vos performances", 
                   style={'color': 'rgba(255,255,255,0.9)', 'fontSize': '1.2rem', 'margin': '0'})
        ]),
        
        # Navigation
        html.Div(className="card", children=[
            html.Div([
                html.A("🔍 Recherche de Segments", href="/", className="btn btn-primary", 
                       style={'margin': '5px 10px'}),
                html.A("📊 Analyse d'Activités", href="/activities", className="btn btn-success",
                       style={'margin': '5px 10px'})
            ], style={'textAlign': 'center'})
        ]),
        
        # Statut Strava
        html.Div(className="card", children=[
            html.H3("🔗 Connexion Strava", style={'color': '#2d3748', 'marginBottom': '20px'}),
            get_strava_status()
        ]),
        
        # Interface de recherche
        html.Div(className="card", children=[
            html.H3("🎯 Recherche de segments avec vent favorable", style={'color': '#2d3748'}),
            html.Div([
                dcc.Input(
                    id='search-input',
                    type='text',
                    placeholder='Tapez une ville ou adresse (ex: Lyon, France, Annecy, etc.)',
                    style={'marginBottom': '15px'}
                ),
                html.Button('🚀 Chercher les segments !', id='search-btn', n_clicks=0,
                           className="btn btn-primary", style={'width': '100%', 'fontSize': '16px'}),
                html.Div(id='search-status', style={'marginTop': '20px'}),
                html.Div(id='map-results', style={'marginTop': '20px'})
            ])
        ])
    ])

# Layout page activités  
def create_activities_layout():
    return html.Div(className="container", children=[
        # Header
        html.Div(className="header", children=[
            html.H1("📊 Analyse d'Activités", style={
                'color': 'white', 'fontSize': '2.5rem', 'margin': '0',
                'textShadow': '2px 2px 4px rgba(0,0,0,0.3)'
            })
        ]),
        
        # Navigation
        html.Div(className="card", children=[
            html.Div([
                html.A("🔍 Recherche de Segments", href="/", className="btn btn-primary", 
                       style={'margin': '5px 10px'}),
                html.A("📊 Analyse d'Activités", href="/activities", className="btn btn-success",
                       style={'margin': '5px 10px'})
            ], style={'textAlign': 'center'})
        ]),
        
        # Statut Strava
        html.Div(className="card", children=[
            html.H3("🔗 Connexion Strava"),
            get_strava_status()
        ]),
        
        # Interface activités
        html.Div(className="card", children=[
            html.H3("🚴‍♂️ Vos activités vélo"),
            html.Button('📥 Charger mes dernières activités', id='load-activities-btn', n_clicks=0,
                       className="btn btn-primary", style={'marginBottom': '15px'}),
            html.Div(id='activities-status'),
            dcc.Dropdown(id='activities-select', placeholder='Sélectionnez une activité à analyser...', 
                        disabled=True, style={'marginBottom': '20px'}),
            
            # Paramètres d'analyse
            html.Div([
                html.Div([
                    html.Label("💓 FC Max (bpm):", style={'fontWeight': 'bold'}),
                    dcc.Input(id='fc-max-input', type='number', value=190, min=120, max=220)
                ], style={'width': '30%', 'display': 'inline-block', 'marginRight': '5%'}),
                html.Div([
                    html.Label("⚡ FTP (watts):", style={'fontWeight': 'bold'}),
                    dcc.Input(id='ftp-input', type='number', value=250, min=100, max=500)
                ], style={'width': '30%', 'display': 'inline-block', 'marginRight': '5%'}),
                html.Div([
                    html.Label("⚖️ Poids (kg):", style={'fontWeight': 'bold'}),
                    dcc.Input(id='weight-input', type='number', value=70, min=40, max=150)
                ], style={'width': '30%', 'display': 'inline-block'})
            ], style={'marginBottom': '20px'}),
            
            html.Button('🔬 Analyser cette activité', id='analyze-btn', n_clicks=0, disabled=True,
                       className="btn btn-success", style={'width': '100%'}),
            
            html.Div(id='analysis-results', style={'marginTop': '20px'})
        ]),
        
        # Store pour les données
        dcc.Store(id='activities-data', data=[])
    ])

# Layout principal
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
    global current_token, user_message
    
    print(f"📍 Page demandée: {pathname}")
    
    # Traitement callback OAuth Strava
    if pathname == '/strava_callback' and search:
        print("🔄 Traitement callback Strava")
        
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
            
            print(f"Code reçu: {bool(code)}, Erreur: {error}")
            
            if error:
                user_message = f"❌ Erreur d'autorisation: {error}"
            elif code and STRAVA_CLIENT_ID and STRAVA_CLIENT_SECRET:
                # Échanger le code contre un token
                try:
                    token_request = {
                        'client_id': STRAVA_CLIENT_ID,
                        'client_secret': STRAVA_CLIENT_SECRET,
                        'code': code,
                        'grant_type': 'authorization_code'
                    }
                    
                    response = requests.post('https://www.strava.com/oauth/token', 
                                           data=token_request, timeout=15)
                    
                    print(f"Réponse token: {response.status_code}")
                    
                    if response.status_code == 200:
                        token_data = response.json()
                        current_token = token_data.get('access_token')
                        
                        if current_token:
                            user_message = "✅ Connexion à Strava réussie ! Vous pouvez maintenant utiliser toutes les fonctionnalités."
                            print("✅ Token Strava récupéré avec succès")
                        else:
                            user_message = "❌ Token d'accès non reçu de Strava"
                    else:
                        user_message = f"❌ Erreur lors de l'échange du token: {response.status_code}"
                        
                except Exception as e:
                    user_message = f"❌ Erreur de connexion à Strava: {str(e)}"
                    print(f"Erreur token: {e}")
            else:
                user_message = "❌ Configuration Strava incomplète (vérifiez vos variables d'environnement)"
                
        except Exception as e:
            user_message = f"❌ Erreur lors du traitement de l'autorisation: {str(e)}"
            print(f"Erreur callback: {e}")
    
    # Affichage des pages
    if pathname == '/activities':
        return create_activities_layout()
    else:
        return create_main_layout()

# Callback pour charger les activités
@app.callback(
    [Output('activities-select', 'options'),
     Output('activities-select', 'disabled'),
     Output('activities-status', 'children'),
     Output('activities-data', 'data')],
    Input('load-activities-btn', 'n_clicks'),
    prevent_initial_call=True
)
def load_activities(n_clicks):
    global current_token
    
    if not current_token:
        return [], True, html.Div("❌ Veuillez vous connecter à Strava d'abord", className="status-error"), []
    
    try:
        headers = {'Authorization': f'Bearer {current_token}'}
        response = requests.get('https://www.strava.com/api/v3/athlete/activities', 
                              headers=headers, params={'per_page': 15}, timeout=15)
        
        if response.status_code != 200:
            return [], True, html.Div(f"❌ Erreur API Strava: {response.status_code}", className="status-error"), []
        
        activities = response.json()
        bike_types = ['Ride', 'VirtualRide', 'EBikeRide', 'Gravel', 'MountainBikeRide']
        bike_activities = [a for a in activities if a.get('type') in bike_types]
        
        if not bike_activities:
            return [], True, html.Div("❌ Aucune activité vélo trouvée", className="status-error"), []
        
        options = []
        for activity in bike_activities:
            name = activity.get('name', 'Sans nom')[:50]
            date = activity.get('start_date_local', '')[:10]
            distance = round(activity.get('distance', 0) / 1000, 1)
            activity_type = activity.get('type', 'Ride')
            
            icons = {'Ride': '🚴', 'VirtualRide': '🚴‍💻', 'EBikeRide': '🚴‍⚡', 'Gravel': '🚵', 'MountainBikeRide': '🚵‍♂️'}
            icon = icons.get(activity_type, '🚴')
            
            label = f"{icon} {date} - {name} - {distance}km"
            options.append({'label': label, 'value': activity['id']})
        
        status = html.Div(f"✅ {len(bike_activities)} activités vélo chargées", className="status-connected")
        
        return options, False, status, bike_activities
        
    except Exception as e:
        return [], True, html.Div(f"❌ Erreur: {str(e)}", className="status-error"), []

# Callback pour activer le bouton d'analyse
@app.callback(
    Output('analyze-btn', 'disabled'),
    Input('activities-select', 'value')
)
def toggle_analyze_button(selected_activity):
    return selected_activity is None

# Callback pour la recherche de segments
@app.callback(
    [Output('map-results', 'children'),
     Output('search-status', 'children')],
    Input('search-btn', 'n_clicks'),
    State('search-input', 'value'),
    prevent_initial_call=True
)
def search_segments(n_clicks, address):
    global current_token
    
    if not address:
        return html.Div(), html.Div("❌ Veuillez entrer une ville ou une adresse", className="status-error")
    
    if not current_token:
        return html.Div(), html.Div("❌ Connectez-vous à Strava d'abord", className="status-error")
    
    if not WEATHER_KEY:
        return html.Div(), html.Div("❌ Configuration météo manquante", className="status-error")
    
    if not MAPBOX_TOKEN:
        return html.Div(), html.Div("❌ Configuration carte manquante", className="status-error")
    
    try:
        # Géocodage
        if not GEOPY_AVAILABLE:
            return html.Div(), html.Div("❌ Service de géocodage non disponible", className="status-error")
        
        geolocator = Nominatim(user_agent="kom_hunters")
        location = geolocator.geocode(address, timeout=10)
        
        if not location:
            return html.Div(), html.Div(f"❌ Impossible de localiser '{address}'", className="status-error")
        
        lat, lon = location.latitude, location.longitude
        
        # Recherche des segments
        if not ANALYZER_AVAILABLE:
            return html.Div(), html.Div("❌ Module d'analyse non disponible", className="status-error")
        
        segments, error = strava_analyzer.find_tailwind_segments_live(
            lat, lon, 10, current_token, WEATHER_KEY, 0.5
        )
        
        if error:
            return html.Div(), html.Div(f"❌ {error}", className="status-error")
        
        if not segments:
            return html.Div(), html.Div(f"ℹ️ Aucun segment avec vent favorable trouvé autour de '{address}'", 
                                      style={'color': '#f6ad55'})
        
        # Créer la carte
        fig = go.Figure()
        colors = ['red', 'blue', 'green', 'orange', 'purple', 'pink']
        
        for i, segment in enumerate(segments[:8]):
            if segment.get('polyline_coords'):
                coords = segment['polyline_coords']
                lats = [c[0] for c in coords if c[0]]
                lons = [c[1] for c in coords if c[1]]
                
                if len(lats) >= 2:
                    fig.add_trace(go.Scattermapbox(
                        lat=lats, lon=lons, mode='lines+markers',
                        line=dict(width=4, color=colors[i % len(colors)]),
                        marker=dict(size=6, color=colors[i % len(colors)]),
                        name=segment['name'][:25],
                        text=f"<b>{segment['name']}</b><br>📏 {segment.get('distance', 0):.0f}m<br>📈 {segment.get('avg_grade', 0):.1f}%<br>💨 +{segment.get('wind_effect_mps', 0):.2f} m/s"
                    ))
        
        # Calculer le centre
        all_lats = [c[0] for s in segments for c in s.get('polyline_coords', []) if c[0]]
        all_lons = [c[1] for s in segments for c in s.get('polyline_coords', []) if c[1]]
        
        if all_lats and all_lons:
            center_lat = sum(all_lats) / len(all_lats)
            center_lon = sum(all_lons) / len(all_lons)
            
            lat_range = max(all_lats) - min(all_lats)
            lon_range = max(all_lons) - min(all_lons)
            zoom = 13 if max(lat_range, lon_range) < 0.02 else 12
        else:
            center_lat, center_lon, zoom = lat, lon, 12
        
        fig.update_layout(
            mapbox_style="streets",
            mapbox_accesstoken=MAPBOX_TOKEN,
            mapbox_zoom=zoom,
            mapbox_center_lat=center_lat,
            mapbox_center_lon=center_lon,
            margin={"r":0,"t":0,"l":0,"b":0},
            height=500
        )
        
        map_div = html.Div([
            html.H4(f"🎉 {len(segments)} segments avec vent favorable trouvés !"),
            html.P("💡 Cliquez sur un segment pour voir ses détails", style={'color': '#666', 'fontStyle': 'italic'}),
            dcc.Graph(figure=fig, style={'height': '500px'})
        ])
        
        status = html.Div(f"✅ Recherche terminée - {len(segments)} segments trouvés", className="status-connected")
        
        return map_div, status
        
    except Exception as e:
        return html.Div(), html.Div(f"❌ Erreur lors de la recherche: {str(e)}", className="status-error")

print("✅ Tous les callbacks définis")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8050))
    debug = os.environ.get('RENDER') is None
    
    print(f"🚀 LANCEMENT KOM HUNTERS")
    print(f"📍 Port: {port}")
    print(f"🔧 Debug: {debug}")
    print(f"🌐 URL: {BASE_URL}")
    print(f"🔑 Variables configurées:")
    print(f"   - MAPBOX: {'✅' if MAPBOX_TOKEN else '❌'}")
    print(f"   - STRAVA_ID: {'✅' if STRAVA_CLIENT_ID else '❌'}")
    print(f"   - STRAVA_SECRET: {'✅' if STRAVA_CLIENT_SECRET else '❌'}")
    print(f"   - WEATHER: {'✅' if WEATHER_KEY else '❌'}")
    print(f"   - OPENAI: {'✅' if OPENAI_KEY else '❌'}")
    
    try:
        app.run_server(debug=debug, host='0.0.0.0', port=port)
    except Exception as e:
        print(f"❌ ERREUR CRITIQUE: {e}")
        import traceback
        traceback.print_exc()