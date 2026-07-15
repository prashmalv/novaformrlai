"""
Clean matplotlib navigation toolbar — removes developer-facing buttons
(Configure subplots, Edit axis parameters) that confuse end users.
Keeps: Home, Back, Forward, Pan, Zoom, Save.
"""
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT


class NovoToolbar(NavigationToolbar2QT):
    # Only keep buttons useful to end users
    toolitems = [
        t for t in NavigationToolbar2QT.toolitems
        if t[0] in ('Home', 'Back', 'Forward', 'Pan', 'Zoom', 'Save', None)
    ]
