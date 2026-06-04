from django.shortcuts import render
from .models import Produit, Avis

PRODUIT_DEFAUT = {
    'nom': 'LUMØRA Masque Lumière',
    'description': 'Masque LED luminothérapie 7 spectres cliniquement validés.',
    'prix': 69,
    'prix_barre': 109,
    'stock': 23,
    'reduction_pct': 37,
}

AVIS_DEFAUT = [
    {'prenom': 'Sophie M.', 'ville': 'Lyon', 'note': 5, 'etoiles': range(5),
     'texte': "J'étais sceptique — encore un gadget de plus. Mais après 3 semaines, mes collègues m'ont demandé si j'avais changé ma routine. Mon teint est littéralement méconnaissable.",
     'delai': 'il y a 12 jours'},
    {'prenom': 'Camille R.', 'ville': 'Paris', 'note': 5, 'etoiles': range(5),
     'texte': "Peau acnéique depuis l'ado. En 21 jours de mode bleu, mes boutons ont pratiquement disparu. Ce que les antibiotiques n'ont pas réussi en 6 mois, ce masque l'a fait en 3 semaines.",
     'delai': 'il y a 8 jours'},
    {'prenom': 'Amandine L.', 'ville': 'Bordeaux', 'note': 5, 'etoiles': range(5),
     'texte': "À 41 ans, mes rides frontales commençaient à bien s'installer. Mode rouge chaque soir : mes rides du lion ont diminué de moitié en un mois. Ma dermatologue m'a demandé ce que j'avais fait.",
     'delai': 'il y a 3 semaines'},
    {'prenom': 'Marie-Claire D.', 'ville': 'Montréal', 'note': 5, 'etoiles': range(5),
     'texte': "Commandé un soir après une vidéo TikTok. Reçu 3 jours après, impeccablement emballé. Après 2 semaines : pores réduits, teint homogène.",
     'delai': 'il y a 5 jours'},
    {'prenom': 'Julie V.', 'ville': 'Bruxelles', 'note': 5, 'etoiles': range(5),
     'texte': "J'en suis à mon 2e masque — j'en ai offert un à ma sœur. Je dépensais 400€/an en séances. Ce masque m'en coûte 69€ une fois pour toutes.",
     'delai': 'il y a 1 mois'},
]

OFFRES = [
    {
        'icone': '✦', 'titre': 'Solo', 'featured': False,
        'desc': 'Pour découvrir la luminothérapie à domicile',
        'prix': 69, 'prix_barre': 109, 'economie': 40,
        'perks': ['1 masque LUMØRA', 'Guide protocole PDF', 'Livraison offerte', '30 jours satisfait/remboursé'],
    },
    {
        'icone': '💎', 'titre': 'Duo Rituel', 'featured': True,
        'desc': 'Pour vous et votre proche — économisez encore plus',
        'prix': 109, 'prix_barre': 218, 'economie': 109,
        'perks': ['2 masques LUMØRA', 'Guide + carnet de suivi', 'Livraison prioritaire 24h', 'Emballage cadeau offert', '30 jours satisfait/remboursé'],
    },
    {
        'icone': '👑', 'titre': 'Famille', 'featured': False,
        'desc': 'Le pack complet pour toute la maison',
        'prix': 149, 'prix_barre': 327, 'economie': 178,
        'perks': ['3 masques LUMØRA', 'Guide + programme 90 jours', 'Livraison prioritaire 24h', 'Support personnalisé 90j', '30 jours satisfait/remboursé'],
    },
]

SPECTRES = [
    {'emoji': '🔴', 'nm': '630nm', 'couleur': 'Rouge',   'desc': 'Stimule la synthèse de collagène et d\'élastine. Réduit les rides fines et raffermit les contours du visage.'},
    {'emoji': '🔵', 'nm': '415nm', 'couleur': 'Bleu',    'desc': 'Action antibactérienne puissante. Élimine les bactéries responsables de l\'acné à la surface et en profondeur.'},
    {'emoji': '🟡', 'nm': '590nm', 'couleur': 'Jaune',   'desc': 'Stimule la lymphe et réduit les rougeurs. Unifie le teint et apporte un éclat naturel immédiat.'},
    {'emoji': '🟢', 'nm': '520nm', 'couleur': 'Vert',    'desc': 'Régule la production de mélanine. Atténue les taches pigmentaires et les cicatrices d\'acné.'},
    {'emoji': '🟣', 'nm': '380nm', 'couleur': 'Violet',  'desc': 'Synergie rouge+bleu amplifiée. Accélère la régénération cellulaire et combat l\'acné inflammatoire.'},
    {'emoji': '🩵', 'nm': '490nm', 'couleur': 'Cyan',    'desc': 'Hydratation cellulaire profonde. Renforce la barrière cutanée et réduit la sensibilité.'},
    {'emoji': '⚪', 'nm': 'Total', 'couleur': 'Blanc',   'desc': 'Combinaison de toutes les fréquences pour un soin global. Le mode "reset" quotidien de votre peau.'},
]


def index(request):
    try:
        produit = Produit.objects.filter(actif=True).first()
        avis = list(Avis.objects.filter(verifie=True)[:5])
        if not avis:
            avis = AVIS_DEFAUT
        ctx_produit = produit if produit else PRODUIT_DEFAUT
    except Exception:
        ctx_produit = PRODUIT_DEFAUT
        avis = AVIS_DEFAUT

    return render(request, 'store/index.html', {
        'produit': ctx_produit,
        'avis': avis,
        'offres': OFFRES,
        'spectres': SPECTRES,
        'stats': {'clientes': 12348, 'note': '4,9', 'recommandent': 94},
    })
