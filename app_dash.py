import dash
from dash import dcc, html, Input, Output, State, callback_context
import plotly.graph_objects as go
import os
from dotenv import load_dotenv
import time 
import math 
import json 
import requests 
from datetime import datetime # Assurez-vous que cet import est bien là

# Pour le géocodage
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderUnavailable

# --- AJOUT POUR S'ASSURER QUE LE RÉPERTOIRE ACTUEL EST DANS SYS.PATH ---
import sys
current_script_directory = os.path.dirname(os.path.abspath(__file__))
if current_script_directory not in sys.path:
    sys.path.insert(0, current_script_directory)
print(f"--- DEBUG (app_dash): Répertoire du script ajouté à sys.path: {current_script_directory} ---")
# --- FIN DE L'AJOUT ---

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
current_strava_access_token = os.getenv('MY_NEW_STRAVA_ACCESS_TOKEN') 
new_token_info_global = "Aucun nouveau token obtenu pour cette session."
WEATHER_API_KEY = os.getenv('OPENWEATHERMAP_API_KEY')

print(f"--- DEBUG (app_dash): Token Mapbox: {'Présent' if MAPBOX_ACCESS_TOKEN else 'MANQUANT'} ---")
print(f"--- DEBUG (app_dash): Strava Client ID: {'Présent' if STRAVA_CLIENT_ID else 'MANQUANT'} ---")
print(f"--- DEBUG (app_dash): Strava Client Secret: {'Présent' if STRAVA_CLIENT_SECRET else 'MANQUANT'} ---")
print(f"--- DEBUG (app_dash): Token Strava initial (depuis .env): {'Présent et chargé' if current_strava_access_token else 'MANQUANT ou non chargé'} ---")
print(f"--- DEBUG (app_dash): Clé OpenWeatherMap: {'Présente' if WEATHER_API_KEY else 'MANQUANTE'} ---")

INITIAL_LAT = 46.2276  
INITIAL_LNG = 2.2137
INITIAL_ZOOM = 5
SEARCH_RADIUS_KM = 15.0
MIN_TAILWIND_EFFECT_MPS_SEARCH = 0.5 
STRAVA_REDIRECT_URI = 'http://localhost:8050/strava_callback' 
STRAVA_SCOPES = 'read,activity:read_all,profile:read_all'

# --- Fonctions Utilitaires (Géocodage - inchangées) ---
def get_address_suggestions(query_str, limit=5):
    if not query_str or len(query_str) < 3: 
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

# --- FONCTION DE RECHERCHE DE SEGMENTS UTILISANT strava_analyzer ---
def find_tailwind_segments_live(lat, lon, radius_km, strava_token_to_use, weather_key, min_tailwind_effect_mps):
    print(f"Appel à find_tailwind_segments_live pour {lat:.4f}, {lon:.4f} avec token: {'Présent' if strava_token_to_use else 'MANQUANT'}")
    
    if not strava_token_to_use: 
        print("Erreur (find_tailwind_segments_live): Token Strava manquant.")
        return [], "Token Strava manquant. Veuillez vous connecter." 

    if not weather_key:
        print("Avertissement (find_tailwind_segments_live): Clé météo manquante. L'analyse du vent sera désactivée.")
        return [], "Clé API Météo manquante. Analyse du vent impossible."

    def _get_bounding_box_local(latitude, longitude, radius_km_local): 
        lat_radians_local = math.radians(latitude) 
        delta_lat_local = radius_km_local / 111.32
        delta_lon_local = radius_km_local / (111.32 * math.cos(lat_radians_local))
        return [latitude - delta_lat_local, longitude - delta_lon_local, latitude + delta_lat_local, longitude + delta_lon_local]
    bounds_list = _get_bounding_box_local(lat, lon, radius_km)
    bounds_str = ",".join(map(str, bounds_list))

    wind_data = strava_analyzer.get_wind_data(lat, lon, weather_key) 
    
    if not wind_data or wind_data.get('speed') is None or wind_data.get('deg') is None:
        print("Impossible de récupérer les données de vent valides pour la recherche live.")
        return [], "Données de vent non récupérables pour cette zone."
    current_wind_speed = wind_data['speed']
    current_wind_direction = wind_data['deg']
    print(f"Vent pour la zone: {current_wind_speed:.2f} m/s de {current_wind_direction}°")

    explore_params = {'bounds': bounds_str, 'activity_type': 'riding'} 
    explore_result = strava_analyzer._make_strava_api_request("segments/explore", strava_token_to_use, params=explore_params)

    if not explore_result: 
        print("Erreur lors de l'appel à Strava pour explorer les segments.")
        return [], "Erreur de communication avec Strava pour trouver les segments."
        
    if explore_result.get("message") == "Authorization Error":
        print("ERREUR D'AUTORISATION STRAVA DÉTECTÉE - Le token est invalide ou expiré.")
        return [], "Erreur d'autorisation Strava. Veuillez (re)connecter votre compte."

    if 'segments' not in explore_result:
        print("Aucun segment trouvé par Strava dans la zone ou format de réponse inattendu.")
        return [], "Aucun segment retourné par Strava pour cette zone."
    
    found_strava_segments = explore_result['segments']
    print(f"{len(found_strava_segments)} segments Strava trouvés dans la zone.")
    if not found_strava_segments:
        return [], "Aucun segment trouvé par Strava dans cette zone."
    
    tailwind_segments_details = []
    for seg_summary in found_strava_segments:
        segment_id = seg_summary.get('id')
        segment_name = seg_summary.get('name')
        encoded_polyline = seg_summary.get('points')
        
        if not encoded_polyline:
            continue

        coordinates = strava_analyzer.decode_strava_polyline(encoded_polyline)
        if coordinates and len(coordinates) >= 2:
            segment_bearing = strava_analyzer.calculate_bearing(coordinates[0][0], coordinates[0][1], coordinates[-1][0], coordinates[-1][1])
            wind_effect = strava_analyzer.get_wind_effect_on_leg(segment_bearing, current_wind_speed, current_wind_direction)
            
            if wind_effect['type'] == "Vent de Dos" and wind_effect['effective_speed_mps'] >= min_tailwind_effect_mps:
                tailwind_segments_details.append({
                    "id": segment_id,
                    "name": segment_name,
                    "polyline_coords": coordinates, 
                    "strava_link": f"https://www.strava.com/segments/{segment_id}",
                    "distance": seg_summary.get('distance'),
                    "avg_grade": seg_summary.get('avg_grade'),
                    "bearing": round(segment_bearing,1),
                    "wind_effect_mps": wind_effect['effective_speed_mps']
                })
                print(f"  -> VENT DE DOS pour '{segment_name}' (Cap: {segment_bearing:.1f}°, Effet: {wind_effect['effective_speed_mps']:.2f} m/s)")
        time.sleep(0.05) 

    return tailwind_segments_details, None 


# --- Initialisation de l'Application Dash ---
app = dash.Dash(__name__, external_stylesheets=['https://codepen.io/chriddyp/pen/bWLwgP.css']) 
app.title = "KOM Hunters - Recherche par Adresse"
app.config.suppress_callback_exceptions = True 

# --- Fonction pour construire le layout principal ---
def build_main_page_layout():
    global new_token_info_global
    global current_strava_access_token

    auth_url = (
        f"https://www.strava.com/oauth/authorize?"
        f"client_id={STRAVA_CLIENT_ID}"
        f"&redirect_uri={STRAVA_REDIRECT_URI}"
        f"&response_type=code"
        f"&approval_prompt=force"  
        f"&scope={STRAVA_SCOPES}"
    )
    token_display = "Non disponible. Veuillez vous connecter."
    if current_strava_access_token:
        token_display = f"...{current_strava_access_token[-6:]}" if len(current_strava_access_token) > 6 else "Présent (court)"

    return html.Div(style={'fontFamily': 'Inter, sans-serif', 'padding': '0', 'margin': '0', 'height': '100vh', 'display': 'flex', 'flexDirection': 'column'}, children=[
        html.Div(style={'backgroundColor': '#1a202c', 'color': 'white', 'padding': '1rem', 'textAlign': 'center', 'flexShrink': '0'}, children=[
            html.H1("KOM Hunters - Recherche de Segments par Adresse", style={'margin': '0 0 10px 0', 'fontSize': '1.8rem'}),
            html.A(html.Button("Connecter avec Strava / Rafraîchir Token", id="login-strava-button"), href=auth_url, style={'marginBottom': '10px', 'display': 'inline-block', 'marginRight': '20px'}), 
            html.Div(id='token-status-message', children=f"Token Strava actuel : {token_display}", style={'color': '#A0AEC0', 'marginBottom': '5px', 'fontSize':'0.8em'}),
            html.Div(id='new-token-info-display', children=new_token_info_global, style={'color': '#A0AEC0', 'fontSize':'0.8em', 'whiteSpace': 'pre-line'}),
            html.Div(style={'display': 'flex', 'flexDirection': 'column', 'alignItems': 'center', 'gap': '5px', 'position': 'relative', 'marginTop': '10px'}, children=[ 
                dcc.Input(
                    id='address-input', type='text', placeholder='Commencez à taper une ville ou une adresse...',
                    debounce=True, 
                    style={'padding': '10px', 'fontSize': '1rem', 'borderRadius': '5px', 'border': '1px solid #4A5568', 'width': '400px', 'backgroundColor': '#2D3748', 'color': '#E2E8F0'}
                ),
                html.Div(id='live-address-suggestions-container', 
                         style={
                             'width': '400px', 'maxHeight': '200px', 'overflowY': 'auto', 
                             'backgroundColor': 'white', 'border': '1px solid #ccc',
                             'borderRadius': '5px', 'marginTop': '2px',
                             'position': 'absolute', 'top': '100%', 'zIndex': '100', 'textAlign': 'left'
                         }
                ),
                html.Button('Chercher les Segments !', id='search-button', n_clicks=0, 
                            style={'padding': '10px 15px', 'fontSize': '1rem', 'backgroundColor': '#3182CE', 'color': 'white', 'border': 'none', 'borderRadius': '5px', 'cursor': 'pointer', 'marginTop': '10px'})
            ]),
            html.Div(id='search-status-message', style={'marginTop': '10px', 'minHeight': '20px', 'color': '#A0AEC0'})
        ]),
        
        dcc.Loading(
            id="loading-map-results", type="default",
            children=[dcc.Graph(id='map-results-graph', style={'flexGrow': '1', 'minHeight': '0'})]
        ),
        dcc.Store(id='selected-suggestion-store', data=None)
    ])

# --- Layout de l'Application (Shell) ---
app.layout = html.Div([
    dcc.Location(id='url', refresh=False), 
    html.Div(id='page-content') 
])

# --- Callbacks de Navigation et d'Authentification ---
@app.callback(
    Output('page-content', 'children'),
    Input('url', 'pathname') 
    # Retrait de prevent_initial_call pour que la page principale se charge toujours
)
def display_page_content(pathname):
    if pathname == '/strava_callback':
        # La logique de traitement du code et de redirection est dans handle_strava_oauth_callback
        return html.Div([
            html.H2("Traitement de l'autorisation Strava..."),
            html.P("Vous allez être redirigé(e) sous peu.", id="callback-message"),
        ])
    return build_main_page_layout() 

@app.callback(
    [Output('token-status-message', 'children', allow_duplicate=True), # allow_duplicate car build_main_page_layout le définit aussi
     Output('new-token-info-display', 'children', allow_duplicate=True),# allow_duplicate
     Output('url', 'pathname', allow_duplicate=True)], # MODIFIÉ: Cible l'URL principale pour redirection
    [Input('url', 'search')], 
    prevent_initial_call=True 
)
def handle_strava_oauth_callback(search_query_params):
    global current_strava_access_token 
    global new_token_info_global

    # Ce callback ne devrait être déclenché que par un changement de 'search' après la redirection de Strava.
    # La condition `pathname == '/strava_callback'` est implicitement gérée par le fait que
    # Strava redirige vers cette URL avec des query_params.
    
    print(f"DEBUG handle_strava_oauth_callback: search_query_params = {search_query_params}")

    if not search_query_params: # Si pas de query params (ex: navigation manuelle vers /strava_callback)
        print("DEBUG handle_strava_oauth_callback: Pas de query params, pas de traitement.")
        return dash.no_update, dash.no_update, dash.no_update

    params = dict(qc.split("=") for qc in search_query_params[1:].split("&")) 
    auth_code = params.get('code')
    error = params.get('error')

    if error:
        new_token_info_global = f"Erreur d'autorisation Strava: {error}"
        print(new_token_info_global)
        # Met à jour les messages et redirige vers la page principale
        return f"Token Strava : Erreur - {error}", new_token_info_global, "/" 
    
    if auth_code:
        print(f"Code d'autorisation Strava reçu: {auth_code[:20]}...")
        if not STRAVA_CLIENT_ID or not STRAVA_CLIENT_SECRET:
            new_token_info_global = "Erreur: Client ID ou Client Secret Strava non configurés côté serveur."
            return "Token Strava: Erreur de configuration serveur.", new_token_info_global, "/"

        token_url = 'https://www.strava.com/oauth/token'
        payload = {
            'client_id': STRAVA_CLIENT_ID,
            'client_secret': STRAVA_CLIENT_SECRET,
            'code': auth_code,
            'grant_type': 'authorization_code',
            'redirect_uri': STRAVA_REDIRECT_URI # Strava peut exiger cela pour certaines configurations
        }
        try:
            response = requests.post(token_url, data=payload, timeout=15)
            response.raise_for_status()
            token_data = response.json()
            
            current_strava_access_token = token_data.get('access_token')
            refresh_token = token_data.get('refresh_token') 
            expires_at = token_data.get('expires_at')
            
            if current_strava_access_token:
                os.environ['MY_NEW_STRAVA_ACCESS_TOKEN'] = current_strava_access_token 
                print(f"Nouveau Strava Access Token stocké dans l'environnement (pour cette session): ...{current_strava_access_token[-6:]}")
            
            new_token_info_global = (
                f"Nouveau Token d'Accès Obtenu: ...{current_strava_access_token[-6:] if current_strava_access_token else 'ERREUR'}\n"
                f"Refresh Token: ...{refresh_token[-6:] if refresh_token else 'N/A'}\n"
                f"Expire à (UTC): {datetime.utcfromtimestamp(expires_at).strftime('%Y-%m-%d %H:%M:%S') if expires_at else 'N/A'}"
            )
            print(f"Nouveaux tokens Strava obtenus: {new_token_info_global}")
            
            # Met à jour les messages et redirige vers la page principale
            return f"Token Strava : ...{current_strava_access_token[-6:]}", new_token_info_global, "/" 
        except requests.exceptions.RequestException as e:
            print(f"Erreur lors de l'échange du code OAuth: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"Détails de l'erreur API Strava: {e.response.text}")
                new_token_info_global = f"Erreur API Strava lors de l'échange du code: {e.response.status_code} - {e.response.text}"
            else:
                new_token_info_global = f"Erreur lors de l'échange du code OAuth: {e}"
            return "Token Strava: Erreur d'échange de code.", new_token_info_global, "/"
    
    # Si pas de code et pas d'erreur, ne rien faire et ne pas rediriger
    return dash.no_update, dash.no_update, dash.no_update


# --- Callbacks pour la recherche d'adresse et de segments ---
@app.callback(
    Output('live-address-suggestions-container', 'children'),
    Input('address-input', 'value')
)
def update_live_suggestions(typed_address):
    if not typed_address or len(typed_address) < 3:
        return [] 
    suggestions_data, error = get_address_suggestions(typed_address, limit=5)
    if error: return [html.P(f"Erreur : {error}", style={'padding': '5px', 'color': 'red'})]
    if not suggestions_data: return [html.P("Aucune suggestion trouvée.", style={'padding': '5px'})]
    
    suggestion_elements = []
    for i, sugg_data in enumerate(suggestions_data):
        suggestion_elements.append(
            html.Div(
                sugg_data['display_name'],
                id={'type': 'suggestion-item', 'index': i}, 
                n_clicks=0, 
                style={'padding': '8px 10px', 'cursor': 'pointer', 'borderBottom': '1px solid #eee', 'color': '#333'}
            )
        )
    return suggestion_elements

@app.callback(
    [Output('address-input', 'value'),
     Output('selected-suggestion-store', 'data'),
     Output('live-address-suggestions-container', 'children', allow_duplicate=True)],
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
        return selected_suggestion['display_name'], selected_suggestion, [] 
    return dash.no_update, dash.no_update, [] 

@app.callback(
    [Output('map-results-graph', 'figure'),
     Output('search-status-message', 'children'),
     Output('selected-suggestion-store', 'data', allow_duplicate=True)],
    [Input('search-button', 'n_clicks')],
    [State('address-input', 'value'),
     State('selected-suggestion-store', 'data')],
    prevent_initial_call=True 
)
def search_and_display_segments(n_clicks, address_input_value, selected_suggestion_data):
    global current_strava_access_token 
    
    search_lat, search_lon = None, None
    display_address = ""
    error_message_search = None

    if selected_suggestion_data and selected_suggestion_data.get('lat') is not None:
        search_lat = selected_suggestion_data['lat']
        search_lon = selected_suggestion_data['lon']
        display_address = selected_suggestion_data['display_name']
        print(f"Recherche basée sur la suggestion stockée: {display_address}")
    elif address_input_value:
        coords, error_msg, addr_disp = geocode_address_directly(address_input_value)
        if coords:
            search_lat, search_lon = coords
            display_address = addr_disp
        else: error_message_search = error_msg
    else: 
        error_message_search = "Veuillez entrer une adresse ou sélectionner une suggestion."

    default_fig = go.Figure()
    default_fig.update_layout(
        mapbox_style="streets", mapbox_accesstoken=MAPBOX_ACCESS_TOKEN,
        mapbox_zoom=INITIAL_ZOOM, mapbox_center_lat=INITIAL_LAT, mapbox_center_lon=INITIAL_LNG,
        margin={"r":0,"t":0,"l":0,"b":0}, uirevision='default_map_state'
    )

    if error_message_search:
        return default_fig, f"Erreur: {error_message_search}", None 

    if search_lat is None or search_lon is None: 
        return default_fig, "Impossible de déterminer les coordonnées pour la recherche.", None

    if not current_strava_access_token: 
        print("ERREUR (search_and_display_segments): Token Strava non disponible.")
        return default_fig, "Erreur: Token Strava non disponible. Veuillez vous connecter via le bouton.", None
    if not WEATHER_API_KEY:
        print("ERREUR (search_and_display_segments): Clé API Météo non disponible.")
        return default_fig, "Erreur de configuration serveur: Clé API Météo manquante.", None

    found_segments, segments_error_msg = find_tailwind_segments_live( 
        search_lat, search_lon, SEARCH_RADIUS_KM, 
        current_strava_access_token, WEATHER_API_KEY, 
        MIN_TAILWIND_EFFECT_MPS_SEARCH
    )
    if segments_error_msg: 
         return default_fig, f"Erreur lors de la recherche de segments: {segments_error_msg}", None


    fig = go.Figure() 
    fig.add_trace(go.Scattermapbox(
        lat=[search_lat], lon=[search_lon], mode='markers',
        marker=go.scattermapbox.Marker(size=15, color='red', symbol='star'),
        text=[f"Recherche: {display_address}"], hoverinfo='text', name='Recherche'
    ))

    status_msg = ""
    if not found_segments:
        status_msg = f"Aucun segment avec vent favorable trouvé autour de '{display_address}'."
    else:
        status_msg = f"{len(found_segments)} segment(s) avec vent favorable trouvé(s) autour de '{display_address}' !"
        for i, segment in enumerate(found_segments):
            if segment.get("polyline_coords"): 
                lats, lons = zip(*segment['polyline_coords'])
                fig.add_trace(go.Scattermapbox(
                    lat=list(lats), lon=list(lons), mode='lines',
                    line=dict(width=4, color='rgba(255, 0, 0, 0.7)'), 
                    name=segment['name'],
                    text=f"<b>{segment['name']}</b><br>ID: {segment['id']}<br>Distance: {segment.get('distance','N/A'):.0f}m<br>Pente: {segment.get('avg_grade','N/A'):.1f}%<br>Cap: {segment.get('bearing','N/A')}°<br>Effet Vent: +{segment.get('wind_effect_mps','N/A'):.2f} m/s<br><a href='{segment['strava_link']}' target='_blank'>Voir sur Strava</a>",
                    hoverinfo='text', customdata=[segment['id']] * len(lats) 
                ))
            else:
                print(f"Segment '{segment.get('name')}' n'a pas de polyligne_coords.")

    fig.update_layout(
        mapbox_style="streets", mapbox_accesstoken=MAPBOX_ACCESS_TOKEN,
        mapbox_zoom=12, 
        mapbox_center_lat=search_lat, 
        mapbox_center_lon=search_lon,
        margin={"r":0,"t":0,"l":0,"b":0}, showlegend=False,
        uirevision=f'map_results_{search_lat}_{search_lon}'
    )
    return fig, status_msg, None 

# --- Exécution de l'Application ---
if __name__ == '__main__':
    if not all([MAPBOX_ACCESS_TOKEN, STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET, WEATHER_API_KEY]):
        print("ERREUR CRITIQUE: Une ou plusieurs clés/ID API sont manquants.")
        print("Vérifiez MAPBOX_ACCESS_TOKEN, STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET, OPENWEATHERMAP_API_KEY dans .env")
    
    print("Pour accéder à l'application, ouvrez votre navigateur et allez à http://127.0.0.1:8050/")
    print("Si le token Strava est manquant ou invalide, utilisez le bouton 'Connecter avec Strava'.")
    app.run(debug=True)
