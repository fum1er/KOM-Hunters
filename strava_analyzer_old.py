import requests
import os
from dotenv import load_dotenv
import json # Pour sauvegarder/charger des données si besoin, ou pour le pretty print
import time
import polyline
import math

# Charger les variables d'environnement (si tu y stockes ton token par exemple)
load_dotenv()

# Récupère ton token d'accès. Assure-toi que la clé est correcte dans ton .env
# Ce token doit avoir les scopes nécessaires (ex: 'read,activity:read_all')
ACCESS_TOKEN = os.getenv('MY_NEW_STRAVA_ACCESS_TOKEN')
OPENWEATHERMAP_API_KEY = os.getenv('OPENWEATHERMAP_API_KEY') 

BASE_STRAVA_URL = 'https://www.strava.com/api/v3'

def _make_strava_api_request(endpoint, access_token, params=None):
    """
    Fonction d'aide pour faire des requêtes GET authentifiées à l'API Strava.
    Gère les erreurs de base.
    """
    headers = {'Authorization': f'Bearer {access_token}'}
    full_url = f"{BASE_STRAVA_URL}/{endpoint}"
    
    # print(f"Debug: Appel à {full_url} avec params {params}") # Décommente pour le débogage
    
    try:
        response = requests.get(full_url, headers=headers, params=params)
        response.raise_for_status()  # Lève une exception pour les erreurs HTTP (4xx, 5xx)
        return response.json()
    except requests.exceptions.HTTPError as http_err:
        print(f"Erreur HTTP lors de l'appel à {full_url}: {http_err}")
        print(f"Réponse de l'API: {response.text if 'response' in locals() else 'N/A'}")
    except requests.exceptions.RequestException as req_err:
        print(f"Erreur de requête (problème réseau ?) lors de l'appel à {full_url}: {req_err}")
    except Exception as e:
        print(f"Une erreur inattendue est survenue lors de l'appel à {full_url}: {e}")
    return None

def get_segments_from_activity(activity_id, access_token):
    """
    Récupère et retourne la liste des segments (SummarySegment) passés durant une activité spécifique.
    """
    if not access_token:
        print("Erreur: Token d'accès requis.")
        return None
    if not activity_id:
        print("Erreur: ID d'activité requis.")
        return None

    # L'endpoint pour les détails d'une activité inclut les "segment_efforts"
    # Le paramètre 'include_all_efforts=true' peut être utile mais n'est pas toujours nécessaire
    # pour juste la liste des segments. Par défaut, il retourne les efforts clés.
    endpoint = f"activities/{activity_id}" 
    
    print(f"\nRécupération des détails de l'activité ID: {activity_id}...")
    activity_details = _make_strava_api_request(endpoint, access_token)
    
    if activity_details and 'segment_efforts' in activity_details:
        segments_in_activity = []
        print(f"  {len(activity_details['segment_efforts'])} efforts de segment trouvés.")
        for effort in activity_details['segment_efforts']:
            # Chaque 'effort' contient un objet 'segment' qui est un SummarySegment
            if 'segment' in effort:
                segments_in_activity.append(effort['segment'])
        return segments_in_activity
    elif activity_details:
        print(f"  Aucun 'segment_efforts' trouvé dans les détails de l'activité (l'activité est peut-être encore en cours de traitement ou n'a pas de segments).")
        print(f"  Détails reçus: {json.dumps(activity_details, indent=2)}") # Affiche ce qui a été reçu
    else:
        print(f"  Impossible de récupérer les détails pour l'activité ID: {activity_id}")
        
    return None

def get_starred_segments(access_token, page=1, per_page=30):
    """
    Récupère et retourne une page des segments mis en favoris (starred) par l'athlète authentifié.
    Cette fonction récupère une seule page. Pour tous les récupérer, il faudra implémenter une boucle de pagination.
    """
    if not access_token:
        print("Erreur: Token d'accès requis.")
        return None

    endpoint = "segments/starred"
    params = {'page': page, 'per_page': per_page}
    
    print(f"\nRécupération de la page {page} des segments favoris (max {per_page} par page)...")
    starred_segments = _make_strava_api_request(endpoint, access_token, params=params)
    
    if starred_segments:
        print(f"  {len(starred_segments)} segments favoris trouvés sur cette page.")
    else:
        # Cela peut aussi signifier qu'il n'y a plus de segments favoris sur les pages suivantes
        print(f"  Aucun segment favori trouvé sur la page {page} ou erreur lors de la récupération.")
        
    return starred_segments

def get_all_starred_segments(access_token, per_page=100):
    """
    Récupère et retourne TOUS les segments mis en favoris par l'athlète authentifié,
    en gérant la pagination.
    """
    if not access_token:
        print("Erreur: Token d'accès requis.")
        return None

    all_starred = []
    current_page = 1
    print("\nDébut de la récupération de TOUS les segments favoris...")
    while True:
        print(f"  Récupération de la page {current_page} des segments favoris...")
        segments_on_page = get_starred_segments(access_token, page=current_page, per_page=per_page)
        
        if segments_on_page: # Si la page contient des segments
            all_starred.extend(segments_on_page)
            if len(segments_on_page) < per_page: # Si on a reçu moins que per_page, c'était la dernière page
                print("  C'était la dernière page de segments favoris.")
                break
            current_page += 1
            time.sleep(0.5) # Petite pause pour être gentil avec l'API
        else: # Si segments_on_page est None (erreur) ou une liste vide (plus de segments)
            print("  Fin de la récupération des segments favoris ou une erreur est survenue.")
            break
            
    print(f"{len(all_starred)} segments favoris récupérés au total.")
    return all_starred

# ... (imports et code existant de strava_analyzer.py : BASE_STRAVA_URL, _make_strava_api_request, etc.) ...
# Assure-toi que ACCESS_TOKEN est bien chargé depuis ton .env avec le token valide

def get_segment_details(segment_id, access_token):
    """
    Récupère et retourne les détails complets (DetailedSegment) d'un segment spécifique.
    """
    if not access_token:
        print("Erreur: Token d'accès requis.")
        return None
    if not segment_id:
        print("Erreur: ID de segment requis.")
        return None

    endpoint = f"segments/{segment_id}" 
    
    print(f"\nRécupération des détails complets du segment ID: {segment_id}...")
    segment_data = _make_strava_api_request(endpoint, access_token)
    
    if segment_data:
        print(f"  Détails du segment '{segment_data.get('name')}' récupérés avec succès.")
    else:
        print(f"  Impossible de récupérer les détails pour le segment ID: {segment_id}")
        
    return segment_data

def decode_strava_polyline(encoded_polyline):
    """
    Décode une chaîne de polyligne Strava en une liste de coordonnées (latitude, longitude).
    """
    if not encoded_polyline:
        print("Erreur: Chaîne de polyligne encodée requise.")
        return None
    
    try:
        # La bibliothèque polyline.decode() renvoie une liste de tuples (latitude, longitude)
        decoded_coordinates = polyline.decode(encoded_polyline)
        # Par défaut, la précision est de 5 décimales. Strava utilise parfois une précision de 5.
        # Si tu as des soucis de précision, polyline.decode(encoded_polyline, precision=5)
        print(f"  Polyligne décodée avec succès en {len(decoded_coordinates)} points.")
        return decoded_coordinates
    except Exception as e:
        print(f"Erreur lors du décodage de la polyligne: {e}")
        return None
    
def calculate_bearing(lat1, lon1, lat2, lon2):
    """
    Calcule le cap initial (bearing) pour aller du point 1 au point 2.
    Les latitudes et longitudes doivent être en degrés.
    Retourne le cap en degrés (0-360, Nord = 0, Est = 90, Sud = 180, Ouest = 270).
    """
    # Convertir les degrés en radians
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)

    delta_lon = lon2_rad - lon1_rad

    x = math.sin(delta_lon) * math.cos(lat2_rad)
    y = math.cos(lat1_rad) * math.sin(lat2_rad) - \
        math.sin(lat1_rad) * math.cos(lat2_rad) * math.cos(delta_lon)

    initial_bearing_rad = math.atan2(x, y)

    # Convertir le bearing de radians en degrés
    initial_bearing_deg = math.degrees(initial_bearing_rad)

    # Normaliser pour avoir un résultat entre 0 et 360 degrés
    compass_bearing_deg = (initial_bearing_deg + 360) % 360

    return compass_bearing_deg

def haversine_distance(lat1, lon1, lat2, lon2):
    """
    Calcule la distance en mètres entre deux points GPS en utilisant la formule de Haversine.
    Latitudes et longitudes doivent être en degrés.
    """
    R = 6371000  # Rayon de la Terre en mètres

    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)

    delta_lat = lat2_rad - lat1_rad
    delta_lon = lon2_rad - lon1_rad

    a = math.sin(delta_lat / 2)**2 + \
        math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    distance = R * c
    return distance

# ... (imports et fonctions existantes, y compris calculate_bearing et haversine_distance) ...

def get_segment_leg_orientations(coordinates, 
                                 min_points_for_bearing=3, 
                                 angle_change_threshold_degrees=30.0,
                                 min_leg_distance_meters=50.0):
    """
    Décompose un segment (liste de coordonnées) en plusieurs tronçons (legs)
    basés sur les changements d'orientation.

    Args:
        coordinates: Liste de tuples (latitude, longitude).
        min_points_for_bearing: Nombre minimum de points pour calculer un cap stable pour un tronçon.
        angle_change_threshold_degrees: Changement d'angle (en degrés) pour considérer un nouveau tronçon.
        min_leg_distance_meters: Distance minimale (en mètres) pour qu'un tronçon soit enregistré.

    Returns:
        Une liste de dictionnaires, chaque dictionnaire représentant un tronçon avec :
        'start_coord', 'end_coord', 'distance_m', 'bearing_deg', 'points_in_leg'
    """
    if not coordinates or len(coordinates) < min_points_for_bearing:
        print("Pas assez de coordonnées pour analyser les tronçons.")
        return []

    legs = []
    current_leg_points = []
    
    # Initialiser le premier tronçon potentiel
    leg_start_index = 0
    current_leg_points.append(coordinates[0])

    for i in range(len(coordinates) - 1):
        current_leg_points.append(coordinates[i+1])

        if len(current_leg_points) >= min_points_for_bearing:
            # Calculer le cap du tronçon actuel (des N derniers points)
            # On prend le premier point du tronçon actuel et le dernier point ajouté
            current_leg_start_coord = current_leg_points[0]
            current_leg_end_coord = current_leg_points[-1]
            current_leg_bearing = calculate_bearing(current_leg_start_coord[0], current_leg_start_coord[1],
                                                    current_leg_end_coord[0], current_leg_end_coord[1])

            # Regarder en avant pour le prochain cap potentiel (si assez de points restants)
            if i + min_points_for_bearing < len(coordinates):
                next_potential_leg_start_coord = current_leg_points[-1] # Le dernier point du tronçon actuel
                next_potential_leg_end_coord = coordinates[i + min_points_for_bearing -1] # Un point un peu plus loin
                
                # Assurer que les points ne sont pas identiques pour éviter division par zéro dans calculate_bearing
                if next_potential_leg_start_coord != next_potential_leg_end_coord:
                    next_bearing = calculate_bearing(next_potential_leg_start_coord[0], next_potential_leg_start_coord[1],
                                                     next_potential_leg_end_coord[0], next_potential_leg_end_coord[1])
                    
                    angle_diff = abs(next_bearing - current_leg_bearing)
                    # Gérer le cas où l'angle passe par 0/360 (ex: 350° vs 10°)
                    if angle_diff > 180:
                        angle_diff = 360 - angle_diff
                else:
                    angle_diff = 0 # Pas de changement si les points sont identiques
            else:
                # On est proche de la fin, pas assez de points pour calculer un "next_bearing" fiable
                angle_diff = 0 # On considère qu'on continue sur le même tronçon

            # Si le changement d'angle est significatif OU si on arrive à la fin de la polyligne
            if angle_diff > angle_change_threshold_degrees or i == len(coordinates) - 2:
                # Calculer la distance du tronçon qu'on vient de terminer
                leg_distance = 0
                for k in range(len(current_leg_points) - 1):
                    leg_distance += haversine_distance(current_leg_points[k][0], current_leg_points[k][1],
                                                       current_leg_points[k+1][0], current_leg_points[k+1][1])

                if leg_distance >= min_leg_distance_meters or i == len(coordinates) - 2 : # ou si c'est le dernier tronçon
                    legs.append({
                        'start_coord': current_leg_points[0],
                        'end_coord': current_leg_points[-1],
                        'distance_m': round(leg_distance, 2),
                        'bearing_deg': round(current_leg_bearing, 2),
                        'num_points': len(current_leg_points)
                    })
                
                # Commencer un nouveau tronçon à partir du point actuel (qui devient le début du nouveau)
                leg_start_index = i 
                current_leg_points = [coordinates[i+1]] # Le nouveau tronçon commence par le point de fin du précédent
    
    # Cas spécial: si le dernier tronçon est trop court et n'a pas été ajouté,
    # mais qu'il y avait des points restants, on l'ajoute s'il est significatif.
    # La logique ci-dessus devrait déjà couvrir la plupart des cas pour le dernier tronçon.
    # S'il reste des points dans current_leg_points et que la boucle est finie sans ajouter le dernier leg:
    if len(current_leg_points) >= min_points_for_bearing and (not legs or legs[-1]['end_coord'] != current_leg_points[-1]):
        leg_distance = 0
        for k in range(len(current_leg_points) - 1):
            leg_distance += haversine_distance(current_leg_points[k][0], current_leg_points[k][1],
                                               current_leg_points[k+1][0], current_leg_points[k+1][1])
        if leg_distance >= min_leg_distance_meters :
             current_leg_start_coord = current_leg_points[0]
             current_leg_end_coord = current_leg_points[-1]
             current_leg_bearing = calculate_bearing(current_leg_start_coord[0], current_leg_start_coord[1],
                                                    current_leg_end_coord[0], current_leg_end_coord[1])
             legs.append({
                'start_coord': current_leg_points[0],
                'end_coord': current_leg_points[-1],
                'distance_m': round(leg_distance, 2),
                'bearing_deg': round(current_leg_bearing, 2),
                'num_points': len(current_leg_points)
            })


    return legs

def get_wind_data(latitude, longitude, api_key):
    """
    Récupère les données de vent actuelles pour des coordonnées GPS données
    en utilisant l'API OpenWeatherMap.
    Retourne un dictionnaire avec 'speed' (m/s) and 'deg' (direction en degrés).
    """
    if not api_key:
        print("Erreur: Clé API OpenWeatherMap manquante (OPENWEATHERMAP_API_KEY dans .env).")
        return None
    
    weather_url = (
        f"https://api.openweathermap.org/data/2.5/weather?"
        f"lat={latitude}&lon={longitude}"
        f"&appid={api_key}"
        f"&units=metric" # Pour avoir la vitesse en m/s
    )
    
    # print(f"Debug: Appel à OpenWeatherMap pour {latitude},{longitude}") # Décommente pour le débogage
    
    try:
        response = requests.get(weather_url)
        response.raise_for_status()
        weather_data = response.json()
        
        if 'wind' in weather_data:
            return {
                'speed': weather_data['wind'].get('speed'), # Vitesse du vent en m/s
                'deg': weather_data['wind'].get('deg'),     # Direction du vent en degrés
                'gust': weather_data['wind'].get('gust')    # Rafales (optionnel)
            }
        else:
            print("Données de vent non trouvées dans la réponse d'OpenWeatherMap.")
            # print(json.dumps(weather_data, indent=2)) # Pour voir la réponse complète
            return None
            
    except requests.exceptions.HTTPError as http_err:
        print(f"Erreur HTTP lors de l'appel à OpenWeatherMap: {http_err}")
        print(f"Réponse: {response.text if 'response' in locals() else 'N/A'}")
    except Exception as e:
        print(f"Une erreur est survenue avec OpenWeatherMap: {e}")
    return None

def get_wind_effect_on_leg(leg_bearing_deg, wind_speed_mps, wind_direction_deg):
    """
    Calcule l'effet du vent sur un tronçon.
    Retourne: 'type' (face, dos, travers_gauche, travers_droit) et 'effective_speed_mps'.
    """
    if wind_speed_mps is None or wind_direction_deg is None:
        return {'type': 'inconnu', 'effective_speed_mps': 0}

    # Convertir les directions en radians
    leg_bearing_rad = math.radians(leg_bearing_deg)
    # La direction du vent est d'où il vient, donc pour le vecteur vent, on ajoute 180° (ou on soustrait)
    # ou on utilise directement la direction telle quelle et on interprète l'angle relatif.
    # Ici, on calcule l'angle entre la direction du tronçon et la direction D'OÙ VIENT le vent.
    wind_vector_rad = math.radians(wind_direction_deg)

    # Différence d'angle entre le cap du tronçon et la direction du vent
    # Un angle de 0° signifie vent de face.
    # Un angle de 180° signifie vent de dos.
    # Un angle de 90° ou 270° (-90°) signifie vent de travers.
    angle_diff_rad = leg_bearing_rad - wind_vector_rad
    
    # Normaliser l'angle entre -pi et pi (-180 et 180 degrés)
    angle_diff_rad = (angle_diff_rad + math.pi) % (2 * math.pi) - math.pi
    angle_diff_deg = math.degrees(angle_diff_rad)

    # Composante du vent dans l'axe du tronçon (positive si vent de dos, négative si vent de face)
    # effective_speed_mps = wind_speed_mps * math.cos(angle_diff_rad - math.pi) # Si angle_diff est entre cap et vent
    # Ou plus simplement, si angle_diff_rad est l'angle entre la direction du segment et la direction D'OÙ vient le vent:
    # cos(0) = 1 (vent de face, composante = -vitesse_vent)
    # cos(pi) = -1 (vent de dos, composante = +vitesse_vent)
    effective_speed_mps = wind_speed_mps * math.cos(angle_diff_rad) # C'est la composante qui s'oppose (ou aide peu si < 90°)
                                                                    # On veut la composante dans la direction du mouvement.
                                                                    # Si angle_diff est l'angle entre le cap et la direction D'OÙ vient le vent.
                                                                    # Si vent vient de 0°, cap est 0° => angle_diff = 0. Vent de face. Effet = -wind_speed.
                                                                    # Si vent vient de 180°, cap est 0° => angle_diff = -180°. Vent de dos. Effet = +wind_speed.
    
    # La composante du vent qui aide ou freine est -wind_speed * cos(angle entre la direction du segment et la direction *d'où* vient le vent)
    # ou wind_speed * cos(angle entre la direction du segment et la direction *où va* le vent)
    # Si angle_diff est l'angle entre le cap du segment et la direction D'OÙ vient le vent:
    #   0° = vent de face. Cos(0)=1. L'effet est -wind_speed_mps.
    #   180° = vent de dos. Cos(180)=-1. L'effet est +wind_speed_mps.
    #   90° = vent de travers. Cos(90)=0. L'effet sur la vitesse avant est 0.
    # Donc, la vitesse effective du vent qui aide (positive) ou freine (négative) est:
    head_tailwind_component = -wind_speed_mps * math.cos(angle_diff_rad)


    wind_type = "inconnu"
    # Simplification pour type de vent (on peut affiner les angles)
    # angle_diff_deg est l'angle entre le cap du segment et la direction D'OÙ VIENT le vent.
    # Convertissons angle_diff_deg pour qu'il soit entre 0 et 360 pour une interprétation plus simple.
    # Si cap = 0 (Nord), vent vient de 0 (Nord) => angle_diff_deg = 0 => vent de face.
    # Si cap = 0 (Nord), vent vient de 180 (Sud) => angle_diff_deg = -180 (ou +180) => vent de dos.
    # Si cap = 0 (Nord), vent vient de 90 (Est) => angle_diff_deg = -90 => vent de travers droit.
    # Si cap = 0 (Nord), vent vient de 270 (Ouest) => angle_diff_deg = 90 => vent de travers gauche.
    
    # angle_diff_deg est l'angle entre le cap du segment et la direction D'OÙ vient le vent
    # (positif si vent à droite du cap, négatif si vent à gauche du cap)
    # Normalisé entre -180 et 180.
    if -45 < angle_diff_deg <= 45:
        wind_type = "Vent de Face"
    elif 135 < angle_diff_deg <= 180 or -180 <= angle_diff_deg <= -135:
        wind_type = "Vent de Dos"
    elif 45 < angle_diff_deg <= 135:
        wind_type = "Vent de Travers (Gauche)" # Vent vient de la droite du segment (sens de l'aiguille d'une montre)
    elif -135 < angle_diff_deg <= -45:
        wind_type = "Vent de Travers (Droite)" # Vent vient de la gauche du segment
        
    return {'type': wind_type, 'effective_speed_mps': round(head_tailwind_component, 2), 'wind_direction_deg': wind_direction_deg, 'wind_speed_mps': wind_speed_mps}

# ... (imports existants: requests, os, json, load_dotenv, time, polyline, math) ...

def get_bounding_box(latitude, longitude, radius_km):
    """
    Calcule les coordonnées de la bounding box (sud-ouest, nord-est)
    autour d'un point central pour un rayon donné.
    Approximation simple.
    """
    # Conversion approximative: 1 degré de latitude ~= 111.32 km
    # 1 degré de longitude ~= 111.32 km * cos(latitude_en_radians)
    lat_radians = math.radians(latitude)
    
    delta_lat = radius_km / 111.32
    delta_lon = radius_km / (111.32 * math.cos(lat_radians))
    
    sw_lat = latitude - delta_lat
    sw_lon = longitude - delta_lon
    ne_lat = latitude + delta_lat
    ne_lon = longitude + delta_lon
    
    return [sw_lat, sw_lon, ne_lat, ne_lon]

# ... (fonctions existantes, y compris get_bounding_box, decode_strava_polyline, 
#      calculate_bearing, get_wind_data, get_wind_effect_on_leg) ...

# ... (imports et fonctions existantes, y compris get_bounding_box, decode_strava_polyline, 
#      calculate_bearing, get_wind_data, get_wind_effect_on_leg) ...

def find_tailwind_segments_in_area_detailed_wind(center_lat, center_lon, radius_km, 
                                                 access_token, weather_api_key, 
                                                 activity_type="riding",
                                                 min_tailwind_effect_mps=1.0,
                                                 api_call_delay_seconds=0.2): # Petite pause entre les appels API météo
    """
    Scanne les segments dans un rayon donné autour d'un point,
    récupère le vent pour CHAQUE segment, et identifie ceux avec un vent de dos significatif.
    """
    if not access_token:
        print("Erreur: Token d'accès Strava requis.")
        return []
    if not weather_api_key:
        print("Erreur: Clé API Météo requise.")
        return []

    # Étape 1: Calculer la bounding box
    bounds_str = ",".join(map(str, get_bounding_box(center_lat, center_lon, radius_km)))
    print(f"Recherche de segments dans la zone délimitée par : {bounds_str}")

    # Étape 2: Explorer les segments dans la zone via l'API Strava
    # (Le vent sera récupéré plus tard, pour chaque segment)
    segments_explore_url = f"{BASE_STRAVA_URL}/segments/explore"
    params = {
        'bounds': bounds_str,
        'activity_type': activity_type
    }
    
    print("\nExploration des segments Strava dans la zone...")
    explore_result = _make_strava_api_request("segments/explore", access_token, params=params)
    
    if not explore_result or 'segments' not in explore_result:
        print("Aucun segment trouvé dans la zone ou erreur lors de l'exploration.")
        return []

    found_segments_summaries = explore_result['segments'] # Liste d'ExplorerSegment
    print(f"{len(found_segments_summaries)} segments trouvés dans la zone par l'API Strava.")
    
    tailwind_segments = []

    # Étape 3 & 4: Analyser chaque segment trouvé, en récupérant le vent pour chacun
    print("\nAnalyse des segments pour le vent de dos (avec météo par segment)...")
    for i, segment_summary in enumerate(found_segments_summaries):
        segment_id = segment_summary.get('id')
        segment_name = segment_summary.get('name')
        encoded_polyline = segment_summary.get('points')
        start_latlng = segment_summary.get('start_latlng') # [latitude, longitude]

        print(f"  Analyse du segment {i+1}/{len(found_segments_summaries)}: '{segment_name}' (ID: {segment_id})")

        if not start_latlng or len(start_latlng) != 2:
            print(f"    Coordonnées de départ manquantes ou invalides pour le segment '{segment_name}', skipping.")
            continue
            
        segment_start_lat, segment_start_lon = start_latlng[0], start_latlng[1]

        # Récupérer les données de vent pour le point de départ de CE segment
        # print(f"    Récupération du vent pour les coordonnées du segment: ({segment_start_lat:.2f}, {segment_start_lon:.2f})")
        wind_data_for_segment = get_wind_data(segment_start_lat, segment_start_lon, weather_api_key)
        
        if not wind_data_for_segment or wind_data_for_segment.get('speed') is None or wind_data_for_segment.get('deg') is None:
            print(f"    Impossible de récupérer les données de vent pour le segment '{segment_name}'. Skipping.")
            if i < len(found_segments_summaries) - 1 : # Si ce n'est pas le dernier segment
                time.sleep(api_call_delay_seconds) # Petite pause avant le prochain appel météo
            continue
        
        current_wind_speed = wind_data_for_segment['speed']
        current_wind_direction = wind_data_for_segment['deg']
        # print(f"    Vent pour ce segment: {current_wind_speed:.2f} m/s venant de {current_wind_direction}°")

        if not encoded_polyline:
            print(f"    Pas de polyligne pour le segment '{segment_name}', skipping wind effect analysis.")
            if i < len(found_segments_summaries) - 1 :
                time.sleep(api_call_delay_seconds)
            continue
            
        coordinates = decode_strava_polyline(encoded_polyline)
        
        if coordinates and len(coordinates) >= 2:
            first_point = coordinates[0] # Devrait être proche de start_latlng
            last_point = coordinates[-1]
            segment_bearing = calculate_bearing(first_point[0], first_point[1], last_point[0], last_point[1])
            
            wind_effect = get_wind_effect_on_leg(segment_bearing, current_wind_speed, current_wind_direction)
            
            if wind_effect['type'] == "Vent de Dos" and wind_effect['effective_speed_mps'] >= min_tailwind_effect_mps:
                tailwind_segments.append({
                    'id': segment_id,
                    'name': segment_name,
                    'distance': segment_summary.get('distance'),
                    'avg_grade': segment_summary.get('avg_grade'),
                    'climb_category_desc': segment_summary.get('climb_category_desc'),
                    'bearing': round(segment_bearing, 2),
                    'wind_at_segment': { # Ajout des infos de vent spécifiques au segment
                        'speed_mps': current_wind_speed,
                        'direction_deg': current_wind_direction,
                        'speed_kmh': round(current_wind_speed * 3.6, 2)
                    },
                    'wind_effect_type': wind_effect['type'], # Renommé pour clarté
                    'wind_effect_mps': wind_effect['effective_speed_mps'],
                    'wind_effect_kmh': round(wind_effect['effective_speed_mps'] * 3.6, 2)
                })
                print(f"    -> VENT DE DOS TROUVÉ pour '{segment_name}' (Effet: {wind_effect['effective_speed_mps']:.2f} m/s)")
        else:
            print(f"    Polyligne invalide ou trop courte pour le segment '{segment_name}', skipping wind effect analysis.")
        
        # Petite pause pour être gentil avec l'API météo, surtout si on fait plusieurs appels
        if i < len(found_segments_summaries) - 1 :
             time.sleep(api_call_delay_seconds) # Ex: 0.2 secondes
            
    return tailwind_segments


# --- Exemple d'utilisation (à mettre dans un if __name__ == '__main__':) ---
if __name__ == '__main__':
    # Charger le token d'accès (assure-toi que ACCESS_TOKEN est défini globalement dans le module
    # ou passe-le en argument aux fonctions si tu préfères une portée plus locale)
    if not ACCESS_TOKEN:
        print("Le token d'accès MY_NEW_STRAVA_ACCESS_TOKEN n'est pas défini dans .env. Veuillez le configurer.")
    else:
        print("Token d'accès chargé. Début des opérations...")

        # 1. OPTIONNEL: Récupérer les segments d'une activité spécifique (si tu veux tester cette fonction)
        # Tu devras remplacer '0' par un véritable ID d'activité de ton compte.
        # sample_activity_id_for_segments = 0 
        # if sample_activity_id_for_segments != 0:
        #     print(f"\n--- Test de get_segments_from_activity pour l'activité ID: {sample_activity_id_for_segments} ---")
        #     segments_in_activity = get_segments_from_activity(sample_activity_id_for_segments, ACCESS_TOKEN)
        #     if segments_in_activity:
        #         print(f"Segments trouvés dans l'activité {sample_activity_id_for_segments}:")
        #         for i, seg in enumerate(segments_in_activity[:3]): # Affiche les 3 premiers
        #             print(f"  {i+1}. {seg.get('name')} (ID: {seg.get('id')})")
        #     else:
        #         print(f"Aucun segment trouvé pour l'activité {sample_activity_id_for_segments} ou l'activité n'a pas pu être chargée.")
        # else:
        #     print("\nSkipping get_segments_from_activity test (sample_activity_id_for_segments est à 0).")


        # 2. Récupérer tous les segments favoris de l'utilisateur pour en choisir un pour l'analyse détaillée
        print("\n--- Récupération des segments favoris pour sélectionner un échantillon ---")
        # Pour un test rapide, on peut limiter le nombre de pages ou d'éléments par page ici.
        # Pour tout récupérer, la fonction get_all_starred_segments s'en charge.
        all_favorites = get_all_starred_segments(ACCESS_TOKEN, per_page=10) # Récupère plus vite pour le test
        
        sample_segment_id_to_detail = None
        segment_name_for_analysis = "segment inconnu"
        encoded_polyline_from_details = None
        coordinates_from_polyline = None
        detailed_segment_data_for_analysis = None # Pour stocker les détails du segment

        if all_favorites:
            print(f"\n{len(all_favorites)} segments favoris récupérés au total.")
            # Prenons le premier segment favori pour l'analyse détaillée
            first_favorite_segment = all_favorites[0]
            sample_segment_id_to_detail = first_favorite_segment.get('id')
            segment_name_for_analysis = first_favorite_segment.get('name', "segment inconnu")
            print(f"Sélection du segment favori '{segment_name_for_analysis}' (ID: {sample_segment_id_to_detail}) pour l'analyse détaillée.")
        else:
            print("Aucun segment favori trouvé. Veuillez mettre au moins un segment en favori sur Strava pour ce test,")
            print("ou décommentez et fournissez un 'manual_segment_id' ci-dessous.")
            # Décommente et remplace par un ID de segment valide si tu n'as pas de favoris :
            # sample_segment_id_to_detail = 1234567 # <--- ID DE SEGMENT MANUEL ICI
            # segment_name_for_analysis = "Segment manuel"


        # 3. Récupérer les détails du segment sélectionné
        if sample_segment_id_to_detail:
            print(f"\n--- Récupération des détails complets pour le segment ID: {sample_segment_id_to_detail} ('{segment_name_for_analysis}') ---")
            detailed_segment_data_for_analysis = get_segment_details(sample_segment_id_to_detail, ACCESS_TOKEN)
            
            if detailed_segment_data_for_analysis:
                # Affichage de quelques détails (tu peux commenter si c'est trop verbeux)
                print(f"  Nom: {detailed_segment_data_for_analysis.get('name')}")
                print(f"  Distance: {detailed_segment_data_for_analysis.get('distance')} m, Pente moyenne: {detailed_segment_data_for_analysis.get('average_grade')}%")
                
                if detailed_segment_data_for_analysis.get('map') and detailed_segment_data_for_analysis.get('map').get('polyline'):
                    encoded_polyline_from_details = detailed_segment_data_for_analysis.get('map').get('polyline')
                    print(f"  Polyligne encodée trouvée: {encoded_polyline_from_details[:50]}...")
                else:
                    print("  Aucune polyligne trouvée dans les détails de ce segment.")
            else:
                print(f"Impossible de récupérer les détails pour le segment ID: {sample_segment_id_to_detail}")
        else:
            print("\nAucun ID de segment sélectionné pour l'analyse détaillée.")


        # 4. Décoder la polyligne du segment (si obtenue)
        if encoded_polyline_from_details:
            print(f"\n--- Décodage de la polyligne pour '{segment_name_for_analysis}' ---")
            coordinates_from_polyline = decode_strava_polyline(encoded_polyline_from_details)
            if coordinates_from_polyline:
                print("Quelques points décodés (latitude, longitude) :")
                for i, coord in enumerate(coordinates_from_polyline[:3]): # Les 3 premiers
                    print(f"  Point {i+1}: {coord}")
                if len(coordinates_from_polyline) > 6:
                    print("  ...")
                    for i, coord in enumerate(coordinates_from_polyline[-3:]): # Les 3 derniers
                        print(f"  Point {len(coordinates_from_polyline) - 3 + i +1}: {coord}")
                elif len(coordinates_from_polyline) > 3:
                     for i, coord in enumerate(coordinates_from_polyline[3:]):
                        print(f"  Point {3 + i +1}: {coord}")
        else:
            print(f"\nAucune polyligne à décoder pour le segment '{segment_name_for_analysis}'.")


        # 5. Calculer l'orientation du segment (si les coordonnées ont été décodées)
        if coordinates_from_polyline and len(coordinates_from_polyline) >= 2:
            first_point = coordinates_from_polyline[0]
            last_point = coordinates_from_polyline[-1]
            
            print(f"\n--- Calcul de l'orientation pour le segment '{segment_name_for_analysis}' ---")
            print(f"  Utilisation du point de départ: {first_point} et du point d'arrivée: {last_point}")
            
            bearing = calculate_bearing(first_point[0], first_point[1], last_point[0], last_point[1])
            print(f"  Orientation (cap) approximative du segment: {bearing:.2f}° (par rapport au Nord).")
            
            if 337.5 <= bearing or bearing < 22.5: direction = "Nord (N)"
            elif 22.5 <= bearing < 67.5: direction = "Nord-Est (NE)"
            elif 67.5 <= bearing < 112.5: direction = "Est (E)"
            elif 112.5 <= bearing < 157.5: direction = "Sud-Est (SE)"
            elif 157.5 <= bearing < 202.5: direction = "Sud (S)"
            elif 202.5 <= bearing < 247.5: direction = "Sud-Ouest (SO)"
            elif 247.5 <= bearing < 292.5: direction = "Ouest (O)"
            else: direction = "Nord-Ouest (NO)" # 292.5 <= bearing < 337.5
            print(f"  Cela correspond à une direction générale : {direction}")
        elif coordinates_from_polyline: # A des coordonnées mais moins de 2 points
             print("\nPolyligne décodée avec moins de 2 points, impossible de calculer l'orientation.")
        else:
            print(f"\nPas de coordonnées décodées pour le segment '{segment_name_for_analysis}', impossible de calculer l'orientation.")
            
        print("\n--- Fin des tests dans if __name__ == '__main__' ---")
        # ... (code existant dans if __name__ == '__main__': qui définit 'coordinates_from_polyline' et 'segment_name_for_analysis')

        # 6. Décomposer le segment en tronçons orientés (si les coordonnées ont été décodées)
        if 'coordinates_from_polyline' in locals() and coordinates_from_polyline and len(coordinates_from_polyline) >= 2:
            print(f"\n--- Analyse des tronçons pour le segment '{segment_name_for_analysis}' ---")
            # Ajuste les paramètres ci-dessous selon tes préférences:
            # min_points_for_bearing: combien de points pour définir un cap (plus c'est élevé, plus c'est lissé)
            # angle_change_threshold_degrees: seuil de changement d'angle pour un nouveau tronçon
            # min_leg_distance_meters: distance minimale pour un tronçon
            segment_legs = get_segment_leg_orientations(
                coordinates_from_polyline,
                min_points_for_bearing=3,       # Un cap basé sur au moins 3 points (donc 2 segments de polyligne)
                angle_change_threshold_degrees=25.0, # Changement de cap de 25° pour un nouveau tronçon
                min_leg_distance_meters=100.0     # Tronçon d'au moins 100m
            )
            
            if segment_legs:
                print(f"Le segment a été décomposé en {len(segment_legs)} tronçon(s) principal(aux):")
                for i, leg in enumerate(segment_legs):
                    # Interprétation simple du cap pour chaque tronçon
                    if 337.5 <= leg['bearing_deg'] or leg['bearing_deg'] < 22.5: direction = "Nord (N)"
                    elif 22.5 <= leg['bearing_deg'] < 67.5: direction = "Nord-Est (NE)"
                    elif 67.5 <= leg['bearing_deg'] < 112.5: direction = "Est (E)"
                    elif 112.5 <= leg['bearing_deg'] < 157.5: direction = "Sud-Est (SE)"
                    elif 157.5 <= leg['bearing_deg'] < 202.5: direction = "Sud (S)"
                    elif 202.5 <= leg['bearing_deg'] < 247.5: direction = "Sud-Ouest (SO)"
                    elif 247.5 <= leg['bearing_deg'] < 292.5: direction = "Ouest (O)"
                    else: direction = "Nord-Ouest (NO)"
                    
                    print(f"  Tronçon {i+1}: Distance={leg['distance_m']}m, Cap={leg['bearing_deg']}° ({direction}), {leg['num_points']} points GPS")
            else:
                print("Impossible de décomposer le segment en tronçons significatifs avec les paramètres actuels.")
        
        # ... (print("\n--- Fin des tests dans if __name__ == '__main__' ---")) à la fin
        # ... (après l'affichage des tronçons dans if __name__ == '__main__':)

        # 7. Analyser l'effet du vent sur les tronçons (si on a des coordonnées et une clé API Météo)
        if 'coordinates_from_polyline' in locals() and coordinates_from_polyline and OPENWEATHERMAP_API_KEY and segment_legs:
            # Prenons le point de départ du premier tronçon pour la météo globale du segment
            # Pour plus de précision, on pourrait prendre le milieu de chaque tronçon ou faire plusieurs appels.
            lat_for_weather = segment_legs[0]['start_coord'][0]
            lon_for_weather = segment_legs[0]['start_coord'][1]
            
            print(f"\n--- Analyse du Vent pour le segment '{segment_name_for_analysis}' (Météo à {lat_for_weather:.2f}, {lon_for_weather:.2f}) ---")
            current_wind_data = get_wind_data(lat_for_weather, lon_for_weather, OPENWEATHERMAP_API_KEY)
            
            if current_wind_data:
                print(f"Données de vent actuelles: Vitesse={current_wind_data['speed']:.2f} m/s ({current_wind_data['speed']*3.6:.2f} km/h), Direction={current_wind_data['deg']}° (d'où il vient)")
                if current_wind_data.get('gust'):
                     print(f"  Rafales jusqu'à: {current_wind_data['gust']:.2f} m/s ({current_wind_data['gust']*3.6:.2f} km/h)")

                print("\nEffet du vent par tronçon :")
                for i, leg in enumerate(segment_legs):
                    wind_effect = get_wind_effect_on_leg(leg['bearing_deg'], current_wind_data['speed'], current_wind_data['deg'])
                    print(f"  Tronçon {i+1} (Cap {leg['bearing_deg']}°): Type Vent = {wind_effect['type']}, Vitesse Effective Vent = {wind_effect['effective_speed_mps']:.2f} m/s ({wind_effect['effective_speed_mps']*3.6:.2f} km/h)")
            else:
                print("Impossible de récupérer les données de vent pour le moment.")
        elif not OPENWEATHERMAP_API_KEY:
            print("\nClé API OpenWeatherMap (OPENWEATHERMAP_API_KEY) non configurée dans .env. Skipping wind analysis.")
        
        # ... (print("\n--- Fin des tests dans if __name__ == '__main__' ---"))
        # ... (à la fin de if __name__ == '__main__':, après les tests existants)

        # 8. Trouver les segments avec vent de dos dans une zone donnée
        print("\n--- Test de la recherche de segments avec vent de dos ---")
        # Utilise des coordonnées pour Questembert, Bretagne, France comme exemple
        # Ou un autre lieu de ton choix.
        user_lat = 47.7626  # Latitude de Questembert (approximative)
        user_lon = -2.4500 # Longitude de Questembert (approximative)
        search_radius_km = 15.0 # Rayon de recherche
        
        # Seuil pour considérer un vent de dos comme "significatif"
        # Par exemple, un vent qui te "pousse" avec au moins 0.5 m/s (1.8 km/h)
        min_tailwind_threshold = 0.5 

        if ACCESS_TOKEN and OPENWEATHERMAP_API_KEY:
            favorable_segments = find_tailwind_segments_in_area_detailed_wind( # <--- APPEL À LA NOUVELLE FONCTION
                user_lat, user_lon, search_radius_km,
                ACCESS_TOKEN, OPENWEATHERMAP_API_KEY,
                activity_type="riding",
                min_tailwind_effect_mps=min_tailwind_threshold,
                api_call_delay_seconds=0.3 # Tu peux ajuster cette pause
            )
            
            if favorable_segments:
                print(f"\nSegments trouvés avec un vent de dos d'au moins {min_tailwind_threshold} m/s autour de ({user_lat}, {user_lon}) (avec météo par segment):")
                for i, seg in enumerate(favorable_segments):
                    print(f"  {i+1}. {seg['name']} (ID: {seg['id']})")
                    print(f"     Distance: {seg['distance']:.0f}m, Pente: {seg['avg_grade']:.1f}%, Cap: {seg['bearing']}°")
                    print(f"     Vent au segment: {seg['wind_at_segment']['speed_kmh']:.2f} km/h de {seg['wind_at_segment']['direction_deg']}°")
                    print(f"     Effet du Vent: +{seg['wind_effect_mps']:.2f} m/s (+{seg['wind_effect_kmh']:.2f} km/h)")
            else:
                print(f"\nAucun segment trouvé avec un vent de dos significatif dans la zone pour le moment (avec météo par segment).")
        else:
            print("\nToken Strava ou Clé API OpenWeatherMap manquants. Impossible de rechercher les segments avec vent favorable.")

        print("\n--- Fin des tests dans if __name__ == '__main__' ---")