window.dashExtensions = Object.assign({}, window.dashExtensions, {
    default: {
        function0: function(event) {
            // Pour d�boguer dans la console du navigateur
            console.log('Event re�u:', event);

            if (event && event.points && event.points.length > 0) {
                const point = event.points[0];

                // Pour un clic sur la carte Mapbox, on r�cup�re directement les coordonn�es
                // du clic depuis l'�v�nement Plotly (peu importe s'il y a un point ou non)
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