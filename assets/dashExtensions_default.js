window.dashExtensions = Object.assign({}, window.dashExtensions, {
    default: {
        function0: function(event) {
            // Pour déboguer dans la console du navigateur
            console.log('Event reçu:', event);

            if (event && event.points && event.points.length > 0) {
                const point = event.points[0];

                // Pour un clic sur la carte Mapbox, on récupère directement les coordonnées
                // du clic depuis l'événement Plotly (peu importe s'il y a un point ou non)
                return {
                    'lat': point.lat,
                    'lon': point.lon,
                    'type': 'map_click'
                };
            }
            return null;
        }

    }
});