import requests
import os
import json
import time # Pour gérer les pauses et respecter les limites de l'API
import polyline # Pour décoder les polylignes Strava
import math # Pour les calculs trigonométriques (cap, distance)
from datetime import datetime # Pour manipuler les dates et heures

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

# --- FONCTIONS POUR LE VENT CORRIGEES ET OPTIMISEES ---
def get_wind_data(latitude, longitude, weather_api_key, timestamp_utc=None):
    """ Récupère les données de vent. Nécessite une clé API météo. """
    if not weather_api_key: 
        print("Erreur (get_wind_data): Clé API Météo (weather_api_key) requise.")
        return None
    
    weather_url = f"https://api.openweathermap.org/data/2.5/weather?lat={latitude}&lon={longitude}&appid={weather_api_key}&units=metric"
    print(f"  (strava_analyzer_v2) Appel à OpenWeatherMap pour le vent à ({latitude},{longitude})...")
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
                print("  (strava_analyzer_v2) Données de vitesse ou direction du vent manquantes dans la réponse.")
                return None
        print("  (strava_analyzer_v2) Clé 'wind' non trouvée dans la réponse d'OpenWeatherMap.")
        return None
    except requests.exceptions.HTTPError as http_err:
        print(f"  (strava_analyzer_v2) Erreur HTTP avec OpenWeatherMap: {http_err}")
        print(f"  (strava_analyzer_v2) Réponse: {response.text if 'response' in locals() else 'N/A'}")
    except Exception as e:
        print(f"  (strava_analyzer_v2) Erreur avec OpenWeatherMap: {e}")
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
    print(f"\n=== DEBUT RECHERCHE SUPER OPTIMISEE V2 ===")
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
        
        print(f"=== FIN RECHERCHE SUPER OPTIMISEE V2 ===\n")
        return tailwind_segments, None
        
    except Exception as e:
        return [], f"Erreur analyse du vent: {e}"

# --- FONCTIONS UTILITAIRES POUR COMPATIBILITE (si nécessaire) ---
def get_segment_details(segment_id, access_token_strava): 
    """Récupère les détails d'un segment (fonction de compatibilité)"""
    if not access_token_strava: return None
    endpoint = f"segments/{segment_id}" 
    return _make_strava_api_request(endpoint, access_token_strava)