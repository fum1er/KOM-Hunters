import requests
import os
import json
from dotenv import load_dotenv
import time # Pour gérer les pauses et respecter les limites de l'API
import polyline # Pour décoder les polylignes Strava
import math # Pour les calculs trigonométriques (cap, distance)
from datetime import datetime # Pour manipuler les dates et heures

# IMPORTS POUR LANGCHAIN ET OPENAI
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

# Charger les variables d'environnement
load_dotenv()

ACCESS_TOKEN = os.getenv('MY_NEW_STRAVA_ACCESS_TOKEN') 
OPENWEATHERMAP_API_KEY = os.getenv('OPENWEATHERMAP_API_KEY')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

BASE_STRAVA_URL = 'https://www.strava.com/api/v3'

# --- Fonctions Utilitaires et de Calcul de Zones ---
def _make_strava_api_request(endpoint, access_token, params=None, method='GET', payload=None):
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
        print(f"  Récupération de l'altitude pour {len(locations_payload)} points (chunk {i//chunk_size + 1}) via Open-Elevation...")
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
                print("  Erreur dans les données d'élévation reçues ou nombre de résultats incorrect pour ce chunk.")
                for original_coord in chunk: all_results_with_elevation.append((original_coord[0], original_coord[1], None))
        except Exception as e: 
            print(f"Une erreur est survenue avec Open-Elevation (chunk {i//chunk_size + 1}): {e}")
            for original_coord in chunk: all_results_with_elevation.append((original_coord[0], original_coord[1], None))
        if i + chunk_size < len(coordinates_list): time.sleep(1) 
    if len(all_results_with_elevation) == len(coordinates_list):
        print(f"  Altitudes récupérées (ou tentatives) pour {len(all_results_with_elevation)} points.")
        return all_results_with_elevation
    return None

def get_athlete_profile(access_token):
    endpoint = "athlete"
    print("\nRécupération du profil de l'athlète (pour le poids)...")
    profile_data = _make_strava_api_request(endpoint, access_token)
    if profile_data and 'weight' in profile_data:
        print(f"  Poids de l'athlète récupéré de Strava : {profile_data['weight']} kg.")
        return profile_data
    elif profile_data:
        print("  Poids non trouvé dans le profil Strava de l'athlète.")
        return profile_data 
    else:
        print("  Impossible de récupérer le profil de l'athlète.")
    return None

def calculate_hr_zones(user_fc_max):
    if not user_fc_max or user_fc_max <= 0:
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
        return None
    return {
        "Zone 1 (Récupération Active)": (0, round(user_ftp * 0.55) -1),
        "Zone 2 (Endurance)": (round(user_ftp * 0.56), round(user_ftp * 0.75) -1),
        "Zone 3 (Tempo)": (round(user_ftp * 0.76), round(user_ftp * 0.90) -1),
        "Zone 4 (Seuil Lactique - FTP)": (round(user_ftp * 0.91), round(user_ftp * 1.05) -1),
        "Zone 5 (VO2 Max)": (round(user_ftp * 1.06), round(user_ftp * 1.20) -1),
        "Zone 6 (Capacité Anaérobie)": (round(user_ftp * 1.21), round(user_ftp * 1.50) -1),
        "Zone 7 (Puissance Neuromusculaire)": (round(user_ftp * 1.51), float('inf'))
    }

def get_segment_details(segment_id, access_token): 
    endpoint = f"segments/{segment_id}" 
    return _make_strava_api_request(endpoint, access_token)

def get_activity_details_with_efforts(activity_id, access_token): 
    if not access_token or not activity_id:
        print("Erreur: Token d'accès et ID d'activité requis.")
        return None
    endpoint = f"activities/{activity_id}?include_all_efforts=true"
    print(f"\nRécupération des détails de l'activité ID: {activity_id} (avec tous les efforts)...")
    activity_data = _make_strava_api_request(endpoint, access_token)
    if activity_data:
        print(f"  Détails de l'activité '{activity_data.get('name')}' récupérés.")
    else:
        print(f"  Impossible de récupérer les détails pour l'activité ID: {activity_id}")
    return activity_data

def get_segment_effort_streams(segment_effort_id, access_token, stream_types=['time', 'latlng', 'heartrate', 'watts', 'cadence', 'velocity_smooth']): 
    if not access_token or not segment_effort_id:
        print("Erreur: Token d'accès et ID d'effort de segment requis.")
        return None
    keys_param = ",".join(stream_types)
    endpoint = f"segment_efforts/{segment_effort_id}/streams"
    params = {'keys': keys_param, 'key_by_type': 'true'} 
    print(f"  Récupération des streams pour l'effort de segment ID: {segment_effort_id} (types: {keys_param})...")
    streams_data = _make_strava_api_request(endpoint, access_token, params=params)
    if streams_data:
        print(f"    Streams récupérés avec succès.")
    else:
        print(f"    Impossible de récupérer les streams pour l'effort ID: {segment_effort_id}")
    return streams_data

def basic_stream_analysis(streams_data, hr_zones, power_zones, user_weight_kg): 
    analysis = {
        "fc_avg": None, "fc_max": None, "fc_start_effort": None, "fc_end_effort": None,
        "watts_avg": None, "watts_max": None, "watts_start_effort": None, "watts_end_effort": None,
        "watts_per_kg_avg": None, 
        "cadence_avg": None, "cadence_max": None, 
        "power_surges_count": 0, 
        "time_in_hr_zones_str": "Analyse des zones FC non disponible.", 
        "time_in_power_zones_str": "Analyse des zones de puissance non disponible.", 
        "pacing_fc_comment": "Données FC insuffisantes pour commentaire.",
        "pacing_watts_comment": "Données Watts insuffisantes pour commentaire.",
        "cadence_comment": "Données de cadence insuffisantes pour commentaire.", 
        "power_variability_comment": "Analyse de la variabilité de puissance non effectuée." 
    }
    if not streams_data: return analysis
    time_stream = streams_data.get('time', {}).get('data', [])
    num_points = len(time_stream)
    if num_points < 2: return analysis
    total_duration_stream = time_stream[-1] - time_stream[0] if time_stream else 0
    time_per_point_approx = total_duration_stream / (num_points -1) if num_points > 1 else 1

    if 'heartrate' in streams_data and streams_data['heartrate'].get('data') and hr_zones:
        fc_stream = streams_data['heartrate']['data']
        if len(fc_stream) == num_points: 
            analysis["fc_avg"] = round(sum(fc_stream) / len(fc_stream), 1)
            analysis["fc_max"] = max(fc_stream)
            analysis["fc_start_effort"] = fc_stream[0]
            analysis["fc_end_effort"] = fc_stream[-1]
            # (logique de pacing_fc_comment existante)
            time_in_zones_fc = {zone_name: 0 for zone_name in hr_zones}
            for fc_value in fc_stream:
                for zone_name, (lower, upper) in hr_zones.items():
                    if lower <= fc_value <= upper:
                        time_in_zones_fc[zone_name] += time_per_point_approx
                        break
            analysis["time_in_hr_zones_str"] = ", ".join([f"{name}: {time_sec:.0f}s" for name, time_sec in time_in_zones_fc.items() if time_sec > 0])
            if not analysis["time_in_hr_zones_str"]: analysis["time_in_hr_zones_str"] = "Pas de temps significatif passé dans les zones FC définies."

    if 'watts' in streams_data and streams_data['watts'].get('data') and streams_data['watts'].get('device_watts', True): 
        watts_stream = streams_data['watts']['data']
        if len(watts_stream) == num_points:
            analysis["watts_avg"] = round(sum(watts_stream) / len(watts_stream), 1)
            analysis["watts_max"] = max(watts_stream)
            analysis["watts_start_effort"] = watts_stream[0]
            analysis["watts_end_effort"] = watts_stream[-1]
            analysis["pacing_watts_comment"] = "Les données de puissance sont disponibles."
            if user_weight_kg and user_weight_kg > 0 and analysis["watts_avg"] is not None:
                analysis["watts_per_kg_avg"] = round(analysis["watts_avg"] / user_weight_kg, 2)
            # (logique de power_surges_count existante)
            if power_zones:
                time_in_zones_power = {zone_name: 0 for zone_name in power_zones}
                for p_value in watts_stream:
                    for zone_name, (lower, upper) in power_zones.items():
                        if lower <= p_value <= upper:
                            time_in_zones_power[zone_name] += time_per_point_approx
                            break
                analysis["time_in_power_zones_str"] = ", ".join([f"{name}: {time_sec:.0f}s" for name, time_sec in time_in_zones_power.items() if time_sec > 0])
                if not analysis["time_in_power_zones_str"]: analysis["time_in_power_zones_str"] = "Pas de temps significatif passé dans les zones de puissance définies."
    
    if 'cadence' in streams_data and streams_data['cadence'].get('data'):
        cadence_stream = streams_data['cadence']['data']
        if len(cadence_stream) > 0:
            active_cadence_stream = [c for c in cadence_stream if c > 0]
            if active_cadence_stream:
                analysis["cadence_avg"] = round(sum(active_cadence_stream) / len(active_cadence_stream), 1)
                analysis["cadence_max"] = max(active_cadence_stream)
                # (logique de cadence_comment existante)
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

def generate_llm_report_langchain(prompt_template_str, prompt_data_dict, model_name="gpt-4o-mini"):
    if not OPENAI_API_KEY:
        print("Erreur: Clé API OpenAI (OPENAI_API_KEY) non configurée dans .env.")
        return f"Erreur: Clé API OpenAI non configurée pour {prompt_data_dict.get('report_type', 'rapport inconnu')}."

    llm = ChatOpenAI(openai_api_key=OPENAI_API_KEY, model_name=model_name, temperature=0.75, max_tokens=1500) 
    prompt = ChatPromptTemplate.from_template(prompt_template_str)
    output_parser = StrOutputParser()
    chain = prompt | llm | output_parser
    
    print(f"\n--- PROMPT PRÉPARÉ POUR LANGCHAIN ({model_name}) ---")
    print(f"Prompt envoyé à OpenAI {llm.model_name} pour {prompt_data_dict.get('report_type', 'rapport inconnu')}...")
    print("---------------------------------------\n")

    try:
        report_text = chain.invoke(prompt_data_dict) 
        return report_text.strip()
    except Exception as e:
        print(f"Erreur inattendue lors de la génération du rapport {prompt_data_dict.get('report_type', '')} avec Langchain/OpenAI: {e}")
        return f"Erreur interne lors de la génération du rapport par l'IA pour {prompt_data_dict.get('report_type', '')}."

# --- FONCTION PRINCIPALE DE GÉNÉRATION DE RAPPORT D'ACTIVITÉ (CORRIGÉE) ---
def generate_activity_report_with_overall_summary(activity_id, access_token, weather_api_key, # weather_api_key est ici
                                     user_fc_max, user_ftp, user_weight_kg,
                                     notable_rank_threshold=10, 
                                     num_best_segments_to_analyze=2):
    
    activity_details = get_activity_details_with_efforts(activity_id, access_token)
    if not activity_details:
        print("Impossible de récupérer les détails de l'activité. Arrêt du rapport.")
        return {"activity_name": "Activité Inconnue", "overall_summary": "Données d'activité non disponibles.", "segment_reports": []}

    hr_zones = calculate_hr_zones(user_fc_max)
    power_zones = calculate_power_zones(user_ftp)

    activity_name = activity_details.get('name', 'Sortie sans nom')
    activity_type = activity_details.get('type', 'Activité')
    activity_distance_km = round(activity_details.get('distance', 0) / 1000, 2)
    activity_duration_sec = activity_details.get('moving_time', 0)
    activity_duration_formatted = time.strftime("%Hh%Mmin%Ss", time.gmtime(activity_duration_sec)) if activity_duration_sec else "N/A"
    activity_avg_hr = activity_details.get('average_heartrate')
    activity_max_hr_session = activity_details.get('max_heartrate') 
    activity_total_elevation_gain = activity_details.get('total_elevation_gain')
    activity_avg_watts = activity_details.get('average_watts') 

    intensity_comment = "Ta FC Max personnelle n'a pas été fournie ou est invalide, donc l'analyse d'intensité est basée sur les sensations générales."
    if hr_zones and activity_avg_hr: 
        percent_fc_max = (activity_avg_hr / user_fc_max) * 100
        intensity_level = "inconnue"
        for zone_name, (lower, upper) in hr_zones.items():
            if lower <= activity_avg_hr <= upper:
                intensity_level = zone_name
                break
        intensity_comment = f"Ton cœur a travaillé en moyenne à {activity_avg_hr} bpm ({percent_fc_max:.0f}% de ta FC Max estimée à {user_fc_max} bpm), ce qui place globalement cette séance en {intensity_level}. C'est une super info pour voir si tu étais dans tes objectifs d'entraînement !"
    elif activity_avg_hr:
         intensity_comment = f"Ta FC moyenne pour cette sortie a été de {activity_avg_hr} bpm. Avec ta FC Max, on pourrait décortiquer ça encore mieux !"

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
        "user_ftp": f"{user_ftp}W" if user_ftp else "N/A"
    }

    overall_summary_template = """
    En tant que coach KOM Hunters, ton rôle est d'être super motivant, un peu comme un ami qui te connaît bien et qui est passionné par tes progrès ! 
    Adresse-toi directement à l'athlète en utilisant "tu". Sois chaleureux, positif et donne envie de repartir à l'aventure.

    Voici le récap de ta dernière sortie "{activity_name}" ({activity_type}) :
    - Super distance de {activity_distance_km} km bouclée en {activity_duration_formatted} !
    - Tu as grimpé {activity_total_elevation_gain} de dénivelé positif. Respect !
    - Ton cœur a joué la mélodie de l'effort à {activity_avg_hr} en moyenne, avec un high score à {activity_max_hr_session}.
    - Puissance moyenne (si dispo) : {activity_avg_watts} (ta FTP perso est à {user_ftp}).
    - Mon petit commentaire sur l'intensité : {intensity_comment}

    Rédige un petit paragraphe de débriefing pour cette séance. Commence par une exclamation ou une phrase d'accroche sympa et personnalisée pour la sortie "{activity_name}". 
    Ensuite, commente l'effort global, l'intensité (en te basant sur le commentaire fourni et la relation FC moyenne/FC Max, ou Watts moyens/FTP).
    Mets en lumière un ou deux aspects que tu trouves chouettes (la distance, la durée, le dénivelé, ou la gestion de l'effort si tu peux le deviner).
    Termine par une phrase super motivante pour sa prochaine sortie, peut-être avec une petite touche d'humour sportif ou un clin d'œil.
    Fais comme si tu parlais à un pote après sa sortie, avec enthousiasme et bienveillance !
    """
    print(f"\nGénération du résumé global pour l'activité '{activity_name}'...")
    overall_summary_report = generate_llm_report_langchain(overall_summary_template, overall_prompt_data)
    
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
                if is_top_rank: rank_text_parts.append(f"Superbe Top {kom_rank} !")
                effort['notable_rank_text'] = " ".join(rank_text_parts) if rank_text_parts else "Belle performance !"
                score = float('inf')
                if is_pr: score = 0  
                if is_top_rank: score = min(score, kom_rank) 
                elif is_pr and not is_top_rank: score = 0.5 
                effort['performance_score'] = score
                notable_efforts.append(effort)
        
        notable_efforts.sort(key=lambda x: x['performance_score'])
        
        if notable_efforts:
            print(f"{len(notable_efforts)} effort(s) notable(s) identifié(s). Analyse des {min(len(notable_efforts), num_best_segments_to_analyze)} meilleur(s)...")
            
            for i, effort_data in enumerate(notable_efforts):
                if i >= num_best_segments_to_analyze:
                    break

                segment_id = effort_data['segment']['id']
                segment_name = effort_data['segment']['name']
                effort_id = effort_data['id']
                effort_start_time_str = effort_data.get('start_date_local') 
                
                print(f"\nPréparation de l'analyse pour le meilleur effort {i+1} sur le segment: '{segment_name}' (ID effort: {effort_id})")

                segment_details = get_segment_details(segment_id, access_token)
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
                effort_streams = get_segment_effort_streams(effort_id, access_token, stream_types=stream_types_to_fetch)
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
                    **stream_analysis_summary 
                }
                
                segment_report_template = """
                En tant que coach KOM Hunters, toujours aussi motivant et un brin espiègle, analyse cette performance spécifique sur le segment "{segment_name}".
                Ce rapport fait partie d'un débriefing plus large de la sortie, donc commence directement ton analyse sans salutations supplémentaires.
                Adresse-toi à l'athlète avec "tu".

                Voici les données de ton exploit sur le segment "{segment_name}" (FTP de référence: {user_ftp}):
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
                watts_section_text_segment = f"- Pas de données de puissance pour cet effort, mais avec la FC (zones basées sur ta FC Max de {user_fc_max} bpm) et la cadence on a déjà de quoi faire !"
                if segment_prompt_data.get('watts_avg'):
                    watts_section_text_segment = (
                        f"- Tes Watts moyens : {segment_prompt_data.get('watts_avg')} W ({segment_prompt_data.get('watts_per_kg_avg')} W/kg). Pic à {segment_prompt_data.get('watts_max')} W.\n"
                        f"- Tu as commencé à {segment_prompt_data.get('watts_start_effort')}W et fini à {segment_prompt_data.get('watts_end_effort')}W.\n"
                        f"- Répartition du temps dans tes zones de puissance (basées sur ta FTP de {user_ftp}W) : {segment_prompt_data.get('time_in_power_zones_str')}\n"
                        f"- Ton pacing Watts : {segment_prompt_data.get('pacing_watts_comment')}"
                    )
                
                segment_prompt_data_filled = {**segment_prompt_data, "watts_section": watts_section_text_segment}
                keys_for_template = [
                    'segment_name', 'segment_distance_m', 'segment_elevation_gain_m', 
                    'segment_avg_grade', 'detailed_elevation_profile', 'user_time_seconds', 
                    'user_rank_text', 'effort_start_time_local', 'user_ftp',
                    'fc_avg', 'fc_max', 'fc_start_effort', 'fc_end_effort', 'time_in_hr_zones_str', 'pacing_fc_comment', 
                    'cadence_avg', 'cadence_max', 'cadence_comment', 
                    'power_variability_comment', 'power_surges_count'
                ]
                for key in keys_for_template:
                    segment_prompt_data_filled.setdefault(key, 'N/A')


                report_text = generate_llm_report_langchain(segment_report_template, segment_prompt_data_filled) 
                segment_reports_list.append({"segment_name": segment_name, "report": report_text})
                time.sleep(1) 
    else:
        print("Aucun effort de segment trouvé dans cette activité pour une analyse détaillée.")

    return {"activity_name": activity_name, "overall_summary": overall_summary_report, "segment_reports": segment_reports_list}


if __name__ == '__main__':
    USER_MAX_HEART_RATE = 196  
    USER_FTP = 320             
    USER_WEIGHT_KG_DEFAULT = 80.0 

    if not ACCESS_TOKEN:
        print("Le token d'accès MY_NEW_STRAVA_ACCESS_TOKEN n'est pas défini dans .env.")
    elif not OPENAI_API_KEY: 
        print("La clé API OPENAI_API_KEY n'est pas définie dans .env.")
    else:
        print("Tokens et clés API chargés. Début des opérations...")

        user_weight_actual = USER_WEIGHT_KG_DEFAULT
        athlete_profile_data = get_athlete_profile(ACCESS_TOKEN)
        if athlete_profile_data and athlete_profile_data.get('weight') is not None:
            user_weight_actual = athlete_profile_data.get('weight')
            print(f"Poids de l'athlète utilisé pour les calculs W/kg : {user_weight_actual} kg.")
        else:
            print(f"Poids de l'athlète non trouvé sur Strava, utilisation du poids par défaut : {user_weight_actual} kg.")

        if USER_MAX_HEART_RATE <= 0: 
            print("ATTENTION: USER_MAX_HEART_RATE doit être une valeur positive. L'analyse d'intensité sera limitée.")
            USER_MAX_HEART_RATE = None 
        if USER_FTP <= 0:
            print("ATTENTION: USER_FTP doit être une valeur positive. L'analyse des zones de puissance sera limitée.")
            USER_FTP = None 

        current_test_activity_id = 13865286895 
        
        if current_test_activity_id == 0: 
            print("\nATTENTION: Veuillez remplacer 'current_test_activity_id' par un véritable ID d'activité.")
        else:
            print("\n--- Lancement de la génération du rapport d'activité complet (peut prendre du temps)... ---")
            
            full_activity_report = generate_activity_report_with_overall_summary(
                current_test_activity_id, 
                ACCESS_TOKEN, 
                OPENWEATHERMAP_API_KEY, 
                USER_MAX_HEART_RATE,
                USER_FTP,
                user_weight_actual, 
                notable_rank_threshold=10, 
                num_best_segments_to_analyze=2 
            )
            
            if full_activity_report:
                print("\n\n==============================================================")
                print("💪 K O M   H U N T E R S   -   TON DÉBRIEF DE COACH PERSO �")
                print("==============================================================")
                
                activity_name_for_title = full_activity_report.get("activity_name", "Ta Sortie")

                print(f"\nSalut l'artiste ! Alors, comment s'est passée cette sortie \"{activity_name_for_title}\" ? On regarde ça ensemble ? 😉")
                print("--------------------------------------------------------------\n")
                print(full_activity_report.get("overall_summary", "Résumé global non disponible. Mais chaque sortie est une victoire !"))
                
                segment_reports_list = full_activity_report.get("segment_reports", [])
                if segment_reports_list:
                    print("\n\n--- 🔥 TES EXPLOITS SUR LES SEGMENTS PASSÉS AU CRIBLE 🔥 ---")
                    for i, report_entry in enumerate(segment_reports_list): 
                        print(f"\n🎯 Zoom sur ta perf N°{i+1} : Segment \"{report_entry['segment_name']}\"")
                        print("--------------------------------------------------------------")
                        print(report_entry['report'])
                else:
                    print("\nPas de performances de folie sur les segments à analyser en détail pour cette fois, mais la prochaine sera la bonne !")
                
                print("\n\n==============================================================")
                print("Super boulot en tout cas ! Continue de chasser ces KOMs (et tes propres limites) ! La route est longue mais la gloire est éternelle... ou presque ! 😄")
                print("À très vite pour ton prochain débrief, champion(ne) !")
                print("==============================================================")

            else:
                print("\nMalheureusement, aucun rapport complet n'a pu être généré pour cette activité. Un petit bug dans la matrice ? 🤔")
            
        print("\n--- Fin des tests principaux ---")
