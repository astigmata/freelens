import dash
from dash import html
from layout import create_layout
from callbacks import register_callbacks

# Initialisation de l'application Dash
app = dash.Dash(__name__, suppress_callback_exceptions=True)

# Création de la mise en page
app.layout = create_layout()

# Enregistrement des callbacks
register_callbacks(app)

# CSS personnalisé pour l'application
app.index_string = '''
<!DOCTYPE html>
<html>
    <head>
        {%metas%}
        <title>Kubernetes Explorer</title>
        {%favicon%}
        {%css%}
        <link rel="stylesheet" href="assets/styles.css">
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

if __name__ == '__main__':
    app.run(debug=True, port=8050)
