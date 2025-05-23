import requests
import os
import json
from dotenv import load_dotenv
import time # Pour gérer les pauses et respecter les limites de l'API

# Charger les variables d'environnement du fichier .env
load_dotenv()

# Récupérer le nouvel access token obtenu via le flux OAuth
# Assure-toi que la clé correspond à ce que tu as mis dans .env
ACCESS_TOKEN = os.getenv('MY_NEW_STRAVA_ACCESS_TOKEN') 

# Nom du fichier où sauvegarder les données
OUTPUT_FILENAME = 'strava_activity_summaries.json'

def fetch_all_strava_activities(token):
    """
    Récupère tous les résumés d'activité d'un athlète depuis l'API Strava
    en gérant la pagination et les limites de taux.
    """
    if not token:
        print("Erreur: Access Token non trouvé. Vérifiez la variable d'environnement MY_NEW_STRAVA_ACCESS_TOKEN.")
        return None

    headers = {'Authorization': f'Bearer {token}'}
    activities_url = 'https://www.strava.com/api/v3/athlete/activities'
    
    all_activities = []
    page = 1
    # Strava permet jusqu'à 200 activités par page, mais commençons avec 100 pour être prudent.
    # Tu peux augmenter à 200 si tu as beaucoup d'activités et que tu veux minimiser les appels.
    per_page = 100 
    
    print(f"Début de la récupération des résumés d'activités (max {per_page} par page)...")

    while True:
        params = {'page': page, 'per_page': per_page}
        print(f"Récupération de la page {page}...")
        
        try:
            response = requests.get(activities_url, headers=headers, params=params)
            response.raise_for_status() # Lève une exception pour les erreurs HTTP (4xx ou 5xx)
            current_page_activities = response.json()
            
            if not current_page_activities: # Si la page est vide, c'est la fin.
                print("Plus d'activités à récupérer.")
                break
            
            all_activities.extend(current_page_activities)
            print(f"  {len(current_page_activities)} activités récupérées sur cette page. Total actuel : {len(all_activities)}")
            
            page += 1
            
            # Respect des limites de l'API Strava (ex: 100 requêtes de lecture / 15 mins)
            # Une petite pause d'1 seconde entre les pages est une bonne pratique.
            # Si tu as des milliers d'activités, tu pourrais avoir besoin d'une pause plus longue
            # ou d'une logique plus sophistiquée pour gérer les limites de taux.
            time.sleep(1) # Pause d'1 seconde

        except requests.exceptions.HTTPError as http_err:
            print(f"Erreur HTTP à la page {page}: {http_err}")
            if response.status_code == 401:
                print("L'Access Token est peut-être invalide ou a expiré.")
            elif response.status_code == 429:
                print("Limite de taux de l'API atteinte ! Veuillez attendre et réessayer plus tard, ou augmenter la pause.")
            print(f"Réponse de l'API : {response.text}")
            break # Arrêter en cas d'erreur HTTP majeure
        except requests.exceptions.RequestException as req_err:
            print(f"Erreur de requête (problème réseau ?) à la page {page}: {req_err}")
            break
        except Exception as e:
            print(f"Une erreur inattendue est survenue à la page {page}: {e}")
            break
            
    return all_activities

def save_data_to_json(data, filename):
    """Sauvegarde les données dans un fichier JSON."""
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        print(f"\n{len(data) if data else 0} éléments sauvegardés avec succès dans {filename}")
    except IOError as e:
        print(f"Erreur lors de l'écriture du fichier {filename}: {e}")
    except TypeError as e:
        print(f"Erreur de type lors de la préparation des données pour JSON (cela peut arriver avec des objets date/heure non sérialisables): {e}")


if __name__ == '__main__':
    print("Lancement du script Workspace_all_activities.py...")
    
    activity_summaries = fetch_all_strava_activities(ACCESS_TOKEN)
    
    if activity_summaries is not None and len(activity_summaries) > 0:
        save_data_to_json(activity_summaries, OUTPUT_FILENAME)
    elif activity_summaries is None:
        print("La récupération des activités a échoué, aucun fichier de sortie n'a été créé.")
    else: # activity_summaries est une liste vide
        print("Aucune activité n'a été récupérée (peut-être que l'athlète n'a pas d'activités ou un problème est survenu).")
        
    print("\nScript terminé.")