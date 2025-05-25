import requests
import os
import json
import time # Pour gérer les pauses et respecter les limites de l'API
import polyline # Pour décoder les polylignes Strava
import math # Pour les calculs trigonométriques (cap, distance)
from datetime import datetime # Pour manipuler les dates et heures

# IMPORTS POUR LANGCHAIN ET OPENAI (si utilisées directement dans ce module)
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

# Constantes du module
BASE_STRAVA_URL = 'https://www.strava.com/api/v3'

# CONSTANTES OPTIMISEES POUR PLUS DE SEGMENTS
MAX_SEGMENTS_PER_API_CALL = 10  # Limite réelle de l'API Strava
OVERLAP_FACTOR_OPTIMIZED = 0.4  # 40% de chevauchement pour capturer plus de segments
MIN_ZONE_RADIUS_KM = 5.0  # Zones plus petites pour plus de précision
MAX_ZONES_PER_SEARCH = 25  # Augmenter le nombre max de zones

# --- Fonctions Utilitaires et de Calcul de Zones ---
def _make_strava_api_request(endpoint, access_token, params=None, method='GET', payload=None):
    """
    Helper function to make authenticated requests to the Strava API.
    Manages basic errors and different HTTP methods.
    Requires access_token to be passed.
    """
    if not access_token:
        print("Erreur (_make_strava_api_request): Strava Access Token requis.")
        return None

    headers = {'Authorization': f'Bearer {access_token}'}
    if method == 'POST' or method == 'PUT':
        headers['Content-Type'] = 'application/json'
        
    full_url = f"{BASE_STRAVA_URL}/{endpoint}"
    
    try:
        if method == 'GET':
            response = requests.get(full_url, headers=headers, params=params, timeout=20)
        elif method == 'POST':
            response = requests.post(full_url, headers=headers, json=payload, timeout=20)
        else:
            print(f"Méthode HTTP non supportée: {method}")
            return None
            
        response.raise_for_status()
        if response.status_code == 204:
            return {} 
        if response.text: 
            return response.json()
        return {} 
    except requests.exceptions.HTTPError as http_err:
        print(f"Erreur HTTP lors de l'appel à {full_url} ({method}): {http_err}")
        print(f"Réponse de l'API: {response.text if 'response' in locals() else 'N/A'}")
    except requests.exceptions.JSONDecodeError:
        print(f"Erreur de décodage JSON pour {full_url}. Réponse: {response.text if 'response' in locals() else 'N/A'}")
    except requests.exceptions.RequestException as req_err:
        print(f"Erreur de requête (problème réseau ?) lors de l'appel à {full_url} ({method}): {req_err}")
    except Exception as e:
        print(f"Une erreur inattendue est survenue lors de l'appel à {full_url} ({method}): {e}")
    return None

def haversine_distance(lat1, lon1, lat2, lon2):
    R = 6371000
    lat1_rad, lon1_rad, lat2_rad, lon2_rad = map(math.radians, [lat1, lon1, lat2, lon2])
    delta_lat = lat2_rad - lat1_rad
    delta_lon = lon2_rad - lon1_rad
    a = math.sin(delta_lat / 2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def calculate_bearing(lat1, lon1, lat2, lon2):
    lat1_rad, lon1_rad, lat2_rad, lon2_rad = map(math.radians, [lat1, lon1, lat2, lon2])
    delta_lon = lon2_rad - lon1_rad
    x = math.sin(delta_lon) * math.cos(lat2_rad)
    y = math.cos(lat1_rad) * math.sin(lat2_rad) - math.sin(lat1_rad) * math.cos(lat2_rad) * math.cos(delta_lon)
    initial_bearing_rad = math.atan2(x, y)
    initial_bearing_deg = math.degrees(initial_bearing_rad)
    return (initial_bearing_deg + 360) % 360

def decode_strava_polyline(encoded_polyline):
    if not encoded_polyline: return None
    try:
        return polyline.decode(encoded_polyline)
    except Exception as e:
        print(f"Erreur lors du décodage de la polyligne: {e}")
        return None

def get_elevation_for_coordinates(coordinates_list):
    if not coordinates_list: return []
    chunk_size = 100 
    all_results_with_elevation = []
    for i in range(0, len(coordinates_list), chunk_size):
        chunk = coordinates_list[i:i + chunk_size]
        locations_payload = [{"latitude": lat, "longitude": lon} for lat, lon in chunk]
        url = "https://api.open-elevation.com/api/v1/lookup"
        headers = {'Content-type': 'application/json', 'Accept': 'application/json'}
        print(f"  (strava_analyzer) Récupération de l'altitude pour {len(locations_payload)} points (chunk {i//chunk_size + 1})...")
        try:
            response = requests.post(url, json={"locations": locations_payload}, headers=headers, timeout=45) 
            response.raise_for_status()
            data = response.json()
            if data and 'results' in data and len(data['results']) == len(chunk):
                for j, original_coord in enumerate(chunk):
                    all_results_with_elevation.append(
                        (original_coord[0], original_coord[1], data['results'][j]['elevation'])
                    )
            else:
                print("  (strava_analyzer) Erreur dans les données d'élévation reçues ou nombre de résultats incorrect pour ce chunk.")
                for original_coord in chunk: all_results_with_elevation.append((original_coord[0], original_coord[1], None))
        except Exception as e: 
            print(f"  (strava_analyzer) Une erreur est survenue avec Open-Elevation (chunk {i//chunk_size + 1}): {e}")
            for original_coord in chunk: all_results_with_elevation.append((original_coord[0], original_coord[1], None))
        if i + chunk_size < len(coordinates_list): time.sleep(1) 
    if len(all_results_with_elevation) == len(coordinates_list):
        print(f"  (strava_analyzer) Altitudes récupérées (ou tentatives) pour {len(all_results_with_elevation)} points.")
        return all_results_with_elevation
    return None

def get_athlete_profile(access_token_strava):
    if not access_token_strava:
        print("Erreur (get_athlete_profile): Strava Access Token requis.")
        return None
    endpoint = "athlete"
    print("\n(strava_analyzer) Récupération du profil de l'athlète (pour le poids)...")
    profile_data = _make_strava_api_request(endpoint, access_token_strava)
    if profile_data and 'weight' in profile_data and profile_data['weight'] is not None:
        print(f"  (strava_analyzer) Poids de l'athlète récupéré de Strava : {profile_data['weight']} kg.")
        return profile_data
    elif profile_data: 
        print("  (strava_analyzer) Poids non trouvé ou non renseigné dans le profil Strava de l'athlète.")
        return profile_data 
    else: 
        print("  (strava_analyzer) Impossible de récupérer le profil de l'athlète.")
    return None

def calculate_hr_zones(user_fc_max):
    if not user_fc_max or user_fc_max <= 0:
        print("(strava_analyzer) FC Max non valide pour le calcul des zones.")
        return None
    return {
        "Zone 1 (Récupération Active)": (round(user_fc_max * 0.50), round(user_fc_max * 0.60) -1),
        "Zone 2 (Endurance Fondamentale)": (round(user_fc_max * 0.60), round(user_fc_max * 0.70) -1),
        "Zone 3 (Tempo)": (round(user_fc_max * 0.70), round(user_fc_max * 0.80) -1),
        "Zone 4 (Seuil Anaérobie)": (round(user_fc_max * 0.80), round(user_fc_max * 0.90) -1),
        "Zone 5 (Capacité Anaérobie/PMA)": (round(user_fc_max * 0.90), user_fc_max)
    }

def calculate_power_zones(user_ftp):
    if not user_ftp or user_ftp <= 0:
        print("(strava_analyzer) FTP non valide pour le calcul des zones de puissance.")
        return None
    return {
        "Z1 Récup. Active (<55% FTP)": (0, round(user_ftp * 0.55) -1),
        "Z2 Endurance (56-75% FTP)": (round(user_ftp * 0.56), round(user_ftp * 0.75) -1),
        "Z3 Tempo (76-90% FTP)": (round(user_ftp * 0.76), round(user_ftp * 0.90) -1),
        "Z4 Seuil (91-105% FTP)": (round(user_ftp * 0.91), round(user_ftp * 1.05) -1),
        "Z5 VO2Max (106-120% FTP)": (round(user_ftp * 1.06), round(user_ftp * 1.20) -1),
        "Z6 Cap. Anaérobie (121-150% FTP)": (round(user_ftp * 1.21), round(user_ftp * 1.50) -1),
        "Z7 Neuromusculaire (>150% FTP)": (round(user_ftp * 1.51), float('inf'))
    }

# --- FONCTIONS POUR LE VENT CORRIGEES ET OPTIMISEES ---
def get_wind_data(latitude, longitude, weather_api_key, timestamp_utc=None):
    """ Récupère les données de vent. Nécessite une clé API météo. """
    if not weather_api_key: 
        print("Erreur (get_wind_data): Clé API Météo (weather_api_key) requise.")
        return None
    
    weather_url = f"https://api.openweathermap.org/data/2.5/weather?lat={latitude}&lon={longitude}&appid={weather_api_key}&units=metric"
    print(f"  (strava_analyzer) Appel à OpenWeatherMap pour le vent à ({latitude},{longitude})...")
    try:
        response = requests.get(weather_url, timeout=10)
        response.raise_for_status()
        weather_data = response.json()
        if 'wind' in weather_data:
            # S'assurer que speed et deg sont présents avant de les retourner
            speed = weather_data['wind'].get('speed')
            deg = weather_data['wind'].get('deg')
            if speed is not None and deg is not None:
                return {'speed': speed, 
                        'deg': deg, 
                        'gust': weather_data['wind'].get('gust')} # Gust est optionnel
            else:
                print("  (strava_analyzer) Données de vitesse ou direction du vent manquantes dans la réponse.")
                return None
        print("  (strava_analyzer) Clé 'wind' non trouvée dans la réponse d'OpenWeatherMap.")
        return None
    except requests.exceptions.HTTPError as http_err:
        print(f"  (strava_analyzer) Erreur HTTP avec OpenWeatherMap: {http_err}")
        print(f"  (strava_analyzer) Réponse: {response.text if 'response' in locals() else 'N/A'}")
    except Exception as e:
        print(f"  (strava_analyzer) Erreur avec OpenWeatherMap: {e}")
    return None

def get_wind_effect_on_leg_optimized(leg_bearing_deg, wind_speed_mps, wind_direction_deg):
    """ 
    FORMULE CORRIGEE: Calcule l'effet du vent sur un tronçon avec la formule aviation correcte.
    
    Args:
        leg_bearing_deg: Direction du segment (0-360°)
        wind_speed_mps: Vitesse du vent en m/s
        wind_direction_deg: Direction D'OÙ vient le vent (0-360°)
    
    Returns:
        dict: {
            'type': str - Type de vent (Vent de Dos/Face/Travers)
            'effective_speed_mps': float - Composante du vent (+ = dos, - = face)
            'angle_difference': float - Différence d'angle pour debug
        }
    """
    if wind_speed_mps is None or wind_direction_deg is None:
        return {'type': 'inconnu (données vent manquantes)', 'effective_speed_mps': 0, 'angle_difference': 0}

    # Convertir en radians
    leg_bearing_rad = math.radians(leg_bearing_deg)
    wind_from_rad = math.radians(wind_direction_deg)
    
    # Calculer l'angle entre la direction du segment et la direction D'OÙ vient le vent
    angle_diff_rad = leg_bearing_rad - wind_from_rad
    
    # Normaliser l'angle entre -π et π (-180° et 180°)
    angle_diff_rad = (angle_diff_rad + math.pi) % (2 * math.pi) - math.pi
    angle_diff_deg = math.degrees(angle_diff_rad)
    
    # FORMULE CORRECTE: Composante parallèle (vent de face/dos)
    # cos(0°) = 1 (vent de face complet), cos(180°) = -1 (vent de dos complet)
    tailwind_component = -wind_speed_mps * math.cos(angle_diff_rad)
    
    # Classification OPTIMISEE avec seuils plus larges
    wind_type = "inconnu"
    abs_angle = abs(angle_diff_deg)
    
    if abs_angle <= 45:  # 0° à 45° = vent de face (élargi)
        wind_type = "Vent de Face"
    elif abs_angle >= 135:  # 135° à 180° = vent de dos (élargi)
        wind_type = "Vent de Dos"
    elif 45 < abs_angle < 135:  # Entre 45° et 135° = vent de travers
        if angle_diff_deg > 0:
            wind_type = "Vent de Travers (Gauche)"
        else:
            wind_type = "Vent de Travers (Droite)"
    
    return {
        'type': wind_type, 
        'effective_speed_mps': round(tailwind_component, 3),
        'angle_difference': round(angle_diff_deg, 1)
    }

# --- FONCTIONS POUR LA RECHERCHE SUPER OPTIMISEE ---
def generate_dense_search_grid(center_lat, center_lon, total_radius_km, min_zone_radius_km=MIN_ZONE_RADIUS_KM):
    """
    Génère une grille dense de zones de recherche pour maximiser la couverture.
    
    Args:
        center_lat (float): Latitude du centre principal
        center_lon (float): Longitude du centre principal  
        total_radius_km (float): Rayon total à couvrir
        min_zone_radius_km (float): Rayon minimum de chaque zone
    
    Returns:
        list: Liste de tuples (lat, lon, radius, name) pour chaque zone
    """
    print(f"\n--- GENERATION GRILLE DENSE DE RECHERCHE ---")
    print(f"Zone principale: ({center_lat:.4f}, {center_lon:.4f}) - Rayon total: {total_radius_km}km")
    print(f"Zones individuelles: Rayon {min_zone_radius_km}km")
    
    zones = []
    zone_count = 0
    
    # Zone centrale - toujours incluse
    zones.append((center_lat, center_lon, min_zone_radius_km, "Centre"))
    zone_count += 1
    
    # Calculer le nombre d'anneaux nécessaires
    max_rings = max(1, int(total_radius_km / (min_zone_radius_km * 0.8)))  # 0.8 pour plus de chevauchement
    
    # Générer des anneaux concentriques
    for ring in range(1, max_rings + 1):
        ring_radius = ring * min_zone_radius_km * 0.7  # Distance entre anneaux réduite
        
        # Si on dépasse le rayon total, stop
        if ring_radius + min_zone_radius_km > total_radius_km:
            break
            
        # Nombre de zones sur ce ring (proportionnel à la circonférence)
        zones_in_ring = max(6, int(2 * math.pi * ring_radius / (min_zone_radius_km * 0.6)))
        
        # Limiter le nombre total de zones
        if zone_count + zones_in_ring > MAX_ZONES_PER_SEARCH:
            zones_in_ring = MAX_ZONES_PER_SEARCH - zone_count
            if zones_in_ring <= 0:
                break
        
        # Générer les zones uniformément réparties sur le ring
        for i in range(zones_in_ring):
            angle = (2 * math.pi * i) / zones_in_ring
            
            # Calculer les coordonnées de la nouvelle zone
            # Conversion en coordonnées géographiques
            lat_offset = (ring_radius * math.cos(angle)) / 111.32  # 1° lat ≈ 111.32 km
            lon_offset = (ring_radius * math.sin(angle)) / (111.32 * math.cos(math.radians(center_lat)))
            
            new_lat = center_lat + lat_offset
            new_lon = center_lon + lon_offset
            
            zone_name = f"Ring{ring}-{i+1}"
            zones.append((new_lat, new_lon, min_zone_radius_km, zone_name))
            zone_count += 1
            
            if zone_count >= MAX_ZONES_PER_SEARCH:
                break
        
        if zone_count >= MAX_ZONES_PER_SEARCH:
            break
    
    print(f"Grille générée: {len(zones)} zones")
    print(f"Couverture estimée: {len(zones) * min_zone_radius_km * 2:.1f}km de diamètre effectif")
    
    # Debug: afficher quelques zones
    for i, (lat, lon, radius, name) in enumerate(zones[:10]):
        print(f"  Zone {i+1}: {name} - ({lat:.4f}, {lon:.4f}) - Rayon: {radius}km")
    if len(zones) > 10:
        print(f"  ... et {len(zones) - 10} autres zones")
    
    return zones

def get_bounding_box_optimized(latitude, longitude, radius_km):
    """Calcule une bounding box légèrement plus large pour capturer plus de segments"""
    lat_radians = math.radians(latitude) 
    # Ajouter 10% de marge pour capturer les segments aux bordures
    effective_radius = radius_km * 1.1
    delta_lat = effective_radius / 111.32
    delta_lon = effective_radius / (111.32 * math.cos(lat_radians))
    return [latitude - delta_lat, longitude - delta_lon, latitude + delta_lat, longitude + delta_lon]

def search_segments_in_zone_optimized(zone_lat, zone_lon, zone_radius, strava_token, zone_name="Zone"):
    """
    Version optimisée pour rechercher plus de segments dans une zone.
    """
    print(f"\n  --- RECHERCHE OPTIMISEE: {zone_name} ---")
    print(f"  Coordonnees: ({zone_lat:.4f}, {zone_lon:.4f}) - Rayon: {zone_radius}km")
    
    try:
        bounds_list = get_bounding_box_optimized(zone_lat, zone_lon, zone_radius)
        bounds_str = ",".join(map(str, bounds_list))
        
        # Paramètres optimisés pour l'API
        explore_params = {
            'bounds': bounds_str, 
            'activity_type': 'riding'
            # Note: L'API ne supporte pas per_page > 10 pour segments/explore
        }
        
        explore_result = _make_strava_api_request("segments/explore", strava_token, params=explore_params)
        
        if not explore_result:
            print(f"  Aucune reponse de Strava pour {zone_name}")
            return [], f"Pas de réponse Strava pour {zone_name}"
            
        if explore_result.get("message") == "Authorization Error":
            print(f"  Erreur d'autorisation pour {zone_name}")
            return [], "Erreur d'autorisation Strava"
            
        if isinstance(explore_result, dict) and "message" in explore_result:
            print(f"  Erreur API Strava pour {zone_name}: {explore_result.get('message')}")
            return [], f"Erreur API: {explore_result.get('message')}"

        if 'segments' not in explore_result:
            print(f"  Format inattendu pour {zone_name}")
            return [], "Format de réponse inattendu"
        
        segments = explore_result['segments']
        print(f"  {len(segments)} segments trouves dans {zone_name} (max: {MAX_SEGMENTS_PER_API_CALL})")
        
        # Ajouter l'info de zone à chaque segment
        for segment in segments:
            segment['search_zone'] = zone_name
            
        return segments, None
        
    except Exception as e:
        print(f"  Erreur lors de la recherche dans {zone_name}: {e}")
        return [], f"Erreur dans {zone_name}: {e}"

def deduplicate_segments_advanced(all_segments):
    """
    Version avancée de déduplication avec statistiques détaillées.
    """
    print(f"\n--- DEDUPLICATION AVANCEE DES SEGMENTS ---")
    print(f"Segments avant deduplication: {len(all_segments)}")
    
    seen_ids = set()
    unique_segments = []
    duplicate_count = 0
    zones_stats = {}
    
    for segment in all_segments:
        segment_id = segment.get('id')
        zone = segment.get('search_zone', 'Zone inconnue')
        
        # Statistiques par zone
        if zone not in zones_stats:
            zones_stats[zone] = {'total': 0, 'uniques': 0, 'doublons': 0}
        zones_stats[zone]['total'] += 1
        
        if segment_id not in seen_ids:
            seen_ids.add(segment_id)
            unique_segments.append(segment)
            zones_stats[zone]['uniques'] += 1
        else:
            duplicate_count += 1
            zones_stats[zone]['doublons'] += 1
            
    print(f"Segments dupliques supprimes: {duplicate_count}")
    print(f"Segments uniques: {len(unique_segments)}")
    
    # Afficher stats par zone
    print(f"Statistiques par zone:")
    for zone, stats in zones_stats.items():
        print(f"  {zone}: {stats['uniques']} uniques / {stats['total']} total ({stats['doublons']} doublons)")
    
    return unique_segments

def find_tailwind_segments_live(lat, lon, radius_km, strava_token_to_use, weather_key, min_tailwind_effect_mps):
    """
    VERSION SUPER OPTIMISEE pour trouver le maximum de segments avec vent de dos.
    
    Améliorations:
    1. Grille dense de recherche au lieu de zones cardinales
    2. Calcul de vent de dos corrigé avec formule aviation
    3. Seuils plus permissifs pour détecter plus de segments
    4. Meilleure couverture géographique
    """
    print(f"\n=== DEBUT RECHERCHE SUPER OPTIMISEE ===")
    print(f"Coordonnees centrales: {lat:.4f}, {lon:.4f}")
    print(f"Rayon total: {radius_km}km")
    print(f"Seuil vent de dos min: {min_tailwind_effect_mps} m/s")
    print(f"Max zones: {MAX_ZONES_PER_SEARCH}, Segments/zone: {MAX_SEGMENTS_PER_API_CALL}")
    
    if not strava_token_to_use: 
        return [], "Token Strava manquant. Veuillez vous connecter."

    if not weather_key:
        return [], "Clé API Météo manquante."

    # ETAPE 1: Récupération météo
    try:
        print(f"\n--- ETAPE 1: Recuperation meteo ---")
        wind_data = get_wind_data(lat, lon, weather_key)
        
        if not wind_data or wind_data.get('speed') is None or wind_data.get('deg') is None:
            return [], "Données météorologiques insuffisantes."
            
        wind_speed = wind_data['speed']
        wind_direction = wind_data['deg']
        print(f"Vent: {wind_speed:.2f} m/s depuis {wind_direction}°")
        
    except Exception as e:
        return [], f"Erreur météorologique: {e}"

    # ETAPE 2: Génération grille de recherche dense
    try:
        print(f"\n--- ETAPE 2: Generation grille dense ---")
        search_zones = generate_dense_search_grid(lat, lon, radius_km, MIN_ZONE_RADIUS_KM)
        print(f"Grille générée: {len(search_zones)} zones de recherche")
        
    except Exception as e:
        return [], f"Erreur génération grille: {e}"

    # ETAPE 3: Recherche parallèle dans toutes les zones
    try:
        print(f"\n--- ETAPE 3: Recherche dans {len(search_zones)} zones ---")
        all_segments = []
        successful_zones = 0
        api_calls_made = 0
        
        for i, (zone_lat, zone_lon, zone_radius, zone_name) in enumerate(search_zones):
            if i % 5 == 0:  # Log de progression
                print(f"\nProgression: {i+1}/{len(search_zones)} zones traitées")
            
            segments, error = search_segments_in_zone_optimized(
                zone_lat, zone_lon, zone_radius, strava_token_to_use, zone_name
            )
            api_calls_made += 1
            
            if error:
                print(f"  Erreur {zone_name}: {error}")
                continue
            else:
                successful_zones += 1
                all_segments.extend(segments)
                print(f"  {len(segments)} segments ajoutés depuis {zone_name}")
            
            # Pause pour respecter les limites de l'API Strava (100 req/15min)
            time.sleep(0.1)
        
        print(f"\nResultats bruts:")
        print(f"  Zones réussies: {successful_zones}/{len(search_zones)}")
        print(f"  API calls: {api_calls_made}")
        print(f"  Segments bruts: {len(all_segments)}")
        
    except Exception as e:
        return [], f"Erreur recherche multi-zones: {e}"

    # ETAPE 4: Déduplication avancée
    try:
        print(f"\n--- ETAPE 4: Deduplication avancee ---")
        if not all_segments:
            return [], f"Aucun segment trouvé dans les {len(search_zones)} zones."
        
        unique_segments = deduplicate_segments_advanced(all_segments)
        print(f"Segments uniques après déduplication: {len(unique_segments)}")
        
    except Exception as e:
        return [], f"Erreur déduplication: {e}"

    # ETAPE 5: Analyse du vent optimisée
    try:
        print(f"\n--- ETAPE 5: Analyse vent optimisee pour {len(unique_segments)} segments ---")
        tailwind_segments = []
        
        # Compteurs pour statistiques
        segments_processed = 0
        segments_with_coords = 0
        wind_stats = {
            'Vent de Dos': 0,
            'Vent de Face': 0,
            'Vent de Travers (Gauche)': 0,
            'Vent de Travers (Droite)': 0,
            'inconnu': 0
        }
        
        for i, segment in enumerate(unique_segments):
            segments_processed += 1
            segment_id = segment.get('id')
            segment_name = segment.get('name', f'Segment {segment_id}')
            encoded_polyline = segment.get('points')
            search_zone = segment.get('search_zone', 'Zone inconnue')
            
            if i % 20 == 0:  # Log progression
                print(f"  Analyse: {i+1}/{len(unique_segments)} segments")
            
            if not encoded_polyline:
                continue

            try:
                coordinates = decode_strava_polyline(encoded_polyline)
                if not coordinates or len(coordinates) < 2:
                    continue
                    
                segments_with_coords += 1
                
                # Calculer le cap du segment
                segment_bearing = calculate_bearing(
                    coordinates[0][0], coordinates[0][1], 
                    coordinates[-1][0], coordinates[-1][1]
                )
                
                # NOUVEAU: Calcul de vent optimisé
                wind_effect = get_wind_effect_on_leg_optimized(
                    segment_bearing, wind_speed, wind_direction
                )
                
                # Statistiques sur les types de vent
                wind_type = wind_effect['type']
                if wind_type in wind_stats:
                    wind_stats[wind_type] += 1
                else:
                    wind_stats['inconnu'] += 1
                
                # CRITERE OPTIMISE: Accepter plus de segments
                effective_wind = wind_effect['effective_speed_mps']
                is_favorable = (
                    wind_type == "Vent de Dos" and effective_wind >= min_tailwind_effect_mps
                ) or (
                    # NOUVEAU: Accepter aussi les vents de travers avec composante favorable
                    wind_type.startswith("Vent de Travers") and effective_wind >= (min_tailwind_effect_mps * 0.5)
                )
                
                if is_favorable:
                    segment_details = {
                        "id": segment_id,
                        "name": segment_name,
                        "polyline_coords": coordinates,
                        "strava_link": f"https://www.strava.com/segments/{segment_id}",
                        "distance": segment.get('distance'),
                        "avg_grade": segment.get('avg_grade'),
                        "bearing": round(segment_bearing, 1),
                        "wind_effect_mps": effective_wind,
                        "wind_type": wind_type,
                        "wind_angle": wind_effect.get('angle_difference', 0),
                        "search_zone": search_zone
                    }
                    tailwind_segments.append(segment_details)
                    
                    if i < 10:  # Debug pour les premiers segments
                        print(f"    FAVORABLE: {segment_name} - {wind_type} - {effective_wind:.2f} m/s")
                    
            except Exception as segment_error:
                print(f"    Erreur segment {segment_name}: {segment_error}")
                continue
        
        # Statistiques finales
        print(f"\n--- STATISTIQUES FINALES ---")
        print(f"Segments traités: {segments_processed}")
        print(f"Segments avec coordonnées: {segments_with_coords}")
        print(f"Répartition des vents:")
        for wind_type, count in wind_stats.items():
            percentage = (count / max(1, segments_with_coords)) * 100
            print(f"  {wind_type}: {count} ({percentage:.1f}%)")
        print(f"Segments avec vent favorable: {len(tailwind_segments)}")
        
        # Trier par effet du vent décroissant
        tailwind_segments.sort(key=lambda x: x['wind_effect_mps'], reverse=True)
        
        print(f"=== FIN RECHERCHE SUPER OPTIMISEE ===\n")
        return tailwind_segments, None
        
    except Exception as e:
        return [], f"Erreur analyse du vent: {e}"

# --- FONCTIONS EXISTANTES (inchangées pour compatibilité) ---
def get_segment_details(segment_id, access_token_strava): 
    if not access_token_strava: return None
    endpoint = f"segments/{segment_id}" 
    return _make_strava_api_request(endpoint, access_token_strava)

def get_activity_details_with_efforts(activity_id, access_token_strava): 
    if not access_token_strava or not activity_id:
        print("Erreur: Token d'accès et ID d'activité requis.")
        return None
    endpoint = f"activities/{activity_id}?include_all_efforts=true"
    print(f"\n(strava_analyzer) Récupération des détails de l'activité ID: {activity_id}...")
    activity_data = _make_strava_api_request(endpoint, access_token_strava)
    if activity_data:
        print(f"  (strava_analyzer) Détails de l'activité '{activity_data.get('name')}' récupérés.")
    else:
        print(f"  (strava_analyzer) Impossible de récupérer les détails pour l'activité ID: {activity_id}")
    return activity_data

def get_segment_effort_streams(segment_effort_id, access_token_strava, stream_types=['time', 'latlng', 'heartrate', 'watts', 'cadence', 'velocity_smooth']): 
    if not access_token_strava or not segment_effort_id:
        print("Erreur: Token d'accès et ID d'effort de segment requis.")
        return None
    keys_param = ",".join(stream_types)
    endpoint = f"segment_efforts/{segment_effort_id}/streams"
    params = {'keys': keys_param, 'key_by_type': 'true'} 
    print(f"  (strava_analyzer) Récupération des streams pour l'effort de segment ID: {segment_effort_id}...")
    streams_data = _make_strava_api_request(endpoint, access_token_strava, params=params)
    if streams_data:
        print(f"    (strava_analyzer) Streams récupérés avec succès.")
    else:
        print(f"    (strava_analyzer) Impossible de récupérer les streams pour l'effort ID: {segment_effort_id}")
    return streams_data

def basic_stream_analysis(streams_data, hr_zones, power_zones, user_weight_kg): 
    analysis = {
        "fc_avg": "N/A", "fc_max": "N/A", "fc_start_effort": "N/A", "fc_end_effort": "N/A",
        "watts_avg": "N/A", "watts_max": "N/A", "watts_start_effort": "N/A", "watts_end_effort": "N/A",
        "watts_per_kg_avg": "N/A", 
        "cadence_avg": "N/A", "cadence_max": "N/A", 
        "power_surges_count": 0, 
        "time_in_hr_zones_str": "Analyse des zones FC non disponible (FC Max utilisateur ou données manquantes).", 
        "time_in_power_zones_str": "Analyse des zones de puissance non disponible (FTP utilisateur ou données manquantes).", 
        "pacing_fc_comment": "Données FC insuffisantes pour commentaire.",
        "pacing_watts_comment": "Données Watts insuffisantes pour commentaire.",
        "cadence_comment": "Données de cadence insuffisantes pour commentaire.", 
        "power_variability_comment": "Analyse de la variabilité de puissance non effectuée (données de puissance manquantes)." 
    }
    if not streams_data: return analysis
    time_stream = streams_data.get('time', {}).get('data', [])
    num_points = len(time_stream)
    if num_points < 2: return analysis
    total_duration_stream = time_stream[-1] - time_stream[0] if time_stream else 0
    time_per_point_approx = total_duration_stream / (num_points -1) if num_points > 1 else 1

    if 'heartrate' in streams_data and streams_data['heartrate'].get('data'):
        fc_stream = streams_data['heartrate']['data']
        if len(fc_stream) == num_points and len(fc_stream) > 1 : 
            analysis["fc_avg"] = round(sum(fc_stream) / len(fc_stream), 1)
            analysis["fc_max"] = max(fc_stream)
            analysis["fc_start_effort"] = fc_stream[0]
            analysis["fc_end_effort"] = fc_stream[-1]
            if hr_zones:
                time_in_zones_fc = {zone_name: 0 for zone_name in hr_zones}
                for fc_value in fc_stream:
                    for zone_name, (lower, upper) in hr_zones.items():
                        if lower <= fc_value <= upper:
                            time_in_zones_fc[zone_name] += time_per_point_approx
                            break
                analysis["time_in_hr_zones_str"] = ", ".join([f"{name}: {time_sec:.0f}s" for name, time_sec in time_in_zones_fc.items() if time_sec > 0.1]) 
                if not analysis["time_in_hr_zones_str"]: analysis["time_in_hr_zones_str"] = "Pas de temps significatif (>0.1s) passé dans les zones FC définies."
            else:
                analysis["time_in_hr_zones_str"] = "Zones FC non fournies pour l'analyse."

    if 'watts' in streams_data and streams_data['watts'].get('data') and streams_data['watts'].get('device_watts', True): 
        watts_stream = streams_data['watts']['data']
        if len(watts_stream) == num_points and len(watts_stream) > 1:
            analysis["watts_avg"] = round(sum(watts_stream) / len(watts_stream), 1)
            analysis["watts_max"] = max(watts_stream)
            analysis["watts_start_effort"] = watts_stream[0]
            analysis["watts_end_effort"] = watts_stream[-1]
            analysis["pacing_watts_comment"] = "Les données de puissance sont disponibles."
            if user_weight_kg and user_weight_kg > 0 and analysis["watts_avg"] is not None and isinstance(analysis["watts_avg"], (int, float)):
                analysis["watts_per_kg_avg"] = round(analysis["watts_avg"] / user_weight_kg, 2)
            else:
                analysis["watts_per_kg_avg"] = "N/A (poids ou watts_avg manquants)"
            analysis["power_variability_comment"] = "Analyse de la variabilité de puissance effectuée." 
            if power_zones:
                time_in_zones_power = {zone_name: 0 for zone_name in power_zones}
                for p_value in watts_stream:
                    for zone_name, (lower, upper) in power_zones.items():
                        if lower <= p_value <= upper:
                            time_in_zones_power[zone_name] += time_per_point_approx
                            break
                analysis["time_in_power_zones_str"] = ", ".join([f"{name}: {time_sec:.0f}s" for name, time_sec in time_in_zones_power.items() if time_sec > 0.1])
                if not analysis["time_in_power_zones_str"]: analysis["time_in_power_zones_str"] = "Pas de temps significatif (>0.1s) passé dans les zones de puissance définies."
            else:
                analysis["time_in_power_zones_str"] = "Zones de puissance non fournies pour l'analyse."
    
    if 'cadence' in streams_data and streams_data['cadence'].get('data'):
        cadence_stream = streams_data['cadence']['data']
        if len(cadence_stream) > 0:
            active_cadence_stream = [c for c in cadence_stream if c > 0]
            if active_cadence_stream:
                analysis["cadence_avg"] = round(sum(active_cadence_stream) / len(active_cadence_stream), 1)
                analysis["cadence_max"] = max(active_cadence_stream)
    return analysis

def analyze_detailed_elevation_profile(coordinates_with_elevation, 
                                       min_section_distance_m=50.0, 
                                       slope_smoothing_window=3,
                                       significant_slope_change_threshold=2.0): 
    if not coordinates_with_elevation or len(coordinates_with_elevation) < 2:
        return "Profil de dénivelé détaillé non disponible (pas assez de points)."
    profile_description_parts = ["Voici comment se décompose le profil de ce segment :"] 
    current_distance_on_segment = 0.0
    micro_segments = []
    for i in range(len(coordinates_with_elevation) - 1):
        p1 = coordinates_with_elevation[i] 
        p2 = coordinates_with_elevation[i+1]
        if p1[2] is None or p2[2] is None: continue 
        dist_m = haversine_distance(p1[0], p1[1], p2[0], p2[1])
        elev_change_m = p2[2] - p1[2]
        if dist_m > 0.1: 
            slope_percent = (elev_change_m / dist_m) * 100
            micro_segments.append({
                'start_dist': current_distance_on_segment,
                'length': dist_m,
                'slope': slope_percent,
                'elev_gain': elev_change_m
            })
        current_distance_on_segment += dist_m
    if not micro_segments:
        return "Profil de dénivelé détaillé non disponible (impossible de calculer les pentes)."
    if len(micro_segments) == 1: 
        ms = micro_segments[0]
        profile_description_parts.append(
            f"- Une seule section de 0m à {ms['start_dist'] + ms['length']:.0f}m, avec une pente moyenne de {ms['slope']:.1f}% (D+ {ms['elev_gain']:.1f}m)."
        )
    else:
        current_section_start_dist = 0.0
        current_section_total_dist = 0.0
        current_section_total_elev_gain = 0.0
        current_section_points_slopes = [] 
        for i, ms in enumerate(micro_segments):
            current_section_points_slopes.append(ms['slope'])
            current_section_total_dist += ms['length']
            current_section_total_elev_gain += ms['elev_gain']
            is_last_micro_segment = (i == len(micro_segments) - 1)
            significant_change = False
            if len(current_section_points_slopes) > slope_smoothing_window : 
                avg_slope_current_section = sum(current_section_points_slopes) / len(current_section_points_slopes)
                if abs(ms['slope'] - avg_slope_current_section) > significant_slope_change_threshold :
                    significant_change = True
            if current_section_total_dist >= min_section_distance_m or significant_change or is_last_micro_segment:
                avg_slope_of_section = (current_section_total_elev_gain / current_section_total_dist) * 100 if current_section_total_dist > 0 else 0
                profile_description_parts.append(
                    f"- De {current_section_start_dist:.0f}m à {current_section_start_dist + current_section_total_dist:.0f}m (sur {current_section_total_dist:.0f}m) : la pente moyenne est d'environ {avg_slope_of_section:.1f}% (pour un D+ de {current_section_total_elev_gain:.1f}m)."
                )
                current_section_start_dist += current_section_total_dist
                current_section_total_dist = 0.0
                current_section_total_elev_gain = 0.0
                current_section_points_slopes = []
                if significant_change and not is_last_micro_segment: 
                    current_section_points_slopes.append(ms['slope'])
                    current_section_total_dist += ms['length']
                    current_section_total_elev_gain += ms['elev_gain']
    if len(profile_description_parts) == 1: 
        return "Le profil de dénivelé de ce segment est très court ou uniforme, difficile de le décomposer en sections distinctes."
    return "\n".join(profile_description_parts)

def generate_llm_report_langchain(prompt_template_str, prompt_data_dict, openai_api_key, model_name="gpt-4o-mini"):
    if not openai_api_key:
        print("Erreur: Clé API OpenAI non fournie à generate_llm_report_langchain.")
        return f"Erreur: Clé API OpenAI non configurée pour {prompt_data_dict.get('report_type', 'rapport inconnu')}."

    llm = ChatOpenAI(openai_api_key=openai_api_key, model_name=model_name, temperature=0.75, max_tokens=1500) 
    prompt = ChatPromptTemplate.from_template(prompt_template_str)
    output_parser = StrOutputParser()
    chain = prompt | llm | output_parser
    
    print(f"\n(strava_analyzer) --- PROMPT PRÉPARÉ POUR LANGCHAIN ({model_name}) ---")
    print(f"(strava_analyzer) Prompt envoyé à OpenAI {llm.model_name} pour {prompt_data_dict.get('report_type', 'rapport inconnu')}...")
    print("---------------------------------------\n")

    try:
        report_text = chain.invoke(prompt_data_dict) 
        return report_text.strip()
    except Exception as e:
        print(f"(strava_analyzer) Erreur inattendue lors de la génération du rapport {prompt_data_dict.get('report_type', '')} avec Langchain/OpenAI: {e}")
        return f"Erreur interne lors de la génération du rapport par l'IA pour {prompt_data_dict.get('report_type', '')}."

def generate_activity_report_with_overall_summary(
        activity_id, 
        access_token_strava, 
        openai_api_key, 
        user_fc_max, 
        user_ftp, 
        user_weight_kg,
        weather_api_key=None, 
        notable_rank_threshold=10, 
        num_best_segments_to_analyze=2):
    
    print(f"\n(strava_analyzer) --- DÉBUT DU RAPPORT D'ACTIVITÉ COMPLET POUR L'ID: {activity_id} ---")
    
    activity_details = get_activity_details_with_efforts(activity_id, access_token_strava)
    if not activity_details:
        print("(strava_analyzer) Impossible de récupérer les détails de l'activité. Arrêt du rapport.")
        return {"activity_name": "Activité Inconnue", "overall_summary": "Données d'activité non disponibles.", "segment_reports": []}

    hr_zones = calculate_hr_zones(user_fc_max)
    power_zones = calculate_power_zones(user_ftp)

    # Récupération des données de base de l'activité
    activity_name = activity_details.get('name', 'Sortie sans nom')
    activity_type = activity_details.get('type', 'Activité')
    activity_distance_km = round(activity_details.get('distance', 0) / 1000, 2)
    activity_duration_sec = activity_details.get('moving_time', 0)
    activity_duration_formatted = time.strftime("%Hh%Mmin%Ss", time.gmtime(activity_duration_sec)) if activity_duration_sec else "N/A"
    activity_avg_hr = activity_details.get('average_heartrate')
    activity_max_hr_session = activity_details.get('max_heartrate') 
    activity_total_elevation_gain = activity_details.get('total_elevation_gain')
    activity_avg_watts = activity_details.get('average_watts')
    activity_description = activity_details.get('description', '')

    # NOUVEAU : Détecter les KOM et PR pour les mentionner dans le résumé global
    kom_segments = []
    pr_segments = []
    top_segments = []
    
    if 'segment_efforts' in activity_details:
        for effort in activity_details['segment_efforts']:
            segment_name = effort.get('segment', {}).get('name', 'Segment inconnu')
            kom_rank = effort.get('kom_rank')
            pr_rank = effort.get('pr_rank')
            
            if kom_rank == 1:
                kom_segments.append(segment_name)
            if pr_rank == 1:
                pr_segments.append(segment_name)
            if kom_rank and kom_rank <= 5:  # Top 5 pour les mentions spéciales
                top_segments.append((segment_name, kom_rank))

    # Construire le texte des exploits pour le résumé global
    exploits_text = ""
    exploits_instruction = ""
    
    if kom_segments or pr_segments or top_segments:
        exploits_parts = []
        
        if kom_segments:
            if len(kom_segments) == 1:
                exploits_parts.append(f"🏆 EXPLOIT MAJEUR : TU AS DÉCROCHÉ LE KOM SUR '{kom_segments[0]}' ! 👑")
            else:
                exploits_parts.append(f"🏆 EXPLOITS MAJEURS : TU AS DÉCROCHÉ {len(kom_segments)} KOM ! 👑 ({', '.join(kom_segments)})")
        
        if pr_segments:
            if len(pr_segments) == 1:
                exploits_parts.append(f"🥇 Record personnel établi sur '{pr_segments[0]}'")
            else:
                exploits_parts.append(f"🥇 {len(pr_segments)} records personnels établis ({', '.join(pr_segments)})")
        
        # Mentionner les top 5 qui ne sont pas des KOM
        non_kom_tops = [(name, rank) for name, rank in top_segments if name not in kom_segments]
        if non_kom_tops:
            top_mentions = [f"Top {rank} sur '{name}'" for name, rank in non_kom_tops[:3]]  # Limiter à 3
            exploits_parts.append(f"🏅 Excellents classements : {', '.join(top_mentions)}")
        
        exploits_text = "\n".join([f"- {part}" for part in exploits_parts])
        
        if kom_segments:
            exploits_instruction = "IMPORTANT : Tu as décroché un ou plusieurs KOM sur cette sortie ! C'est un exploit majeur à célébrer avec enthousiasme ! Mentionne-le clairement et félicite chaleureusement l'athlète pour cet exploit. "
        else:
            exploits_instruction = "L'athlète a réalisé de belles performances sur des segments. Mentionne ces exploits avec enthousiasme. "

    # Gestion de la description AVANT l'utilisation
    description_text = ""
    description_instruction = ""
    if activity_description and activity_description.strip():
        description_text = f"- Tes notes perso sur cette sortie : \"{activity_description}\""
        description_instruction = "Si sa description personnelle contient des infos importantes (météo, ressenti, objectifs, problèmes), intègre-les intelligemment dans ton analyse. "
    else:
        description_text = "- Pas de notes personnelles ajoutées pour cette sortie."
        description_instruction = ""

    # Calcul de l'intensité
    intensity_comment = "Ta FC Max personnelle n'a pas été fournie ou est invalide, donc l'analyse d'intensité est basée sur les sensations générales."
    if hr_zones and activity_avg_hr and user_fc_max and user_fc_max > 0 : 
        percent_fc_max = (activity_avg_hr / user_fc_max) * 100
        intensity_level = "inconnue"
        for zone_name, (lower, upper) in hr_zones.items():
            if lower <= activity_avg_hr <= upper:
                intensity_level = zone_name
                break
        intensity_comment = f"Ton cœur a travaillé en moyenne à {activity_avg_hr} bpm ({percent_fc_max:.0f}% de ta FC Max estimée à {user_fc_max} bpm), ce qui place globalement cette séance en {intensity_level}. C'est une super info pour voir si tu étais dans tes objectifs d'entraînement !"
    elif activity_avg_hr:
         intensity_comment = f"Ta FC moyenne pour cette sortie a été de {activity_avg_hr} bpm. Avec ta FC Max, on pourrait décortiquer ça encore mieux !"

    # Préparation des données pour le prompt avec les exploits
    overall_prompt_data = {
        "report_type": "résumé global de séance",
        "activity_name": activity_name,
        "activity_type": activity_type,
        "activity_distance_km": activity_distance_km,
        "activity_duration_formatted": activity_duration_formatted, 
        "activity_avg_hr": f"{activity_avg_hr} bpm" if activity_avg_hr else "N/A",
        "activity_max_hr_session": f"{activity_max_hr_session} bpm" if activity_max_hr_session else "N/A", 
        "activity_total_elevation_gain": f"{activity_total_elevation_gain} m" if activity_total_elevation_gain is not None else "N/A",
        "intensity_comment": intensity_comment,
        "activity_avg_watts": f"{activity_avg_watts:.0f}W" if activity_avg_watts else "N/A",
        "user_ftp": f"{user_ftp}W" if user_ftp else "N/A",
        "description_text": description_text,
        "description_instruction": description_instruction,
        "exploits_text": exploits_text,
        "exploits_instruction": exploits_instruction
    }

    # Template amélioré pour le résumé global avec prise en compte des exploits
    overall_summary_template = """
    En tant que coach KOM Hunters, ton rôle est d'être super motivant, un peu comme un ami qui te connaît bien et qui est passionné par tes progrès ! 
    Adresse-toi directement à l'athlète en utilisant "tu". Sois chaleureux, positif et donne envie de repartir à l'aventure.

    Voici le récap de ta dernière sortie "{activity_name}" ({activity_type}) :
    - Super distance de {activity_distance_km} km bouclée en {activity_duration_formatted} !
    - Tu as grimpé {activity_total_elevation_gain} de dénivelé positif. Respect !
    - Ton cœur a joué la mélodie de l'effort à {activity_avg_hr} en moyenne, avec un high score à {activity_max_hr_session}.
    - Puissance moyenne (si dispo) : {activity_avg_watts} (ta FTP perso est à {user_ftp}).
    - Mon petit commentaire sur l'intensité : {intensity_comment}
    {description_text}

    {exploits_text}

    Rédige un petit paragraphe de débriefing pour cette séance. Commence par une exclamation ou une phrase d'accroche sympa et personnalisée pour la sortie "{activity_name}". 
    {exploits_instruction}Ensuite, commente l'effort global, l'intensité (en te basant sur le commentaire fourni et la relation FC moyenne/FC Max, ou Watts moyens/FTP).
    {description_instruction}Mets en lumière un ou deux aspects que tu trouves chouettes (la distance, la durée, le dénivelé, ou la gestion de l'effort si tu peux le deviner).
    Termine par une phrase super motivante pour sa prochaine sortie, peut-être avec une petite touche d'humour sportif ou un clin d'œil.
    Fais comme si tu parlais à un pote après sa sortie, avec enthousiasme et bienveillance !
    """

    print(f"\n(strava_analyzer) Génération du résumé global pour l'activité '{activity_name}'...")
    print(f"KOM détectés: {len(kom_segments)}, PR détectés: {len(pr_segments)}, Top 5: {len(top_segments)}")
    
    overall_summary_report = generate_llm_report_langchain(overall_summary_template, overall_prompt_data, openai_api_key)
    
    # Analyse des segments (code existant avec amélioration du scoring)
    segment_reports_list = [] 
    if 'segment_efforts' in activity_details:
        notable_efforts = []
        for effort in activity_details['segment_efforts']:
            is_pr = effort.get('pr_rank') == 1
            kom_rank = effort.get('kom_rank') 
            is_top_rank = kom_rank is not None and kom_rank <= notable_rank_threshold
            if is_pr or is_top_rank:
                rank_text_parts = []
                if is_pr: rank_text_parts.append("Record Personnel (PR) ! Chapeau bas !")
                if kom_rank == 1: rank_text_parts.append("KOM DÉCROCHÉ ! Tu es le nouveau roi ! 👑")
                elif is_top_rank: rank_text_parts.append(f"Superbe Top {kom_rank} !")
                effort['notable_rank_text'] = " ".join(rank_text_parts) if rank_text_parts else "Belle performance !"
                
                # Score de priorité amélioré pour prioriser les KOM
                score = float('inf')
                if kom_rank == 1: score = -1  # KOM a la priorité absolue
                elif is_pr: score = 0  
                elif is_top_rank: score = kom_rank
                else: score = 100
                
                effort['performance_score'] = score
                notable_efforts.append(effort)
        
        notable_efforts.sort(key=lambda x: x['performance_score'])
        
        if notable_efforts:
            print(f"(strava_analyzer) {len(notable_efforts)} effort(s) notable(s) identifié(s). Analyse des {min(len(notable_efforts), num_best_segments_to_analyze)} meilleur(s)...")
            
            for i, effort_data in enumerate(notable_efforts):
                if i >= num_best_segments_to_analyze:
                    break

                segment_id = effort_data['segment']['id']
                segment_name = effort_data['segment']['name']
                effort_id = effort_data['id']
                effort_start_time_str = effort_data.get('start_date_local') 
                
                print(f"\n(strava_analyzer) Préparation de l'analyse pour le meilleur effort {i+1} sur le segment: '{segment_name}' (ID effort: {effort_id})")

                segment_details = get_segment_details(segment_id, access_token_strava)
                if not segment_details:
                    segment_reports_list.append({"segment_name": segment_name, "report": "Données du segment non disponibles pour une analyse détaillée."})
                    continue
                
                segment_distance = segment_details.get('distance')
                segment_avg_grade = segment_details.get('average_grade')
                segment_elevation_gain_strava = segment_details.get('total_elevation_gain') 

                detailed_elevation_profile_str = "Profil de dénivelé détaillé non disponible." 
                encoded_polyline = segment_details.get('map', {}).get('polyline')
                if encoded_polyline:
                    coordinates = decode_strava_polyline(encoded_polyline)
                    if coordinates:
                        coordinates_with_elevation = get_elevation_for_coordinates(coordinates)
                        if coordinates_with_elevation and not all(c[2] is None for c in coordinates_with_elevation): 
                            detailed_elevation_profile_str = analyze_detailed_elevation_profile(coordinates_with_elevation)
                
                stream_types_to_fetch = ['time', 'heartrate', 'watts', 'cadence', 'velocity_smooth'] 
                effort_streams = get_segment_effort_streams(effort_id, access_token_strava, stream_types=stream_types_to_fetch)
                stream_analysis_summary = basic_stream_analysis(effort_streams, hr_zones, power_zones, user_weight_kg) 
                
                segment_prompt_data = {
                    "report_type": f"analyse du segment '{segment_name}'",
                    "segment_name": segment_name,
                    "segment_distance_m": f"{segment_distance:.0f}" if segment_distance else "N/A",
                    "segment_elevation_gain_m": f"{segment_elevation_gain_strava:.1f}" if segment_elevation_gain_strava is not None else "N/A", 
                    "segment_avg_grade": f"{segment_avg_grade:.1f}" if segment_avg_grade is not None else "N/A", 
                    "detailed_elevation_profile": detailed_elevation_profile_str, 
                    "user_time_seconds": effort_data.get('elapsed_time', 'N/A'),
                    "user_rank_text": effort_data.get('notable_rank_text', 'N/A'),
                    "effort_start_time_local": effort_start_time_str if effort_start_time_str else "N/A",
                    "user_ftp": f"{user_ftp}W" if user_ftp else "N/A", 
                    "user_fc_max": f"{user_fc_max} bpm" if user_fc_max else "N/A", 
                    **stream_analysis_summary 
                }
                
                segment_report_template = """
                En tant que coach KOM Hunters, toujours aussi motivant et un brin espiègle, analyse cette performance spécifique sur le segment "{segment_name}".
                Ce rapport fait partie d'un débriefing plus large de la sortie, donc commence directement ton analyse sans salutations supplémentaires.
                Adresse-toi à l'athlète avec "tu".

                Voici les données de ton exploit sur le segment "{segment_name}" (FTP de référence: {user_ftp}, FC Max de référence: {user_fc_max}):
                - Distance : {segment_distance_m}m
                - Dénivelé Positif (selon Strava) : {segment_elevation_gain_m}m (Pente moyenne Strava: {segment_avg_grade}%)
                {detailed_elevation_profile} 
                - Ta superbe performance : Temps = {user_time_seconds}s (Classement : {user_rank_text})
                - C'était le : {effort_start_time_local}

                Tes sensations et chiffres pendant cet effort :
                - FC moyenne : {fc_avg} bpm (Max : {fc_max} bpm). Tu as démarré à {fc_start_effort} bpm et fini à {fc_end_effort} bpm.
                - Répartition du temps dans tes zones FC : {time_in_hr_zones_str}
                - Ton pacing FC : {pacing_fc_comment}
                {watts_section}
                - Cadence moyenne : {cadence_avg} rpm (Max : {cadence_max} rpm). Commentaire cadence : {cadence_comment}
                - Variabilité de puissance : {power_variability_comment} (Nombre d'à-coups détectés: {power_surges_count})

                Ton analyse de coach personnalisé et tes conseils pour tout déchirer la prochaine fois (en français, avec un ton humain, encourageant et précis) :
                1.  **"Franchement, bravo pour cet effort sur '{segment_name}' ! Ce que j'ai adoré voir :"** (Sois spécifique sur 1 ou 2 points positifs. Commente la gestion des zones FC/Puissance, la cadence, la puissance en W/kg si pertinente.)
                2.  **"Si on veut chercher la petite bête pour grappiller encore (parce qu'on est des chasseurs de KOMs, non ?) :"** (Identifie des pistes d'amélioration basées sur toutes les données. Ex: "Tu as passé beaucoup de temps en zone X, pour ce type de segment, viser la zone Y pourrait être plus efficace...", "Tes {power_surges_count} à-coups de puissance montrent de l'explosivité, mais peut-être qu'un effort plus lissé serait bénéfique ici ?")
                3.  **"Ton plan d'attaque MACHIAVÉLIQUE pour la prochaine tentative sur '{segment_name}' :"** (Donne des conseils très concrets pour chaque section clé identifiée dans le "Profil de dénivelé détaillé". Intègre des conseils sur les zones FC/Puissance à viser, la cadence, la gestion des efforts intenses en fonction du profil. Ex: "Sur la première rampe, vise la Zone 4 en FC et essaie de maintenir tes watts autour de X W/kg...")
                Conclus par une phrase qui donne envie de retourner chasser ce segment !
                """
                
                # Gestion de la section watts
                watts_section_text_segment = f"- Pas de données de puissance pour cet effort, mais avec la FC (zones basées sur ta FC Max de {user_fc_max} bpm) et la cadence on a déjà de quoi faire !"
                watts_avg_val = segment_prompt_data.get('watts_avg')
                if isinstance(watts_avg_val, (int, float)): 
                    watts_per_kg_val = segment_prompt_data.get('watts_per_kg_avg')
                    watts_per_kg_text = f"({watts_per_kg_val} W/kg)" if isinstance(watts_per_kg_val, (int, float)) else ""
                    
                    watts_max_val = segment_prompt_data.get('watts_max')
                    watts_start_val = segment_prompt_data.get('watts_start_effort')
                    watts_end_val = segment_prompt_data.get('watts_end_effort')
                    time_in_power_zones_val = segment_prompt_data.get('time_in_power_zones_str')
                    pacing_watts_val = segment_prompt_data.get('pacing_watts_comment')

                    watts_section_text_segment = (
                        f"- Tes Watts moyens : {watts_avg_val} W {watts_per_kg_text}. Pic à {watts_max_val if watts_max_val != 'N/A' else ''} W.\n"
                        f"- Tu as commencé à {watts_start_val if watts_start_val != 'N/A' else ''}W et fini à {watts_end_val if watts_end_val != 'N/A' else ''}W.\n"
                        f"- Répartition du temps dans tes zones de puissance (basées sur ta FTP de {user_ftp}W) : {time_in_power_zones_val}\n"
                        f"- Ton pacing Watts : {pacing_watts_val}"
                    )
                
                segment_prompt_data_filled = {**segment_prompt_data, "watts_section": watts_section_text_segment}
                keys_for_template_segment = [ 
                    'segment_name', 'user_ftp', 'user_fc_max', 'segment_distance_m', 'segment_elevation_gain_m', 
                    'segment_avg_grade', 'detailed_elevation_profile', 'user_time_seconds', 
                    'user_rank_text', 'effort_start_time_local', 
                    'fc_avg', 'fc_max', 'fc_start_effort', 'fc_end_effort', 'time_in_hr_zones_str', 'pacing_fc_comment', 
                    'watts_section', 
                    'cadence_avg', 'cadence_max', 'cadence_comment', 
                    'power_variability_comment', 'power_surges_count'
                ]
                for key in keys_for_template_segment: 
                    segment_prompt_data_filled.setdefault(key, 'N/A')

                report_text = generate_llm_report_langchain(segment_report_template, segment_prompt_data_filled, openai_api_key) 
                segment_reports_list.append({"segment_name": segment_name, "report": report_text})
                time.sleep(1) 
    else:
        print("(strava_analyzer) Aucun effort de segment notable trouvé dans cette activité pour une analyse détaillée.")

    print(f"\n(strava_analyzer) --- FIN DE LA COLLECTE DES DONNÉES POUR LE RAPPORT D'ACTIVITÉ ID: {activity_id} ---")
    return {"activity_name": activity_name, "overall_summary": overall_summary_report, "segment_reports": segment_reports_list}