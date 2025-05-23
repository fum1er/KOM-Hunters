import plotly.graph_objects as go
from dotenv import load_dotenv
import os
load_dotenv()
MAPBOX_ACCESS_TOKEN = os.getenv('MAPBOX_ACCESS_TOKEN')
# Remplace par ta vraie clé Mapbox ici directement pour le test


fig = go.Figure(go.Scattermapbox(
    lat=['47.7626'],
    lon=['-2.4500'],
    mode='markers',
    marker=go.scattermapbox.Marker(size=14),
    text=['Questembert'],
))

fig.update_layout(
    hovermode='closest',
    mapbox=dict(
        accesstoken=MAPBOX_ACCESS_TOKEN,
        bearing=0,
        center=go.layout.mapbox.Center(lat=47.7626, lon=-2.4500),
        pitch=0,
        zoom=10,
        style='streets' # Tu peux aussi essayer 'open-street-map'
    )
)
fig.show()